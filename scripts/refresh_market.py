"""Download every priced 0912 listing and replace the live valuation snapshot.

rond.ir sits behind a browser challenge, so the download runs inside headless
Chrome after the page itself has been allowed through. The live database is
replaced only when the new catalog is complete and large enough. The web
process keeps serving the previous snapshot until this script restarts it.
"""

from __future__ import annotations

import base64
import json
import math
import os
import shutil
import signal
import socket
import struct
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.refresh import (  # noqa: E402
    accept_new_snapshot,
    listing_count,
    publish_files,
    rows_from_pages,
)
from app.valuation import (  # noqa: E402
    DATA,
    DB_PATH,
    build_engine,
    dump_metrics,
    listings_from_rows,
    save_listings,
)

PAGE_SIZE = 40
BATCH = 8
MAX_PAGES = 2500
TEHRAN = ZoneInfo("Asia/Tehran")
PUBLISHED = ("market.db", "model.joblib", "metrics.json")

BODY = {
    "advertPriceTypeIn": ["PRICE"],
    "advertPriceTypeNotIn": [],
    "advertSellTypeIn": [],
    "advertSellTypeNotIn": [],
    "advertSpecialTypeIn": [],
    "advertSpecialTypeNotIn": [],
    "cityIdIn": [],
    "operatorIdIn": [],
    "operatorIdNotIn": [],
    "provinceIdIn": [],
    "rondTypeIds": [],
    "searchReference": "SEARCH",
    "simCardNumberPreCodes": ["0912"],
    "simCardNumberPreCodesNotIn": [],
    "simCardNumberWithoutPreCodePattern": "\\d\\d\\d\\d\\d\\d\\d",
    "simCardStatusIn": [],
    "simCardTypeIn": [],
    "hasShop": None,
}

JS_FETCH = r"""
(pages) => new Promise((resolve) => {
  const body = __BODY__;
  const results = new Array(pages.length);
  let done = 0;
  if (!pages.length) { resolve("[]"); return; }
  pages.forEach((p, i) => {
    const url = '/api/ns/sim-card/web/sim-card-advert/page?page=' + p
      + '&size=40&sort=advertSpecialType,desc&sort=lastUpdateDateMillis,desc&sort=createDateMillis,desc';
    const x = new XMLHttpRequest();
    x.open('POST', url);
    x.setRequestHeader('Content-Type', 'application/json');
    x.setRequestHeader('Accept', 'application/json, text/plain, */*');
    x.setRequestHeader('skip', 'true');
    x.onload = () => {
      let parsed = null;
      try { parsed = JSON.parse(x.responseText); } catch (e) {}
      if (!parsed || !parsed.content) {
        results[i] = {page: p, error: true, status: x.status, head: (x.responseText || '').slice(0, 40)};
      } else {
        results[i] = {
          page: p,
          total: parsed.totalElements,
          items: parsed.content.map(c => ({
            num: c.simCardNumber,
            price: c.price,
            status: c.simCardStatus
          }))
        };
      }
      done++;
      if (done === pages.length) resolve(JSON.stringify(results));
    };
    x.onerror = () => {
      results[i] = {page: p, error: true, status: 0};
      done++;
      if (done === pages.length) resolve(JSON.stringify(results));
    };
    x.send(JSON.stringify(body));
  });
})
""".replace("__BODY__", json.dumps(BODY))


def chrome_binary() -> str:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    raise RuntimeError("headless Chrome is not installed")


