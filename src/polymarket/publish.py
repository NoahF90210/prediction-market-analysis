"""Generate the compact publication payload from frozen local results."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from src.polymarket.full_collection import ROOT

RESULTS = ROOT / "data" / "results"
PROCESSED = ROOT / "data" / "processed"
OUTPUT = ROOT / "static_dashboard" / "data.js"


def load(path: Path):
    return json.loads(path.read_text())


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def publish() -> dict:
    summary = load(RESULTS / "summary.json")
    quality = load(RESULTS / "data_quality.json")
    robustness = load(RESULTS / "robustness_one_market_per_event.json")
    manifest = load(RESULTS / "dataset_manifest.json")
    with (RESULTS / "probability_buckets.csv").open(encoding="utf-8") as handle:
        bucket_rows = list(csv.DictReader(handle))
    with (PROCESSED / "polymarket_markets.csv").open(encoding="utf-8") as handle:
        all_rows = list(csv.DictReader(handle))
    sample = []
    seen_buckets = set()
    for row in all_rows:
        probability = float(row["probability"])
        if probability < 0.2:
            label = "0-20%"
        elif probability < 0.4:
            label = "20-40%"
        elif probability < 0.6:
            label = "40-60%"
        elif probability < 0.8:
            label = "60-80%"
        else:
            label = "80-100%"
        if label in seen_buckets and len(sample) >= 15:
            continue
        sample.append({
            "market_id": row["market_id"],
            "event_id": row["event_id"],
            "title": row["question"],
            "probability": probability,
            "resolution": "YES" if row["resolution"] == "1" else "NO",
            "probability_timestamp": row["probability_timestamp"],
            "resolution_timestamp": row["resolution_timestamp"],
            "market_url": row["market_url"],
            "bucket": label,
        })
        seen_buckets.add(label)
        if len(sample) >= 15 and len(seen_buckets) == 5:
            break
    data = {
        "data_status": "validated_real_sample",
        "question": "When Polymarket says YES is likely, does YES actually happen about that often?",
        "status_message": "This is a verified local analysis of canonical YES/NO markets resolved during calendar year 2025.",
        "scope": "75,036 included markets · 14,678 events · 2025 UTC resolution window",
        "source": {
            "platform_boundary": "Polymarket Gamma metadata + CLOB price history",
            "sha256": manifest["files"]["normalized_dataset"]["sha256"],
            "docs": [
                "https://docs.polymarket.com/api-reference/markets/list-markets-keyset-pagination",
                "https://docs.polymarket.com/api-reference/markets/get-prices-history",
            ],
        },
        "summary": {
            "included_count": summary["included_market_count"],
            "submitted_count": quality["inventory_candidates"],
            "coverage_rate": summary["included_market_count"] / quality["inventory_candidates"],
            "event_count": summary["unique_event_count"],
            "average_probability": summary["overall_average_predicted_probability"],
            "observed_yes_rate": summary["overall_observed_yes_frequency"],
            "gap": summary["overall_percentage_point_gap"],
            "directional_hit_rate": summary["directional_hit_rate_at_0_5"],
            "brier_score": summary["brier_score"],
        },
        "buckets": [
            {
                "label": f"{int(float(row['lower_probability']) * 100)} to {int(float(row['upper_probability']) * 100)}%",
                "lower": float(row["lower_probability"]),
                "upper": float(row["upper_probability"]),
                "count": int(row["market_count"]),
                "average_probability": float(row["average_predicted_probability"]),
                "observed_yes_rate": float(row["observed_yes_frequency"]),
                "gap": float(row["percentage_point_gap"]),
            }
            for row in bucket_rows
        ],
        "robustness": {
            "included_count": robustness["included_market_count"],
            "average_probability": robustness["average_predicted_probability"],
            "observed_yes_rate": robustness["observed_yes_frequency"],
            "gap": robustness["percentage_point_gap"],
            "directional_hit_rate": robustness["directional_hit_rate_at_0_5"],
            "brier_score": robustness["brier_score"],
            "selection_rule": robustness["selection_rule"],
        },
        "exclusions": [
            {"reason": "missing or stale CLOB price history", "count": 17839},
            {"reason": "named outcomes excluded before price collection", "count": 135869},
            {"reason": "outside the approved resolution window", "count": 1266720},
        ],
        "evidence_sample": sample,
        "method": {
            "snapshot": "Latest observed YES-token price at or before 24 hours before closedTime.",
            "buckets": "Five fixed probability ranges from 0% to 100%.",
            "gap": "Observed YES frequency minus average predicted YES probability.",
            "outcome": "YES equals 1 and NO equals 0.",
        },
        "limitations": [
            "Market-level rows include related markets from the same event.",
            "The one-market-per-event check changes the sign of the overall gap, so the pooled result is not an event-independent estimate.",
            "The result is descriptive for Polymarket and the 2025 UTC resolution window only.",
            "Categories were not used as eligibility filters, and Gamma category labels were missing in this inventory.",
            "This does not establish a trading edge, causal effect, or universal accuracy claim.",
        ],
        "build_id": manifest["files"]["normalized_dataset"]["sha256"],
    }
    OUTPUT.write_text("// Generated by src.polymarket.publish.\nwindow.DASHBOARD_DATA = " + json.dumps(data, separators=(",", ":")) + ";\n")
    return data


if __name__ == "__main__":
    data = publish()
    print(json.dumps({"output": str(OUTPUT), "included": data["summary"]["included_count"], "sample_rows": len(data["evidence_sample"])}, indent=2))
