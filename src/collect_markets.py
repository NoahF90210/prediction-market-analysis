import json
import os
import sys
import time

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kalshi_client as kalshi
from src.accuracy import normalize_resolution, to_float
from src.category_mapping import classify_market
RAW_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw")
CLEAN_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cleaned")


def find_resume_point() -> tuple[int, str | None]:
    """Return (next_page, cursor) by scanning already-saved raw pages."""
    page = 0
    while True:
        raw_path = os.path.join(RAW_DIR, f"markets_{page:04d}.json")
        if not os.path.exists(raw_path):
            break
        with open(raw_path) as f:
            data = json.load(f)
        cursor = data.get("cursor")
        page += 1
        if not cursor:
            break
    if page > 0:
        print(f"  Resuming from page {page + 1} (found {page} saved pages)")
    return page, cursor


def load_saved_markets() -> list[dict]:
    """Load all markets from already-saved raw pages."""
    markets = []
    page = 0
    while True:
        raw_path = os.path.join(RAW_DIR, f"markets_{page:04d}.json")
        if not os.path.exists(raw_path):
            break
        with open(raw_path) as f:
            data = json.load(f)
        markets.extend(data.get("markets", []))
        page += 1
    return markets


def fetch_all_settled() -> list[dict]:
    start_page, cursor = find_resume_point()
    markets = load_saved_markets()
    print(f"  Loaded {len(markets)} markets from {start_page} cached pages")

    page = start_page
    while True:
        params = {"status": "settled", "limit": 200}
        if cursor:
            params["cursor"] = cursor
        data = kalshi.get("/markets", params)
        batch = data.get("markets", [])
        markets.extend(batch)

        raw_path = os.path.join(RAW_DIR, f"markets_{page:04d}.json")
        with open(raw_path, "w") as f:
            json.dump(data, f)

        print(f"  page {page + 1}: {len(batch)} markets (running total: {len(markets)})")
        cursor = data.get("cursor")
        if not cursor or not batch:
            break
        page += 1
        time.sleep(0.15)
    return markets


def fetch_all_historical_settled() -> list[dict]:
    markets = []
    cursor = None
    page = 0
    while True:
        params = {"status": "settled", "limit": 200}
        if cursor:
            params["cursor"] = cursor
        data = kalshi.get("/historical/markets", params)
        batch = data.get("markets", [])
        markets.extend(batch)

        raw_path = os.path.join(RAW_DIR, f"historical_markets_{page:04d}.json")
        with open(raw_path, "w") as f:
            json.dump(data, f)

        print(f"  historical page {page + 1}: {len(batch)} markets")
        cursor = data.get("cursor")
        if not cursor or not batch:
            break
        page += 1
        time.sleep(0.15)
    return markets


def market_category(market: dict) -> str | None:
    return classify_market(
        platform="kalshi",
        market_id=str(market.get("ticker") or ""),
        title=str(market.get("title") or ""),
        slug=str(market.get("ticker") or ""),
        raw_platform_category=str(market.get("category") or ""),
        raw_tags=[],
        context_fields=[
            str(market.get("subtitle") or ""),
            str(market.get("event_ticker") or ""),
            str(market.get("series_ticker") or ""),
            str(market.get("ticker") or ""),
            str(market.get("rules_primary") or ""),
        ],
    )


def market_volume(market: dict) -> float | None:
    for key in ("volume", "volume_dollars", "volume_fp"):
        volume = to_float(market.get(key))
        if volume is not None:
            return volume
    return None


def normalize(markets: list[dict], min_volume: float | None = None) -> pd.DataFrame:
    rows = []
    for m in markets:
        result = normalize_resolution(m.get("result"))
        if result is None:
            continue
        category = market_category(m)
        volume = market_volume(m)
        if volume is None:
            continue
        if min_volume is not None and volume < min_volume:
            continue
        rows.append({
            "ticker": m.get("ticker", ""),
            "title": m.get("title", ""),
            "category": category.canonical_category,
            "category_source": category.category_source,
            "category_confidence": category.category_confidence,
            "needs_review": category.needs_review,
            "review_reason": category.review_reason,
            "raw_platform_category": category.raw_platform_category,
            "raw_tags": category.raw_tags,
            "series_ticker": m.get("series_ticker", ""),
            "open_time": m.get("open_time", ""),
            "close_time": m.get("close_time", ""),
            "result": result,
            "last_price": m.get("last_price") or m.get("last_price_dollars"),
            "volume": volume,
        })
    return pd.DataFrame(rows)


def main(min_volume: float | None = None, include_historical: bool = True):
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(CLEAN_DIR, exist_ok=True)

    print("Fetching all settled markets...")
    all_markets = fetch_all_settled()
    if include_historical:
        print("Fetching historical settled markets...")
        all_markets.extend(fetch_all_historical_settled())
    print(f"\nTotal raw markets fetched: {len(all_markets)}")

    df = normalize(all_markets, min_volume=min_volume)
    if min_volume is None:
        print(f"Captured full resolved inventory: {len(df)} markets")
    else:
        print(f"After filtering to >=${min_volume:,.0f} volume: {len(df)} markets")
    if not df.empty:
        print(f"Category breakdown:\n{df['category'].value_counts().to_string()}")

    out_path = os.path.join(CLEAN_DIR, "markets.csv")
    df.to_csv(out_path, index=False)
    print(f"\nWrote {len(df)} rows to {out_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-volume", type=float, default=0.0)
    parser.add_argument("--live-only", action="store_true")
    args = parser.parse_args()
    min_volume = None if args.min_volume <= 0 else args.min_volume
    main(min_volume=min_volume, include_historical=not args.live_only)
