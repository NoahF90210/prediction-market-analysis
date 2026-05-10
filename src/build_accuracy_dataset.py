"""
Build the full resolved-market warehouse export used by the local app.

The rebuilt pipeline separates:
1. raw inventory capture
2. category normalization
3. scored analysis-ready markets

All resolved markets are kept in the exported dashboard dataset. The
`$100K` volume threshold is applied only when deciding which rows are
analysis-ready and therefore eligible for scoring.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from src.data_quality import write_quality_outputs
from src.export_dashboard_dataset import main as export_dashboard_main
from src.ingest_kalshi_resolved import build_kalshi_inventory, sync_kalshi_inventory
from src.ingest_polymarket_resolved import build_polymarket_inventory, sync_polymarket_inventory
from src.normalize_market_categories import main as normalize_main
from src.score_markets import main as score_main
from src.settings import CLEAN_DIR, OUTPUT_MARKETS_CSV, OUTPUT_REVIEW_QUEUE_CSV, OUTPUT_SCORED_CSV
from src.supabase_storage import SupabaseWarehouseClient
from src.warehouse_pipeline import build_dashboard_export, build_raw_inventory, build_review_queue, normalize_market_inventory, score_markets


def review_queue(df: pd.DataFrame) -> pd.DataFrame:
    return build_review_queue(df)


def build_dataset() -> pd.DataFrame:
    polymarket = build_polymarket_inventory()
    kalshi = build_kalshi_inventory()

    client = SupabaseWarehouseClient()
    sync_polymarket_inventory(client, polymarket)
    sync_kalshi_inventory(client, kalshi)

    raw_inventory = build_raw_inventory(polymarket, kalshi)
    normalized = normalize_market_inventory(raw_inventory)
    scored = score_markets(normalized)
    dashboard_df = build_dashboard_export(normalized, scored)

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    normalized.to_csv(CLEAN_DIR / "normalized_markets.csv", index=False)
    scored.to_csv(CLEAN_DIR / "scored_markets.csv", index=False)
    dashboard_df.to_csv(OUTPUT_MARKETS_CSV, index=False)
    scored.to_csv(OUTPUT_SCORED_CSV, index=False)
    review_queue(normalized).to_csv(OUTPUT_REVIEW_QUEUE_CSV, index=False)
    write_quality_outputs(scored, normalized=normalized)
    return dashboard_df


def main() -> None:
    df = build_dataset()
    print(f"Wrote {len(df)} rows to {OUTPUT_MARKETS_CSV}")
    if not df.empty:
        print("\nCaptured coverage by platform")
        print(df.groupby("platform").size().to_string())
        print("\nAnalysis-ready coverage by platform/category")
        analysis_ready = df[df["analysis_ready"]]
        if analysis_ready.empty:
            print("No rows are analysis-ready yet.")
        else:
            print(analysis_ready.groupby(["platform", "category"]).size().to_string())


if __name__ == "__main__":
    main()
