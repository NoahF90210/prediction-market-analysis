from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.collect_polymarket import collect_history, extract_markets, fetch_events
from src.forecast_snapshots import SECONDARY_FORECAST_HORIZONS
from src.settings import CLEAN_DIR, MIN_ANALYSIS_VOLUME
from src.supabase_storage import SupabaseWarehouseClient, dataframe_records


def build_polymarket_inventory(fetch_history: bool = True, min_event_volume: float = MIN_ANALYSIS_VOLUME) -> pd.DataFrame:
    events = fetch_events(min_volume=min_event_volume)
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
    if "source_event_id" not in inventory.columns:
        inventory["source_event_id"] = inventory.get("slug")
    inventory["source_event_id"] = inventory["source_event_id"].fillna(inventory.get("slug"))
    inventory["title"] = inventory["question"].fillna(inventory["event_title"])
    inventory["open_time"] = inventory["start_date"]
    inventory["close_time"] = inventory["end_date"]
    inventory["forecast_prob"] = inventory["closing_prob"]
    for col in (
        "forecast_observed_at",
        "forecast_target_time",
        "forecast_seconds_before_close",
        "forecast_horizon",
        "forecast_quality",
    ):
        if col not in inventory.columns:
            inventory[col] = None
    for horizon in SECONDARY_FORECAST_HORIZONS:
        for col in (
            "forecast_prob",
            "forecast_source",
            "forecast_observed_at",
            "forecast_target_time",
            "forecast_seconds_before_close",
            "forecast_horizon",
            "forecast_quality",
        ):
            column_name = f"{col}_{horizon}"
            if column_name not in inventory.columns:
                inventory[column_name] = None
    inventory["raw_payload"] = "{}"
    inventory["source_url"] = inventory["slug"].map(lambda slug: f"https://polymarket.com/event/{slug}" if slug else None)
    columns = [
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
        "forecast_observed_at",
        "forecast_target_time",
        "forecast_seconds_before_close",
        "forecast_horizon",
        "forecast_quality",
    ]
    for horizon in SECONDARY_FORECAST_HORIZONS:
        for col in (
            "forecast_prob",
            "forecast_source",
            "forecast_observed_at",
            "forecast_target_time",
            "forecast_seconds_before_close",
            "forecast_horizon",
            "forecast_quality",
        ):
            columns.append(f"{col}_{horizon}")
    columns.extend(
        [
            "volume",
            "source_url",
            "raw_payload",
        ]
    )
    return inventory[columns].copy()


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
    print(
        f"Fetched closed events using min event volume ${MIN_ANALYSIS_VOLUME:,.0f}. "
        "Market-level scoring filters are applied downstream."
    )


if __name__ == "__main__":
    main()