class CDP:
    """Tiny DevTools client. Chrome's debugger socket speaks WebSocket."""

    def __init__(self, ws_url: str):
        if not ws_url.startswith("ws://"):
            raise RuntimeError(f"unexpected debugger url {ws_url}")
        hostport, path = ws_url[5:].split("/", 1)
        host, port = hostport.split(":")
        self.sock = socket.create_connection((host, int(port)), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        request = (
            f"GET /{path} HTTP/1.1\r\n"
            f"Host: {hostport}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(request.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError("debugger closed during handshake")
            buf += chunk
        if b" 101 " not in buf.split(b"\r\n", 1)[0]:
            raise RuntimeError(buf[:200].decode("utf-8", "replace"))
        self.msg_id = 0

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        mask = os.urandom(4)
        header = bytearray([0x80 | opcode])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header += struct.pack("!H", length)
        else:
            header.append(0x80 | 127)
            header += struct.pack("!Q", length)
        header += mask
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def _recv_frame(self, timeout: float) -> tuple[int, bytes]:
        self.sock.settimeout(timeout)

        def readn(size: int) -> bytes:
            out = b""
            while len(out) < size:
                chunk = self.sock.recv(size - len(out))
                if not chunk:
                    raise RuntimeError("debugger socket closed")
                out += chunk
            return out

        first, second = readn(2)
        opcode = first & 0x0F
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", readn(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", readn(8))[0]
        if second & 0x80:
            mask = readn(4)
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(readn(length)))
        else:
            payload = readn(length)
        return opcode, payload

    def _recv_message(self, timeout: float) -> dict:
        deadline = time.time() + timeout
        parts: list[bytes] = []
        opcode = 0
        while True:
            remaining = max(1.0, deadline - time.time())
            frame_opcode, payload = self._recv_frame(remaining)
            if frame_opcode == 0x9:
                self._send_frame(0xA, payload)
                continue
            if frame_opcode == 0x8:
                raise RuntimeError("debugger closed the socket")
            if frame_opcode in (0x1, 0x0):
                if frame_opcode == 0x1:
                    opcode = 0x1
                    parts = [payload]
                else:
                    parts.append(payload)
                # A finished text message has the FIN bit. _recv_frame does not
                # expose FIN, and Chrome sends these replies in one frame.
                if opcode == 0x1:
                    return json.loads(b"".join(parts))
            if time.time() > deadline:
                raise TimeoutError("debugger message")

    def call(self, method: str, params: dict | None = None, timeout: float = 90) -> dict:
        self.msg_id += 1
        ident = self.msg_id
        self._send_frame(
            0x1,
            json.dumps({"id": ident, "method": method, "params": params or {}}).encode(),
        )
        deadline = time.time() + timeout
        while time.time() < deadline:
            message = self._recv_message(max(1.0, deadline - time.time()))
            if message.get("id") == ident:
                return message
        raise TimeoutError(method)

    def evaluate(self, expression: str, timeout: float = 90) -> str:
        message = self.call(
            "Runtime.evaluate",
            {"expression": expression, "awaitPromise": True, "returnByValue": True},
            timeout=timeout,
        )
        result = message.get("result", {}).get("result", {})
        if "value" not in result:
            raise RuntimeError(json.dumps(message)[:500])
        return result["value"]


