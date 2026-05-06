from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.accuracy import normalize_probability, normalize_resolution
from src.collect_polymarket import extract_markets
from src.kalshi_forecasts import kalshi_forecast, kalshi_volume
from src.settings import CLEAN_DIR, OUTPUT_MARKETS_CSV, OUTPUT_REVIEW_QUEUE_CSV, OUTPUT_SCORED_CSV, RAW_DIR
from src.warehouse_pipeline import build_dashboard_export, build_raw_inventory, build_review_queue, normalize_market_inventory, score_markets


def _load_json(path: Path):
    with path.open() as f:
        return json.load(f)


def cached_polymarket_inventory() -> pd.DataFrame:
    events: list[dict] = []
    for path in sorted((RAW_DIR / "polymarket").glob("events_*.json")):
        try:
            batch = _load_json(path)
        except json.JSONDecodeError:
            continue
        if isinstance(batch, list):
            events.extend(batch)

    if not events:
        return pd.DataFrame()

    markets = extract_markets(events).rename(columns={"id": "source_market_id"}).copy()
    markets["platform"] = "polymarket"
    markets["source_event_id"] = markets.get("slug")
    markets["title"] = markets["question"].fillna(markets["event_title"])
    markets["open_time"] = markets["start_date"]
    markets["close_time"] = markets["end_date"]
    markets["forecast_prob"] = markets.get("closing_prob").map(normalize_probability)
    markets["forecast_source"] = markets["forecast_prob"].map(lambda value: "history" if pd.notna(value) else None)
    markets["source_url"] = markets["slug"].map(lambda slug: f"https://polymarket.com/event/{slug}" if slug else None)
    markets["raw_payload"] = "{}"
    return markets[
        [
            "platform",
            "source_market_id",
            "source_event_id",
            "event_title",
            "title",
            "slug",
            "raw_platform_category",
            "raw_tags",
            "open_time",
            "close_time",
            "resolution",
            "forecast_prob",
            "forecast_source",
            "volume",
            "source_url",
            "raw_payload",
        ]
    ].drop_duplicates(subset=["platform", "source_market_id"])


def cached_kalshi_inventory() -> pd.DataFrame:
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    raw_paths = sorted(RAW_DIR.glob("markets_*.json")) + sorted(RAW_DIR.glob("historical_markets_*.json"))
    for path in raw_paths:
        try:
            payload = _load_json(path)
        except json.JSONDecodeError:
            continue
        for market in payload.get("markets", []):
            market_id = str(market.get("ticker") or "")
            key = ("kalshi", market_id)
            if not market_id or key in seen:
                continue
            seen.add(key)
            forecast_prob, forecast_source = kalshi_forecast(market, fetch_missing_history=False)
            rows.append(
                {
                    "platform": "kalshi",
                    "source_market_id": market_id,
                    "source_event_id": market.get("event_ticker") or market.get("series_ticker") or market_id,
                    "event_title": market.get("title"),
                    "title": market.get("title"),
                    "slug": market_id,
                    "raw_platform_category": str(market.get("category") or ""),
                    "raw_tags": "[]",
                    "series_ticker": market.get("series_ticker"),
                    "event_ticker": market.get("event_ticker"),
                    "subtitle": market.get("subtitle"),
                    "rules_primary": market.get("rules_primary"),
                    "open_time": market.get("open_time") or market.get("created_time"),
                    "close_time": market.get("close_time") or market.get("settlement_ts"),
                    "resolution": normalize_resolution(market.get("result")),
                    "forecast_prob": forecast_prob,
                    "forecast_source": forecast_source,
                    "volume": kalshi_volume(market),
                    "source_url": f"https://kalshi.com/markets/{market_id.lower()}",
                    "raw_payload": json.dumps(market, ensure_ascii=True),
                }
            )
    return pd.DataFrame(rows).drop_duplicates(subset=["platform", "source_market_id"])


def main() -> None:
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    polymarket = cached_polymarket_inventory()
    kalshi = cached_kalshi_inventory()
    raw_inventory = build_raw_inventory(polymarket, kalshi)
    normalized = normalize_market_inventory(raw_inventory)
    scored = score_markets(normalized)
    dashboard = build_dashboard_export(normalized, scored)
    review_queue = build_review_queue(normalized)

    raw_inventory.to_json(CLEAN_DIR / "raw_markets_backfill.json", orient="records")
    normalized.to_json(CLEAN_DIR / "normalized_markets_backfill.json", orient="records")
    scored.to_json(CLEAN_DIR / "scored_markets_backfill.json", orient="records")
    dashboard.to_csv(OUTPUT_MARKETS_CSV, index=False)
    scored.to_csv(OUTPUT_SCORED_CSV, index=False)
    review_queue.to_csv(OUTPUT_REVIEW_QUEUE_CSV, index=False)

    print(f"raw_markets={len(raw_inventory)}")
    print(f"normalized_markets={len(normalized)}")
    print(f"scored_markets={len(scored)}")


if __name__ == "__main__":
    main()
