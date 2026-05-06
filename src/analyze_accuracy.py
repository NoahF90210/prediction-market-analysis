"""
Compute MVP accuracy tables from data/cleaned/accuracy_markets.csv.
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from src.accuracy import (
    add_baseline_columns,
    calibration_table,
    baseline_comparison_table,
    metric_ci_summary,
    metric_summary,
)

CLEAN_DIR = ROOT / "data" / "cleaned"
INPUT_CSV = CLEAN_DIR / "accuracy_markets.csv"


def main() -> None:
    df = pd.read_csv(INPUT_CSV)
    scored = add_baseline_columns(df)

    overall = metric_summary(scored)
    by_platform = metric_summary(scored, ["platform"])
    by_category = metric_summary(scored, ["category"])
    by_platform_category = metric_summary(scored, ["platform", "category"])
    by_source = metric_summary(scored, ["platform", "forecast_source"])
    by_duration = metric_summary(scored, ["duration_bucket"])
    by_volume_bucket = metric_summary(scored, ["volume_bucket"])
    calibration = calibration_table(scored)
    platform_ci = metric_ci_summary(scored, ["platform"])
    baseline_overall = pd.concat(
        [
            baseline_comparison_table(scored, "baseline_prob_50", "always_50"),
            baseline_comparison_table(scored, "baseline_prob_category_rate", "category_base_rate_in_sample"),
        ],
        ignore_index=True,
    )
    baseline_by_platform = pd.concat(
        [
            baseline_comparison_table(scored, "baseline_prob_50", "always_50", ["platform"]),
            baseline_comparison_table(
                scored,
                "baseline_prob_category_rate",
                "category_base_rate_in_sample",
                ["platform"],
            ),
        ],
        ignore_index=True,
    )
    baseline_by_category = pd.concat(
        [
            baseline_comparison_table(scored, "baseline_prob_50", "always_50", ["category"]),
            baseline_comparison_table(
                scored,
                "baseline_prob_category_rate",
                "category_base_rate_in_sample",
                ["category"],
            ),
        ],
        ignore_index=True,
    )

    overall.to_csv(CLEAN_DIR / "accuracy_summary_overall.csv", index=False)
    by_platform.to_csv(CLEAN_DIR / "accuracy_summary_by_platform.csv", index=False)
    by_category.to_csv(CLEAN_DIR / "accuracy_summary_by_category.csv", index=False)
    by_platform_category.to_csv(CLEAN_DIR / "accuracy_summary_by_platform_category.csv", index=False)
    by_source.to_csv(CLEAN_DIR / "accuracy_summary_by_source.csv", index=False)
    by_duration.to_csv(CLEAN_DIR / "accuracy_summary_by_duration.csv", index=False)
    by_volume_bucket.to_csv(CLEAN_DIR / "accuracy_summary_by_volume_bucket.csv", index=False)
    calibration.to_csv(CLEAN_DIR / "accuracy_calibration.csv", index=False)
    platform_ci.to_csv(CLEAN_DIR / "accuracy_platform_metric_ci.csv", index=False)
    baseline_overall.to_csv(CLEAN_DIR / "accuracy_baseline_overall.csv", index=False)
    baseline_by_platform.to_csv(CLEAN_DIR / "accuracy_baseline_by_platform.csv", index=False)
    baseline_by_category.to_csv(CLEAN_DIR / "accuracy_baseline_by_category.csv", index=False)
    scored.to_csv(CLEAN_DIR / "accuracy_markets_scored.csv", index=False)

    print("Overall")
    print(overall.to_string(index=False))
    print("\nBy platform")
    print(by_platform.to_string(index=False))
    print("\nBy category")
    print(by_category.to_string(index=False))
    print("\nBy source")
    print(by_source.to_string(index=False))
    print("\nBy duration")
    print(by_duration.to_string(index=False))
    print("\nBy volume bucket")
    print(by_volume_bucket.to_string(index=False))
    print("\nPlatform metric CIs")
    print(platform_ci.to_string(index=False))
    print("\nBaseline comparison by platform")
    print(baseline_by_platform.to_string(index=False))


if __name__ == "__main__":
    main()