class Browser:
    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self.cdp: CDP | None = None
        self.profile = Path(f"/tmp/rond-chrome-{os.getpid()}")

    def __enter__(self) -> Browser:
        self.open()
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def open(self) -> None:
        if self.profile.exists():
            shutil.rmtree(self.profile, ignore_errors=True)
        self.profile.mkdir(parents=True)
        port = 9222
        env = os.environ.copy()
        env["TZ"] = "Asia/Tehran"
        self.proc = subprocess.Popen(
            [
                chrome_binary(),
                "--headless=new",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-extensions",
                f"--remote-debugging-port={port}",
                "--remote-allow-origins=*",
                f"--user-data-dir={self.profile}",
                "--lang=fa-IR",
                "--window-size=1366,768",
                "https://rond.ir/",
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        page = None
        for _ in range(80):
            if self.proc.poll() is not None:
                raise RuntimeError("Chrome exited before the debugger was ready")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=2) as response:
                    tabs = json.load(response)
                page = next(tab for tab in tabs if tab.get("type") == "page")
                break
            except Exception:
                time.sleep(0.25)
        if page is None:
            raise RuntimeError("Chrome did not open a debugger tab")
        self.cdp = CDP(page["webSocketDebuggerUrl"])
        self._wait_until_api_open()

    def close(self) -> None:
        if self.cdp is not None:
            self.cdp.close()
            self.cdp = None
        proc = self.proc
        self.proc = None
        if proc is not None and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait(timeout=5)
        shutil.rmtree(self.profile, ignore_errors=True)

    def _wait_until_api_open(self) -> None:
        assert self.cdp is not None
        for _ in range(40):
            probe = self.cdp.evaluate(
                """new Promise((resolve) => {
                  const x = new XMLHttpRequest();
                  x.open('GET', '/api/ns/sim-card/web/rond-types');
                  x.setRequestHeader('Accept','application/json');
                  x.setRequestHeader('skip','true');
                  x.onload = () => resolve((x.responseText || '').slice(0, 1));
                  x.onerror = () => resolve('');
                  x.send();
                })""",
                timeout=30,
            )
            if probe == "[":
                return
            time.sleep(1)
        raise RuntimeError("rond.ir did not accept the browser session")

    def fetch_pages(self, pages: list[int]) -> list[dict]:
        assert self.cdp is not None
        expression = f"({JS_FETCH})({json.dumps(pages)})"
        raw = self.cdp.evaluate(expression, timeout=90)
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            raise RuntimeError("unexpected page batch")
        return parsed


def collect_pages(browser: Browser) -> list[dict]:
    collected: dict[int, dict] = {}
    total = _fetch_range(browser, collected, [0])
    page_count = math.ceil(int(total) / PAGE_SIZE)
    if page_count < 1 or page_count > MAX_PAGES:
        raise RuntimeError(f"unexpected catalog size: {total}")
    pending = [page for page in range(page_count) if page not in collected]
    _fetch_range(browser, collected, pending)
    # Ads published while the crawl runs show up past the original last page.
    extra = 0
    while extra < 40:
        last = collected[max(collected)]
        if len(last.get("items") or []) < PAGE_SIZE:
            break
        nxt = max(collected) + 1
        if nxt >= MAX_PAGES:
            break
        _fetch_range(browser, collected, [nxt])
        extra += 1
    last_index = max(collected)
    missing = [page for page in range(last_index + 1) if page not in collected]
    if missing:
        raise RuntimeError(f"missing {len(missing)} catalog pages")
    for page in range(last_index):
        if len(collected[page].get("items") or []) != PAGE_SIZE:
            raise RuntimeError(f"catalog page {page} was short")
    if len(collected[last_index].get("items") or []) >= PAGE_SIZE:
        raise RuntimeError("catalog did not end on a short page")
    pages = [collected[page] for page in range(max(collected) + 1)]
    print(
        f"collected pages={len(pages)} total={total} rows={sum(len(p.get('items') or []) for p in pages)}",
        flush=True,
    )
    return pages


def _fetch_range(browser: Browser, collected: dict[int, dict], pages: list[int]) -> int:
    total = 0
    cursor = 0
    while cursor < len(pages):
        batch = pages[cursor : cursor + BATCH]
        parsed = _fetch_batch(browser, batch)
        for part in parsed:
            if part.get("error"):
                raise RuntimeError(f"catalog page failed: {part}")
            collected[int(part["page"])] = part
            total = int(part.get("total") or total)
            print(
                f"page {part['page']} n={len(part.get('items') or [])} total={part.get('total')}",
                flush=True,
            )
        cursor += BATCH
        time.sleep(0.1)
    return total


def _fetch_batch(browser: Browser, batch: list[int]) -> list[dict]:
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            parsed = browser.fetch_pages(batch)
            if len(parsed) != len(batch) or any(part.get("error") for part in parsed):
                raise RuntimeError(json.dumps(parsed)[:300])
            return parsed
        except Exception as exc:
            last_error = exc
            print(f"retry batch {batch[0]} attempt {attempt + 1}: {exc}", flush=True)
            time.sleep(2 + attempt * 2)
    raise RuntimeError(f"giving up on pages {batch[0]}-{batch[-1]}: {last_error}")


def collect_rows() -> list[dict]:
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            with Browser() as browser:
                return rows_from_pages(collect_pages(browser))
        except Exception as exc:
            last_error = exc
            print(f"collect attempt {attempt + 1} failed: {exc}", flush=True)
            time.sleep(3)
    raise RuntimeError(f"could not download the catalog: {last_error}")


def rebuild(rows: list[dict]) -> None:
    previous = listing_count(DB_PATH)
    listings = listings_from_rows(rows)
    accept_new_snapshot(len(listings), previous)
    kept = [
        {"number": item.number, "price": item.price, "status": item.status}
        for item in listings
    ]
    print(f"training on {len(kept)} priced listings (live was {previous})", flush=True)
    engine = build_engine(kept)
    engine.metrics["refreshed_at"] = datetime.now(TEHRAN).isoformat(timespec="seconds")
    engine.metrics["listings"] = len(kept)
    staging = DATA / ".staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        save_listings(listings, staging / "market.db")
        engine.save(staging / "model.joblib")
        dump_metrics(engine, staging / "metrics.json")
        publish_files(staging, DATA, PUBLISHED)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    print("published", engine.metrics["refreshed_at"], flush=True)


def restart_service() -> None:
    if os.environ.get("SIMPRICE_RESTART", "1") != "1":
        print("skipping service restart", flush=True)
        return
    if shutil.which("systemctl") is None:
        return
    subprocess.run(["systemctl", "restart", "simprice.service"], check=True)
    print("restarted simprice", flush=True)


def main() -> None:
    if os.environ.get("SIMPRICE_SMOKE") == "1":
        with Browser() as browser:
            part = browser.fetch_pages([0])[0]
            print(
                "smoke",
                "error" if part.get("error") else "ok",
                "total",
                part.get("total"),
                "n",
                len(part.get("items") or []),
                flush=True,
            )
        return
    rows = collect_rows()
    print(f"unique numbers {len(rows)}", flush=True)
    rebuild(rows)
    restart_service()


if __name__ == "__main__":
    main()
