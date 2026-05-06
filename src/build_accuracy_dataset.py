"""
Build the unified MVP dataset for prediction-market accuracy analysis.

Inputs are the platform-specific cleaned files and cached raw history files.
The output is data/cleaned/accuracy_markets.csv, one row per liquid resolved
binary sports/elections market with a pre-resolution YES probability.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.accuracy import (
    MIN_VOLUME,
    apply_mvp_filters,
    classify_category,
    last_non_trivial_probability,
    load_json,
    normalize_probability,
    normalize_resolution,
    to_float,
)

RAW_DIR = ROOT / "data" / "raw"
CLEAN_DIR = ROOT / "data" / "cleaned"
POLYMARKET_MARKETS_CSV = CLEAN_DIR / "polymarket_markets.csv"
KALSHI_MARKETS_CSV = CLEAN_DIR / "markets.csv"
OUTPUT_CSV = CLEAN_DIR / "accuracy_markets.csv"


def polymarket_rows() -> list[dict]:
    if not POLYMARKET_MARKETS_CSV.exists():
        return []
    markets = pd.read_csv(POLYMARKET_MARKETS_CSV)
    markets["volume"] = pd.to_numeric(markets["volume"], errors="coerce")
    markets = markets[
        markets["category"].astype(str).str.lower().isin({"sports", "elections"})
        & (markets["volume"] >= MIN_VOLUME)
        & markets["resolution"].astype(str).str.upper().isin({"YES", "NO"})
    ]
    rows = []
    for _, row in markets.iterrows():
        forecast = normalize_probability(row.get("closing_prob"))
        if forecast is None:
            history_path = RAW_DIR / "polymarket" / "history" / f"{row.get('yes_token_id')}.json"
            if history_path.exists():
                forecast = last_non_trivial_probability(load_json(history_path), ("p",))
        rows.append(
            {
                "platform": "polymarket",
                "market_id": str(row.get("id", "")),
                "title": row.get("question") or row.get("event_title"),
                "category": str(row.get("category", "")).lower(),
                "open_time": row.get("start_date"),
                "close_time": row.get("end_date"),
                "resolution": normalize_resolution(row.get("resolution")),
                "forecast_prob": forecast,
                "forecast_source": "history" if forecast is not None else None,
                "volume": to_float(row.get("volume")),
            }
        )
    return rows


def kalshi_volume(market: dict) -> float | None:
    for key in ("volume", "volume_dollars", "volume_fp"):
        volume = to_float(market.get(key))
        if volume is not None:
            return volume
    return None


def kalshi_category(market: dict) -> str | None:
    category = str(market.get("category") or "").lower()
    if category in {"sports", "elections"}:
        return category
    return classify_category(
        " ".join(
            str(market.get(key) or "")
            for key in ("title", "subtitle", "event_ticker", "series_ticker", "ticker")
        )
    )


def iter_cached_kalshi_markets():
    for path in sorted(list(RAW_DIR.glob("markets_*.json")) + list(RAW_DIR.glob("historical_markets_*.json"))):
        data = load_json(path)
        for market in data.get("markets", []):
            yield market


def fetch_kalshi_history(ticker: str, historical: bool = False) -> list[dict]:
    import kalshi_client as kalshi

    prefix = "/historical" if historical else ""
    entries = []
    cursor = None
    while True:
        params = {"limit": 1000}
        if cursor:
            params["cursor"] = cursor
        data = kalshi.get(f"{prefix}/markets/{ticker}/history", params)
        batch = data.get("history", [])
        entries.extend(batch)
        cursor = data.get("cursor")
        if not cursor or not batch:
            break
        time.sleep(0.1)
    return entries


def kalshi_snapshot_probability(market: dict) -> float | None:
    """
    Best-effort fallback when full history is unavailable.

    Historical candlesticks are preferred, but the cached settled-market snapshot
    sometimes still carries the final non-trivial price in the previous-price fields.
    """
    candidates: list[float] = []
    for key in (
        "previous_price_dollars",
        "previous_yes_bid_dollars",
        "previous_yes_ask_dollars",
        "last_price_dollars",
        "yes_bid_dollars",
        "yes_ask_dollars",
    ):
        p = normalize_probability(market.get(key))
        if p is not None:
            candidates.append(p)
    for p in candidates:
        if 0.02 <= p <= 0.98:
            return p
    return None


def kalshi_forecast(market: dict, fetch_missing_history: bool = False) -> tuple[float | None, str | None]:
    ticker = market.get("ticker")
    if not ticker:
        return None, None
    history_path = RAW_DIR / "history" / f"{ticker}.json"
    if history_path.exists():
        entries = load_json(history_path)
        forecast = last_non_trivial_probability(entries)
        return forecast, "history" if forecast is not None else None
    if fetch_missing_history:
        historical = bool(market.get("settlement_ts"))
        entries = fetch_kalshi_history(ticker, historical=historical)
        history_path.parent.mkdir(parents=True, exist_ok=True)
        with history_path.open("w") as f:
            json.dump(entries, f)
        forecast = last_non_trivial_probability(entries)
        return forecast, "history" if forecast is not None else None
    forecast = kalshi_snapshot_probability(market)
    return forecast, "snapshot_fallback" if forecast is not None else None


def kalshi_rows(fetch_missing_history: bool = False) -> list[dict]:
    rows = []
    seen_ids: set[str] = set()

    source_iter = iter_cached_kalshi_markets()
    if KALSHI_MARKETS_CSV.exists():
        markets_df = pd.read_csv(KALSHI_MARKETS_CSV)
        fallback_records = markets_df.to_dict("records")
    else:
        fallback_records = []

    for market in source_iter:
        resolution = normalize_resolution(market.get("result"))
        category = kalshi_category(market)
        if resolution is None or category is None:
            continue
        forecast_prob, forecast_source = kalshi_forecast(market, fetch_missing_history)
        market_id = str(market.get("ticker", ""))
        if market_id in seen_ids:
            continue
        seen_ids.add(market_id)
        rows.append(
            {
                "platform": "kalshi",
                "market_id": market_id,
                "title": market.get("title"),
                "category": category,
                "open_time": market.get("open_time") or market.get("created_time"),
                "close_time": market.get("close_time") or market.get("settlement_ts"),
                "resolution": resolution,
                "forecast_prob": forecast_prob,
                "forecast_source": forecast_source,
                "volume": kalshi_volume(market),
            }
        )

    for market in fallback_records:
        market_id = str(market.get("ticker", ""))
        if market_id in seen_ids:
            continue
        resolution = normalize_resolution(market.get("result"))
        category = kalshi_category(market)
        if resolution is None or category is None:
            continue
        forecast_prob, forecast_source = kalshi_forecast(market, fetch_missing_history)
        rows.append(
            {
                "platform": "kalshi",
                "market_id": market_id,
                "title": market.get("title"),
                "category": category,
                "open_time": market.get("open_time") or market.get("created_time"),
                "close_time": market.get("close_time") or market.get("settlement_ts"),
                "resolution": resolution,
                "forecast_prob": forecast_prob,
                "forecast_source": forecast_source,
                "volume": kalshi_volume(market),
            }
        )
    return rows


def build_dataset(fetch_missing_kalshi_history: bool = False, min_volume: float = MIN_VOLUME) -> pd.DataFrame:
    rows = polymarket_rows() + kalshi_rows(fetch_missing_kalshi_history)
    df = pd.DataFrame(
        rows,
        columns=[
            "platform", "market_id", "title", "category", "open_time", "close_time",
            "resolution", "forecast_prob", "forecast_source", "volume",
        ],
    )
    return apply_mvp_filters(df, min_volume=min_volume)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-volume", type=float, default=MIN_VOLUME)
    parser.add_argument(
        "--fetch-missing-kalshi-history",
        action="store_true",
        help="Fetch Kalshi histories not already cached. This can take a while.",
    )
    args = parser.parse_args()

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    df = build_dataset(
        fetch_missing_kalshi_history=args.fetch_missing_kalshi_history,
        min_volume=args.min_volume,
    )
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"Wrote {len(df)} rows to {OUTPUT_CSV}")
    if not df.empty:
        print(df.groupby(["platform", "category"]).size().to_string())


if __name__ == "__main__":
    main()
