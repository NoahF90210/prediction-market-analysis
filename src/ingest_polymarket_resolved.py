from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.collect_polymarket import collect_history, extract_markets, fetch_events
from src.settings import CLEAN_DIR, MIN_ANALYSIS_VOLUME
from src.supabase_storage import SupabaseWarehouseClient, dataframe_records


def build_polymarket_inventory(fetch_history: bool = True) -> pd.DataFrame:
    events = fetch_events(min_volume=MIN_ANALYSIS_VOLUME)
    markets = extract_markets(events)
    if markets.empty:
        return pd.DataFrame()

    if fetch_history:
        markets, _ = collect_history(markets)

    inventory = markets.rename(
        columns={
            "id": "source_market_id",
        }
    ).copy()
    inventory["platform"] = "polymarket"
    inventory["source_event_id"] = inventory.get("slug")
    inventory["title"] = inventory["question"].fillna(inventory["event_title"])
    inventory["open_time"] = inventory["start_date"]
    inventory["close_time"] = inventory["end_date"]
    inventory["forecast_prob"] = inventory["closing_prob"]
    inventory["forecast_source"] = inventory["closing_prob"].map(lambda value: "history" if pd.notna(value) else None)
    inventory["raw_payload"] = "{}"
    inventory["source_url"] = inventory["slug"].map(lambda slug: f"https://polymarket.com/event/{slug}" if slug else None)
    return inventory[
        [
            "platform",
            "source_market_id",
            "event_title",
            "title",
            "slug",
            "source_event_id",
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
    ].copy()


def sync_polymarket_inventory(client: SupabaseWarehouseClient, inventory: pd.DataFrame) -> None:
    if inventory.empty or not client.enabled:
        return
    client.upsert_rows("raw_markets", dataframe_records(inventory), on_conflict="platform,source_market_id")


def main() -> None:
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    inventory = build_polymarket_inventory()
    inventory.to_csv(CLEAN_DIR / "polymarket_resolved_inventory.csv", index=False)
    client = SupabaseWarehouseClient()
    sync_polymarket_inventory(client, inventory)
    print(f"Wrote {len(inventory)} Polymarket resolved markets")
    print(f"Analysis threshold remains ${MIN_ANALYSIS_VOLUME:,.0f}, but raw capture is unfiltered.")


if __name__ == "__main__":
    main()
