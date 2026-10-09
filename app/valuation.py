"""Price a 0912 number from mined rond classes and the live listing market.

Two signals are combined:

* a gradient-boosted model trained on the structural features of every priced
  listing (code, block, rond class, trailing zeros, digit entropy, status);
* a comparable-sales lookup that only averages listings in the same code whose
  rond class, trailing zeros, and middle block are actually close.

The blend weights are chosen on a held-out slice of the market, then the model
is refit on every listing. The public result is a single price, the detected
rond classes, and the listings that justified the number.
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import train_test_split

from app.patterns import SPECIFICITY, Analysis, detect

# Classes at least this specific are allowed to match across 3-digit blocks
# inside the same code. Weaker classes (a loose step, a 3-digit sequence,
# a birth year) are common and must not pull a line out of its block.
STRONG_RANK = 26

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DB_PATH = DATA / "market.db"
MODEL_PATH = DATA / "model.joblib"

PRICE_MIN = 5_000_000
PRICE_MAX = 50_000_000_000
QUOTE_STEP = 500_000

CATEGORICAL = ["code", "status", "primary_type"]
NUMERIC = [
    "block_level",
    "trailing_zeros",
    "unique_digits",
    "max_run",
    "mirror_pairs",
    "sequential_len",
    "sequential_reversed",
    "n_types",
    "entropy",
    "is_ordinary",
]

# Binary pattern flags that actually move price. Kept as a stable column list
# so a saved model and a live query describe the same vector.
PATTERN_FLAGS = [
    "هفت رقم یکی",
    "میلیونی",
    "ده هزاری از آخر",
    "ده هزاری از اول",
    "شش رقم یکی از آخر",
    "شش رقم یکی از اول",
    "پنج رقم یکی از آخر",
    "پنج رقم یکی از اول",
    "پنج رقم یکی از وسط",
    "چهار رقم یکی از آخر",
    "چهار رقم یکی از اول",
    "چهار رقم یکی از وسط",
    "سه رقم یکی از آخر",
    "سه رقم یکی از اول",
    "سه رقم یکی از وسط",
    "هزاری از آخر",
    "هزاری از اول",
    "ترازویی",
    "آینه‌ای",
    "گفتاری",
    "سه پله",
    "سه جفت از اول",
    "سه جفت از آخر",
    "صد صدی",
    "پله‌ای از اول",
    "پله‌ای از آخر",
    "جفت جفت از اول",
    "جفت جفت از آخر",
    "ترتیبی از اول",
    "ترتیبی از آخر",
    "ده دهی از اول",
    "ده دهی از آخر",
    "تاریخ تولدی",
    "متشکل از دو رقم",
    "کد پایین",
    "حروفی",
    "تکرار پیش شماره",
]


def entropy(core: str) -> float:
    counts = Counter(core)
    total = len(core)
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def feature_row(analysis: Analysis, status: str, block_level: float = 0.0) -> dict:
    row = {
        "code": str(analysis.code),
        "status": status or "UNKNOWN",
        "primary_type": analysis.primary,
        "block_level": block_level,
        "trailing_zeros": analysis.trailing_zeros,
        "unique_digits": analysis.unique_digits,
        "max_run": analysis.max_run,
        "mirror_pairs": analysis.mirror_pairs,
        "sequential_len": analysis.sequential_len,
        "sequential_reversed": analysis.sequential_reversed,
        "n_types": len(analysis.types),
        "entropy": round(entropy(analysis.core), 4),
        "is_ordinary": int(analysis.is_ordinary),
    }
    present = set(analysis.types)
    for name in PATTERN_FLAGS:
        row[f"pat_{name}"] = int(name in present)
    return row


class BlockStats:
    """Smoothed log-price level of each 3-digit block. Unknown blocks use the market median."""

    def __init__(self):
        self.global_level = 0.0
        self.levels: dict[str, float] = {}

    def fit(self, blocks: list[str], prices: np.ndarray) -> "BlockStats":
        logs = np.log1p(prices)
        self.global_level = float(np.median(logs))
        grouped: dict[str, list[float]] = defaultdict(list)
        for block, value in zip(blocks, logs):
            grouped[str(block)].append(float(value))
        self.levels = {}
        for block, values in grouped.items():
            median = float(np.median(values))
            count = len(values)
            self.levels[block] = (count * median + 12 * self.global_level) / (count + 12)
        return self

    def value(self, block: str) -> float:
        return self.levels.get(str(block), self.global_level)


class CategoryEncoder:
    """Stable integer codes for categorical columns. Unknown values get their own bin."""

    def __init__(self):
        self.maps: dict[str, dict[str, int]] = {}

    def fit(self, frame: pd.DataFrame) -> "CategoryEncoder":
        for column in CATEGORICAL:
            values = sorted(set(frame[column].astype(str)))
            self.maps[column] = {value: index for index, value in enumerate(values)}
        return self

    def transform(self, frame: pd.DataFrame) -> pd.DataFrame:
        out = frame.copy()
        for column, mapping in self.maps.items():
            unknown = len(mapping)
            out[column] = [mapping.get(str(value), unknown) for value in frame[column]]
        return out


def feature_frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


@dataclass
class Listing:
    number: str
    price: int
    status: str
    code: int
    block3: str
    block4: str
    middle4: str
    trailing_zeros: int
    primary: str
    types: tuple[str, ...]
    unique_digits: int
    max_run: int


def pricing_name(primary: str) -> str:
    if SPECIFICITY.get(primary, 100) <= STRONG_RANK:
        return primary
    return "معمولی"


# A pattern is allowed to set the price only when the market actually pays
# for it. The cutoff is a mined multiple of the ordinary line in the same
# code, not the catalog order. Three-step is common and cheap; a repeated
# pair at the tail is rarer and much more expensive, so the pair wins.
MIN_PATTERN_PREMIUM = 1.8
MIN_PATTERN_COUNT = 8


def choose_price_pattern(analysis: Analysis, premiums: dict) -> str:
    """Highest mined coefficient among the patterns this number actually has."""
    best_name = "معمولی"
    best_premium = 1.0
    for name in analysis.types:
        row = premiums.get(f"{analysis.code}|{name}") or {}
        if row.get("count", 0) < MIN_PATTERN_COUNT:
            continue
        premium = row.get("premium") or 0
        if premium > best_premium:
            best_premium = premium
            best_name = name
    if best_premium < MIN_PATTERN_PREMIUM:
        return pricing_name(analysis.primary)
    return best_name


def _middle_weight(middle: str) -> int:
    unique = len(set(middle))
    if unique <= 2 or middle == middle[::-1]:
        return 10
    return 4


# A zero line and a used line in the same block are not the same sale.
# The gap is large enough that a moderately close same-status ad outranks
# an almost-identical ad in a different condition.
_STATUS_GAP = {
    frozenset({"USED", "LIKE_NEW"}): 10.0,
    frozenset({"USED", "BRAND_NEW_WITHOUT_NAME"}): 14.0,
    frozenset({"USED", "BRAND_NEW_WITH_NAME"}): 16.0,
    frozenset({"LIKE_NEW", "BRAND_NEW_WITHOUT_NAME"}): 6.0,
    frozenset({"LIKE_NEW", "BRAND_NEW_WITH_NAME"}): 8.0,
    frozenset({"BRAND_NEW_WITHOUT_NAME", "BRAND_NEW_WITH_NAME"}): 6.0,
}


def status_gap(left: str, right: str) -> float:
    if not left or not right or left == right:
        return 0.0
    return _STATUS_GAP.get(frozenset({left, right}), 24.0)


def _carries(listing: Listing, pattern: str) -> bool:
    return listing.primary == pattern or pattern in listing.types


def distance(query: Analysis, listing: Listing, status: str = "", price_class: str = "") -> float:
    if query.number == listing.number:
        return 0.0
    score = status_gap(status, listing.status)
    kind = price_class or pricing_name(query.primary)
    if kind != "معمولی":
        same_strong = True
        if not _carries(listing, kind):
            score += 90
    else:
        query_price_class = pricing_name(query.primary)
        listing_price_class = pricing_name(listing.primary)
        same_strong = (
            query_price_class == listing_price_class and query_price_class != "معمولی"
        )
        if query_price_class != listing_price_class:
            if "معمولی" in (query_price_class, listing_price_class):
                score += 80
            else:
                score += 120
    score += abs(query.trailing_zeros - listing.trailing_zeros) * 50
    same_zero_tail = (
        query.trailing_zeros >= 2 and query.trailing_zeros == listing.trailing_zeros
    )
    if query.block3 != listing.block3:
        if same_strong or same_zero_tail:
            score += 28
        else:
            score += 62
    elif query.block4 != listing.block4:
        score += 16
    mismatches = sum(a != b for a, b in zip(query.middle4, listing.middle4))
    score += mismatches * max(_middle_weight(query.middle4), _middle_weight(listing.middle4))
    score += abs(query.unique_digits - listing.unique_digits) * 5
    score += abs(query.max_run - listing.max_run) * 6
    return score or 1.0


class MarketIndex:
    def __init__(self, listings: list[Listing]):
        self.listings = listings
        self.by_number: dict[str, list[Listing]] = defaultdict(list)
        self.by_code_block: dict[tuple[int, str], list[Listing]] = defaultdict(list)
        self.by_code_pattern: dict[tuple[int, str], list[Listing]] = defaultdict(list)
        self.by_code_zeros: dict[tuple[int, int], list[Listing]] = defaultdict(list)
        for listing in listings:
            self.by_number[listing.number].append(listing)
            self.by_code_block[(listing.code, listing.block3)].append(listing)
            for name in listing.types or (listing.primary,):
                self.by_code_pattern[(listing.code, name)].append(listing)
            self.by_code_zeros[(listing.code, listing.trailing_zeros)].append(listing)

    def candidates(self, query: Analysis, limit: int = 500, price_class: str = "") -> list[Listing]:
        pools = [self.by_code_block.get((query.code, query.block3), [])]
        kind = price_class or pricing_name(query.primary)
        if kind != "معمولی":
            pools.append(self.by_code_pattern.get((query.code, kind), []))
        if query.trailing_zeros >= 2:
            pools.append(self.by_code_zeros.get((query.code, query.trailing_zeros), []))
        seen: set[int] = set()
        chosen: list[Listing] = []
        for pool in pools:
            for listing in pool:
                marker = id(listing)
                if marker in seen:
                    continue
                seen.add(marker)
                chosen.append(listing)
                if len(chosen) >= limit:
                    return chosen
        return chosen

    def nearest(
        self,
        query: Analysis,
        k: int = 12,
        status: str = "",
        price_class: str = "",
    ) -> list[tuple[float, Listing]]:
        kind = price_class or pricing_name(query.primary)
        scored = [
            (distance(query, listing, status, kind), listing)
            for listing in self.candidates(query, price_class=kind)
        ]
        scored.sort(key=lambda item: (item[0], item[1].price, item[1].number))
        return scored[:k]


def trim_comps(
    scored: list[tuple[float, Listing]],
    limit: int = 8,
) -> list[tuple[float, Listing]]:
    """Keep the nearest ads and drop a price that is far from that neighborhood."""
    pool = list(scored[:limit])
    if len(pool) < 4:
        return pool
    anchor = float(np.median([listing.price for _, listing in pool[:5]]))
    kept = [
        item
        for item in pool
        if anchor / 2.2 <= item[1].price <= anchor * 2.2
    ]
    return kept if len(kept) >= 3 else pool[:5]


def closeness_weights(scored: list[tuple[float, Listing]]) -> list[tuple[float, float]]:
    """Closer ads count for more, but not so much that one listing sets the price."""
    return [(listing.price, 1.0 / (1.0 + dist) ** 1.4) for dist, listing in scored]


def local_comps(
    analysis: Analysis,
    neighbors: list[tuple[float, Listing]],
    status: str,
    blend_gap: float,
    price_class: str = "",
) -> list[tuple[float, Listing]]:
    """Same-condition ads that can actually price this number.

    Ordinary lines stay inside their 3-digit block. A paid pattern may look
    across blocks, but only at the same condition and the same pattern.
    """
    kind = price_class or pricing_name(analysis.primary)
    ordinary = kind == "معمولی"
    chosen = []
    for dist, listing in neighbors:
        if listing.status != status:
            continue
        if ordinary:
            if listing.block3 != analysis.block3 or dist > 48:
                continue
        elif not _carries(listing, kind) or dist > blend_gap:
            continue
        chosen.append((dist, listing))
    if not ordinary:
        same_label = [item for item in chosen if item[1].primary == kind]
        if len(same_label) >= 3:
            return same_label
    return chosen


def weighted_median(pairs: list[tuple[float, float]]) -> float:
    ordered = sorted(pairs, key=lambda item: item[0])
    total = sum(weight for _, weight in ordered)
    if total <= 0:
        return ordered[len(ordered) // 2][0]
    walked = 0.0
    for price, weight in ordered:
        walked += weight
        if walked >= total / 2:
            return price
    return ordered[-1][0]


def _predict(model, frame: pd.DataFrame) -> np.ndarray:
    return np.expm1(model.predict(frame))


def pattern_premiums(listings: list[Listing]) -> dict:
    """Median asking price of each rond class inside each code, versus ordinary lines."""
    ordinary: dict[int, list[int]] = defaultdict(list)
    grouped: dict[tuple[int, str], list[int]] = defaultdict(list)
    for listing in listings:
        grouped[(listing.code, listing.primary)].append(listing.price)
        if listing.primary == "معمولی":
            ordinary[listing.code].append(listing.price)
    report = {}
    for (code, pattern), prices in grouped.items():
        base_prices = ordinary.get(code) or []
        base = float(np.median(base_prices)) if base_prices else None
        median = float(np.median(prices))
        report[f"{code}|{pattern}"] = {
            "code": code,
            "pattern": pattern,
            "count": len(prices),
            "median": int(median),
            "ordinary_median": int(base) if base else None,
            "premium": round(median / base, 2) if base else None,
        }
    return report


def _mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    denom = np.maximum(y_true, 1)
    return float(np.median(np.abs(y_pred - y_true) / denom))


def _with_block_level(frame: pd.DataFrame, blocks: list[str], stats: BlockStats) -> pd.DataFrame:
    out = frame.copy()
    out["block_level"] = [stats.value(block) for block in blocks]
    return out


def train_from_frame(frame: pd.DataFrame, prices: np.ndarray, blocks: list[str]) -> dict:
    indices = np.arange(len(frame))
    train_idx, test_idx = train_test_split(indices, test_size=0.2, random_state=42)

    holdout_stats = BlockStats().fit(
        [blocks[i] for i in train_idx], prices[train_idx]
    )
    holdout_frame = _with_block_level(frame, blocks, holdout_stats)
    encoder = CategoryEncoder().fit(holdout_frame.iloc[train_idx])
    encoded = encoder.transform(holdout_frame)
    cat_idx = [encoded.columns.get_loc(column) for column in CATEGORICAL]
    model = _new_model(cat_idx)
    model.fit(encoded.iloc[train_idx], np.log1p(prices[train_idx]))
    holdout_pred = _predict(model, encoded.iloc[test_idx])
    metrics = {
        "holdout_median_ape": round(_mape(prices[test_idx], holdout_pred), 4),
        "holdout_rows": int(len(test_idx)),
        "train_rows": int(len(train_idx)),
    }

    final_stats = BlockStats().fit(blocks, prices)
    final_frame = _with_block_level(frame, blocks, final_stats)
    final_encoder = CategoryEncoder().fit(final_frame)
    final_encoded = final_encoder.transform(final_frame)
    final = _new_model(cat_idx)
    final.fit(final_encoded, np.log1p(prices))
    return {
        "model": final,
        "encoder": final_encoder,
        "block_stats": final_stats,
        "metrics": metrics,
    }


def _new_model(categorical_index: list[int]) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        loss="squared_error",
        learning_rate=0.06,
        max_iter=350,
        max_depth=8,
        min_samples_leaf=20,
        l2_regularization=0.15,
        categorical_features=categorical_index,
        random_state=42,
    )


@dataclass
class Engine:
    model: HistGradientBoostingRegressor
    encoder: CategoryEncoder
    block_stats: BlockStats
    index: MarketIndex
    premiums: dict
    metrics: dict
    columns: list[str]
    blend_gap: float = 55.0
    blend_weight: float = 0.72

    def predict_price(self, analysis: Analysis, status: str) -> float:
        frame = feature_frame(
            [feature_row(analysis, status, self.block_stats.value(analysis.block3))]
        )
        frame = frame.reindex(columns=self.columns)
        encoded = self.encoder.transform(frame)
        return float(_predict(self.model, encoded)[0])

    def estimate(self, raw: str, status: str = "LIKE_NEW") -> dict:
        analysis = detect(raw)
        if analysis is None:
            return {"error": "شماره باید ۱۱ رقم و با ۰۹ شروع شود."}
        if not analysis.number.startswith("0912"):
            return {"error": "این نسخه روی پیش‌شماره ۰۹۱۲ آموزش دیده است."}

        model_price = max(self.predict_price(analysis, status), 0)
        kind = choose_price_pattern(analysis, self.premiums)
        exact = [
            listing
            for listing in self.index.by_number.get(analysis.number, [])
            if listing.price > 0
        ]
        neighbors = self.index.nearest(analysis, k=48, status=status, price_class=kind)
        tight = [(dist, listing) for dist, listing in neighbors if dist <= self.blend_gap]
        local = local_comps(analysis, neighbors, status, self.blend_gap, kind)
        # An exact listing is a market fact, not a neighbor to be diluted.
        if exact:
            anchor = float(np.median([listing.price for listing in exact]))
            price = 0.85 * anchor + 0.15 * model_price
            source = "آگهی همین شماره"
            used = [(0.0, listing) for listing in exact[:5]]
        elif len(local) >= 3:
            priced = trim_comps(local)
            comp_price = weighted_median(closeness_weights(priced))
            blend = 0.94 if priced[0][0] <= 18 else 0.84
            price = blend * comp_price + (1 - blend) * model_price
            source = "آگهی‌های هم‌وضعیت"
            used = priced[:6]
        elif len(tight) >= 4:
            tight = trim_comps(tight)
            comp_price = weighted_median(closeness_weights(tight))
            # Very close listings are the market. The model only fills gaps.
            weight = 0.9 if tight[0][0] <= 25 else self.blend_weight
            price = weight * comp_price + (1 - weight) * model_price
            source = "میانگین وزنی آگهی‌های هم‌الگو"
            used = tight[:6]
        elif tight:
            comp_price = float(np.median([listing.price for _, listing in tight]))
            price = 0.45 * comp_price + 0.55 * model_price
            source = "ترکیب مدل و چند آگهی نزدیک"
            used = tight[:6]
        else:
            price = model_price
            source = "مدل یادگیری‌شده از کل بازار"
            used = neighbors[:5]

        agreement = 1.0
        if used:
            comp_mid = float(np.median([listing.price for _, listing in used]))
            agreement = 1 - min(abs(comp_mid - model_price) / max(comp_mid, 1), 1)
        best = used[0][0] if used else 999
        if exact or (best <= 20 and agreement > 0.75 and len(tight) >= 4):
            confidence = "بالا"
        elif best <= self.blend_gap and agreement > 0.55:
            confidence = "متوسط"
        else:
            confidence = "پایین"

        key = f"{analysis.code}|{analysis.primary}"
        premium = self.premiums.get(key)
        shown_types = list(analysis.types or ["معمولی"])
        if kind != "معمولی" and kind in shown_types:
            shown_types = [kind] + [name for name in shown_types if name != kind]
        factors = []
        for name in shown_types:
            row = self.premiums.get(f"{analysis.code}|{name}") or {}
            multiplier = row.get("premium") if row.get("count", 0) >= MIN_PATTERN_COUNT else None
            factors.append({"name": name, "premium": multiplier})
        samples = []
        for dist, listing in used:
            samples.append(
                {
                    "number": listing.number,
                    "price": listing.price,
                    "status": listing.status,
                    "primary": listing.primary,
                    "distance": round(dist, 1),
                    "block3": listing.block3,
                    "trailing_zeros": listing.trailing_zeros,
                }
            )
        quoted = round_quote(price)
        return {
            "number": analysis.number,
            "status": status,
            "price": quoted,
            "deal_price": round_quote(quoted * 0.9),
            "model_price": int(round(model_price)),
            "source": source,
            "confidence": confidence,
            "primary": analysis.primary,
            "price_pattern": kind,
            "types": shown_types,
            "factors": factors,
            "notes": analysis.notes,
            "block3": analysis.block3,
            "middle4": analysis.middle4,
            "trailing_zeros": analysis.trailing_zeros,
            "code": analysis.code,
            "premium": premium,
            "samples": samples,
            "metrics": self.metrics,
        }

    def save(self, path: Path = MODEL_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "model": self.model,
                "encoder": self.encoder,
                "block_stats": self.block_stats,
                "columns": self.columns,
                "premiums": self.premiums,
                "metrics": self.metrics,
                "blend_gap": self.blend_gap,
                "blend_weight": self.blend_weight,
            },
            path,
        )


def round_quote(value: float, step: int = QUOTE_STEP) -> int:
    """Nearest public quote. Halfway rounds away from zero, up to the step."""
    amount = int(round(value))
    return ((amount + step // 2) // step) * step


def listings_from_rows(rows: list[dict]) -> list[Listing]:
    listings = []
    for row in rows:
        analysis = detect(row["number"])
        if analysis is None:
            continue
        price = int(row["price"] or 0)
        if price < PRICE_MIN or price > PRICE_MAX:
            continue
        listings.append(
            Listing(
                number=analysis.number,
                price=price,
                status=row.get("status") or "UNKNOWN",
                code=analysis.code,
                block3=analysis.block3,
                block4=analysis.block4,
                middle4=analysis.middle4,
                trailing_zeros=analysis.trailing_zeros,
                primary=analysis.primary,
                types=tuple(analysis.types),
                unique_digits=analysis.unique_digits,
                max_run=analysis.max_run,
            )
        )
    return listings


def build_engine(rows: list[dict]) -> Engine:
    listings = listings_from_rows(rows)
    if len(listings) < 50:
        raise RuntimeError(f"not enough priced listings: {len(listings)}")
    blocks = [item.block3 for item in listings]
    frame = feature_frame(
        [feature_row(detect(item.number), item.status) for item in listings]
    )
    prices = np.array([item.price for item in listings], dtype=float)
    trained = train_from_frame(frame, prices, blocks)
    premiums = pattern_premiums(listings)
    return Engine(
        model=trained["model"],
        encoder=trained["encoder"],
        block_stats=trained["block_stats"],
        index=MarketIndex(listings),
        premiums=premiums,
        metrics={**trained["metrics"], "listings": len(listings)},
        columns=list(frame.columns),
    )


def save_listings(listings: list[Listing], path: Path = DB_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE listings (
            number TEXT PRIMARY KEY,
            price INTEGER,
            status TEXT,
            code INTEGER,
            block3 TEXT,
            block4 TEXT,
            middle4 TEXT,
            trailing_zeros INTEGER,
            primary_type TEXT,
            types TEXT,
            unique_digits INTEGER,
            max_run INTEGER
        )
        """
    )
    # Keep the latest price if the same number was listed more than once.
    deduped: dict[str, Listing] = {}
    for listing in listings:
        deduped[listing.number] = listing
    conn.executemany(
        """
        INSERT INTO listings VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        [
            (
                item.number,
                item.price,
                item.status,
                item.code,
                item.block3,
                item.block4,
                item.middle4,
                item.trailing_zeros,
                item.primary,
                ",".join(item.types),
                item.unique_digits,
                item.max_run,
            )
            for item in deduped.values()
        ],
    )
    conn.commit()
    conn.close()


def load_listings(path: Path = DB_PATH) -> list[Listing]:
    conn = sqlite3.connect(path)
    rows = conn.execute(
        """
        SELECT number, price, status, code, block3, block4, middle4,
               trailing_zeros, primary_type, types, unique_digits, max_run
        FROM listings
        """
    ).fetchall()
    conn.close()
    return [
        Listing(
            number=row[0],
            price=row[1],
            status=row[2],
            code=row[3],
            block3=row[4],
            block4=row[5],
            middle4=row[6],
            trailing_zeros=row[7],
            primary=row[8],
            types=tuple(part for part in (row[9] or "").split(",") if part),
            unique_digits=row[10],
            max_run=row[11],
        )
        for row in rows
    ]


def load_engine(model_path: Path = MODEL_PATH, db_path: Path = DB_PATH) -> Engine:
    blob = joblib.load(model_path)
    return Engine(
        model=blob["model"],
        encoder=blob["encoder"],
        block_stats=blob["block_stats"],
        index=MarketIndex(load_listings(db_path)),
        premiums=blob["premiums"],
        metrics=blob["metrics"],
        columns=blob["columns"],
        blend_gap=blob.get("blend_gap", 55.0),
        blend_weight=blob.get("blend_weight", 0.72),
    )


def premiums_public(premiums: dict) -> list[dict]:
    rows = [row for row in premiums.values() if row["count"] >= 15 and row["premium"]]
    rows.sort(key=lambda row: (-(row["premium"] or 0), row["code"]))
    return rows


def dump_metrics(engine: Engine, path: Path | None = None) -> None:
    payload = {
        "metrics": engine.metrics,
        "top_premiums": premiums_public(engine.premiums)[:40],
    }
    target = path or (DATA / "metrics.json")
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
