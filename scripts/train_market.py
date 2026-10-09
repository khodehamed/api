"""Build the market database and valuation model from collected rond.ir pages."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.patterns import detect
from app.valuation import (
    DATA,
    build_engine,
    dump_metrics,
    listings_from_rows,
    save_listings,
)

PAGE_DIR = Path("/tmp/rond_pages")


def load_rows() -> list[dict]:
    rows = []
    seen = set()
    for path in sorted(PAGE_DIR.glob("page_*.json")):
        payload = json.loads(path.read_text())
        for item in payload.get("items") or []:
            number = item.get("num") or ""
            if number in seen:
                continue
            seen.add(number)
            rows.append(
                {
                    "number": number,
                    "price": item.get("price") or 0,
                    "status": item.get("status") or "UNKNOWN",
                }
            )
    return rows


def main() -> None:
    rows = load_rows()
    print(f"raw listings {len(rows)}")
    if len(rows) < 1000:
        raise SystemExit("listing download is incomplete")
    listings = listings_from_rows(rows)
    print(f"priced listings kept {len(listings)}")
    save_listings(listings)
    # build_engine re-detects; pass the original priced rows so prices survive.
    kept_rows = [
        {"number": item.number, "price": item.price, "status": item.status}
        for item in listings
    ]
    engine = build_engine(kept_rows)
    engine.save()
    dump_metrics(engine)
    print("metrics", json.dumps(engine.metrics, ensure_ascii=False))

    probes = [
        "09121796900",
        "09122013456",
        "09122003456",
        "09121111111",
        "09122251225",
        "09121234567",
        "09129000000",
    ]
    for number in probes:
        result = engine.estimate(number)
        analysis = detect(number)
        print(
            number,
            analysis.primary if analysis else None,
            f"{result.get('price', 0):,}",
            result.get("source"),
            result.get("confidence"),
            "comps",
            [sample["number"] for sample in result.get("samples", [])[:3]],
        )


if __name__ == "__main__":
    main()
