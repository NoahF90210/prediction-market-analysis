from __future__ import annotations

import pandas as pd

from src.collect_markets import fetch_all_historical_settled, fetch_all_settled
from src.kalshi_forecasts import kalshi_forecast, kalshi_volume
from src.settings import CLEAN_DIR, MIN_ANALYSIS_VOLUME
from src.supabase_storage import SupabaseWarehouseClient, dataframe_records


def build_kalshi_inventory(include_historical: bool = True) -> pd.DataFrame:
    markets = fetch_all_settled()
    if include_historical:
        markets.extend(fetch_all_historical_settled())

    rows: list[dict] = []
    for market in markets:
        market_id = str(market.get("ticker") or "")
        if not market_id:
            continue
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
                "resolution": market.get("result"),
                "forecast_prob": forecast_prob,
                "forecast_source": forecast_source,
                "volume": kalshi_volume(market),
                "source_url": f"https://kalshi.com/markets/{market_id.lower()}" if market_id else None,
                "raw_payload": market,
            }
        )

    inventory = pd.DataFrame(rows)
    return inventory.drop_duplicates(subset=["platform", "source_market_id"]).reset_index(drop=True)


def sync_kalshi_inventory(client: SupabaseWarehouseClient, inventory: pd.DataFrame) -> None:
    if inventory.empty or not client.enabled:
        return
    client.upsert_rows("raw_markets", dataframe_records(inventory), on_conflict="platform,source_market_id")


def main() -> None:
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    inventory = build_kalshi_inventory()
    inventory.to_csv(CLEAN_DIR / "kalshi_resolved_inventory.csv", index=False)
    client = SupabaseWarehouseClient()
    sync_kalshi_inventory(client, inventory)
    print(f"Wrote {len(inventory)} Kalshi resolved markets")
    print(f"Analysis threshold remains ${MIN_ANALYSIS_VOLUME:,.0f}, but raw capture is unfiltered.")


if __name__ == "__main__":
    main()
