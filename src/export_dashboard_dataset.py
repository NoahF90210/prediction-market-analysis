from __future__ import annotations

import pandas as pd

from src.settings import CLEAN_DIR, OUTPUT_MARKETS_CSV, OUTPUT_REVIEW_QUEUE_CSV, OUTPUT_SCORED_CSV
from src.warehouse_pipeline import build_dashboard_export, build_review_queue


def main() -> None:
    normalized = pd.read_csv(CLEAN_DIR / "normalized_markets.csv") if (CLEAN_DIR / "normalized_markets.csv").exists() else pd.DataFrame()
    scored = pd.read_csv(CLEAN_DIR / "scored_markets.csv") if (CLEAN_DIR / "scored_markets.csv").exists() else pd.DataFrame()
    dashboard_df = build_dashboard_export(normalized, scored)
    review_queue = build_review_queue(normalized)

    dashboard_df.to_csv(OUTPUT_MARKETS_CSV, index=False)
    scored.to_csv(OUTPUT_SCORED_CSV, index=False)
    review_queue.to_csv(OUTPUT_REVIEW_QUEUE_CSV, index=False)
    print(f"Wrote {len(dashboard_df)} dashboard rows to {OUTPUT_MARKETS_CSV}")


if __name__ == "__main__":
    main()
