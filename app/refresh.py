"""Decide when a freshly downloaded rond.ir snapshot may replace the live one."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

# A partial crawl must not replace the market. The live catalog is tens of
# thousands of priced 0912 ads; anything smaller is an incomplete download.
MIN_PRICED = 10_000
# A complete-looking but much smaller catalog is still rejected so a bad
# filter on the source site cannot wipe the prices the model was built on.
MIN_RATIO = 0.6


def rows_from_pages(pages: list[dict]) -> list[dict]:
    """Flatten collected pages. The first copy of a number wins.

    Pages are requested newest-first, so the earlier page is the newer ad.
    """
    rows: list[dict] = []
    seen: set[str] = set()
    ordered = sorted(pages, key=lambda page: int(page.get("page", 0)))
    for page in ordered:
        for item in page.get("items") or []:
            number = str(item.get("num") or "")
            if not number or number in seen:
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


def accept_new_snapshot(new_count: int, previous_count: int | None) -> None:
    if new_count < MIN_PRICED:
        raise RuntimeError(
            f"refusing snapshot with {new_count} priced listings (minimum {MIN_PRICED})"
        )
    if previous_count is not None and new_count < previous_count * MIN_RATIO:
        raise RuntimeError(
            f"refusing snapshot with {new_count} listings; live database has {previous_count}"
        )


def listing_count(path: Path) -> int | None:
    if not path.exists():
        return None
    conn = sqlite3.connect(path)
    try:
        return int(conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0])
    finally:
        conn.close()


def freshness_line(refreshed_at: str | None) -> str:
    if not refreshed_at:
        return "کل آگهی‌های قیمت‌دار هر روز یک‌بار از rond.ir گرفته می‌شود."
    stamp = refreshed_at.replace("T", " ")[:16]
    return (
        "کل آگهی‌های قیمت‌دار هر روز یک‌بار از rond.ir گرفته می‌شود. "
        f"آخرین بروزرسانی: {stamp} به وقت تهران."
    )


def publish_files(staging: Path, live: Path, names: tuple[str, ...]) -> None:
    """Atomically replace live files with a finished staging snapshot."""
    live.mkdir(parents=True, exist_ok=True)
    for name in names:
        source = staging / name
        if not source.is_file():
            raise RuntimeError(f"staging snapshot is missing {name}")
        os.replace(source, live / name)
