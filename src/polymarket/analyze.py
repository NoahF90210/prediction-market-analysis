"""Broad pooled YES/NO calibration summaries for the normalized local dataset."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from statistics import mean

from src.polymarket.full_collection import ROOT

MARKETS_CSV = ROOT / "data" / "processed" / "polymarket_markets.csv"
RESULTS = ROOT / "data" / "results"
BUCKETS_CSV = RESULTS / "probability_buckets.csv"
SUMMARY_JSON = RESULTS / "summary.json"
BOUNDARIES = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]


def bucket(probability: float) -> tuple[str, float, float]:
    for index in range(len(BOUNDARIES) - 1):
        lower, upper = BOUNDARIES[index:index + 2]
        if probability < upper or (index == len(BOUNDARIES) - 2 and probability <= upper):
            return f"[{lower:.1f}, {upper:.1f}{']' if index == len(BOUNDARIES) - 2 else ')'}", lower, upper
    raise ValueError(f"probability outside [0, 1]: {probability}")


def load_rows() -> list[dict]:
    if not MARKETS_CSV.exists():
        raise FileNotFoundError(f"normalized dataset missing: {MARKETS_CSV}")
    with MARKETS_CSV.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def analyze() -> dict:
    rows = load_rows()
    parsed = []
    for row in rows:
        probability = float(row["probability"])
        outcome = int(row["resolution"])
        label, lower, upper = bucket(probability)
        parsed.append({**row, "probability_num": probability, "outcome_num": outcome, "bucket": label, "lower": lower, "upper": upper})
    bucket_rows = []
    for label, group in _groups(parsed, "bucket"):
        bucket_rows.append({
            "bucket": label,
            "lower_probability": group[0]["lower"],
            "upper_probability": group[0]["upper"],
            "market_count": len(group),
            "event_count": len({row["event_id"] for row in group}),
            "average_predicted_probability": safe_mean(row["probability_num"] for row in group),
            "observed_yes_frequency": safe_mean(row["outcome_num"] for row in group),
            "percentage_point_gap": safe_mean(row["outcome_num"] for row in group) - safe_mean(row["probability_num"] for row in group),
        })
    bucket_rows.sort(key=lambda row: row["lower_probability"])
    overall_probability = safe_mean(row["probability_num"] for row in parsed)
    overall_yes = safe_mean(row["outcome_num"] for row in parsed)
    summary = {
        "analysis_scope": "all included canonical YES/NO Polymarket markets; categories retained only as metadata",
        "included_market_count": len(parsed),
        "unique_event_count": len({row["event_id"] for row in parsed}),
        "overall_average_predicted_probability": overall_probability,
        "overall_observed_yes_frequency": overall_yes,
        "overall_percentage_point_gap": overall_yes - overall_probability,
        "directional_hit_rate_at_0_5": safe_mean(int((row["probability_num"] >= 0.5) == bool(row["outcome_num"])) for row in parsed),
        "brier_score": safe_mean((row["probability_num"] - row["outcome_num"]) ** 2 for row in parsed),
        "bucket_count_sum": sum(row["market_count"] for row in bucket_rows),
        "category_counts": dict(Counter(row["category"] or "missing" for row in parsed)),
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    with BUCKETS_CSV.open("w", newline="", encoding="utf-8") as handle:
        fields = list(bucket_rows[0]) if bucket_rows else ["bucket", "lower_probability", "upper_probability", "market_count", "event_count", "average_predicted_probability", "observed_yes_frequency", "percentage_point_gap"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(bucket_rows)
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def _groups(rows: list[dict], key: str):
    groups = {}
    for row in rows:
        groups.setdefault(row[key], []).append(row)
    return groups.items()


def safe_mean(values) -> float:
    values = list(values)
    return mean(values) if values else 0.0


if __name__ == "__main__":
    print(json.dumps(analyze(), indent=2))
