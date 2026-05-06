from __future__ import annotations

import pandas as pd

from src.settings import CLEAN_DIR
from src.supabase_storage import SupabaseWarehouseClient, dataframe_records
from src.warehouse_pipeline import score_markets


def main() -> None:
    normalized_path = CLEAN_DIR / "normalized_markets.csv"
    normalized = pd.read_csv(normalized_path) if normalized_path.exists() else pd.DataFrame()
    scored = score_markets(normalized)
    scored.to_csv(CLEAN_DIR / "scored_markets.csv", index=False)

    client = SupabaseWarehouseClient()
    if client.enabled:
        client.upsert_rows("scored_markets", dataframe_records(scored), on_conflict="platform,source_market_id")

    print(f"Wrote {len(scored)} scored markets")


if __name__ == "__main__":
    main()
