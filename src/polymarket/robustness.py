"""Deterministic one-market-per-event robustness check."""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

from src.polymarket.full_collection import ROOT

INPUT = ROOT / "data" / "processed" / "polymarket_markets.csv"
OUTPUT = ROOT / "data" / "results" / "robustness_one_market_per_event.json"
BUCKETS_OUTPUT = ROOT / "data" / "results" / "robustness_one_market_per_event_buckets.csv"


def bucket(probability: float) -> tuple[str, float, float]:
    boundaries = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    for index in range(len(boundaries) - 1):
        lower, upper = boundaries[index:index + 2]
        if probability < upper or (index == len(boundaries) - 2 and probability <= upper):
            return f"[{lower:.1f}, {upper:.1f}{']' if index == len(boundaries) - 2 else ')'}", lower, upper
    raise ValueError(probability)


def safe_mean(values):
    values = list(values)
    return mean(values) if values else 0.0


def run() -> dict:
    with INPUT.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    by_event = defaultdict(list)
    for row in rows:
        by_event[row["event_id"]].append(row)
    selected = [sorted(group, key=lambda row: row["market_id"])[0] for group in by_event.values()]
    selected.sort(key=lambda row: row["market_id"])
    parsed = []
    for row in selected:
        probability = float(row["probability"])
        outcome = int(row["resolution"])
        label, lower, upper = bucket(probability)
        parsed.append({"probability": probability, "outcome": outcome, "bucket": label, "lower": lower, "upper": upper, "event_id": row["event_id"]})
    bucket_rows = []
    for label in sorted({row["bucket"] for row in parsed}):
        group = [row for row in parsed if row["bucket"] == label]
        bucket_rows.append({
            "bucket": label,
            "market_count": len(group),
            "average_predicted_probability": safe_mean(row["probability"] for row in group),
            "observed_yes_frequency": safe_mean(row["outcome"] for row in group),
            "percentage_point_gap": safe_mean(row["outcome"] for row in group) - safe_mean(row["probability"] for row in group),
        })
    result = {
        "selection_rule": "Within each event_id, select the lexicographically smallest market_id.",
        "included_market_count": len(parsed),
        "unique_event_count": len(by_event),
        "average_predicted_probability": safe_mean(row["probability"] for row in parsed),
        "observed_yes_frequency": safe_mean(row["outcome"] for row in parsed),
        "percentage_point_gap": safe_mean(row["outcome"] for row in parsed) - safe_mean(row["probability"] for row in parsed),
        "directional_hit_rate_at_0_5": safe_mean(int((row["probability"] >= 0.5) == bool(row["outcome"])) for row in parsed),
        "brier_score": safe_mean((row["probability"] - row["outcome"]) ** 2 for row in parsed),
        "buckets": bucket_rows,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n")
    with BUCKETS_OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        fields = ["bucket", "market_count", "average_predicted_probability", "observed_yes_frequency", "percentage_point_gap"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(bucket_rows)
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
