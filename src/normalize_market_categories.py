from __future__ import annotations

import pandas as pd

from src.settings import CLEAN_DIR
from src.supabase_storage import SupabaseWarehouseClient, dataframe_records
from src.warehouse_pipeline import build_raw_inventory, normalize_market_inventory


def main() -> None:
    polymarket = pd.read_csv(CLEAN_DIR / "polymarket_resolved_inventory.csv") if (CLEAN_DIR / "polymarket_resolved_inventory.csv").exists() else pd.DataFrame()
    kalshi = pd.read_csv(CLEAN_DIR / "kalshi_resolved_inventory.csv") if (CLEAN_DIR / "kalshi_resolved_inventory.csv").exists() else pd.DataFrame()
    raw_inventory = build_raw_inventory(polymarket, kalshi)
    normalized = normalize_market_inventory(raw_inventory)
    normalized.to_csv(CLEAN_DIR / "normalized_markets.csv", index=False)

    client = SupabaseWarehouseClient()
    if client.enabled:
        client.upsert_rows("normalized_markets", dataframe_records(normalized), on_conflict="platform,source_market_id")

    print(f"Wrote {len(normalized)} normalized markets")


if __name__ == "__main__":
    main()
