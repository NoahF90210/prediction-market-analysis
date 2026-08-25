"""Normalize the completed local inventory and price ledgers."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from src.polymarket.full_collection import (
    INVENTORY_EXCLUSIONS,
    INVENTORY_JSONL,
    PRICE_RESULTS,
    ROOT,
)

PROCESSED = ROOT / "data" / "processed"
RESULTS = ROOT / "data" / "results"
MARKETS_CSV = PROCESSED / "polymarket_markets.csv"
EXCLUSIONS_CSV = RESULTS / "exclusions.csv"
QUALITY_JSON = RESULTS / "data_quality.json"

INCLUDED_FIELDS = [
    "market_id", "event_id", "event_title", "question", "category", "tags",
    "yes_token_id", "probability", "probability_timestamp", "snapshot_cutoff",
    "snapshot_age_hours", "resolution", "resolution_timestamp", "resolution_source",
    "market_url", "volume",
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def normalize() -> dict[str, Any]:
    candidates = read_jsonl(INVENTORY_JSONL)
    inventory_exclusions = read_jsonl(INVENTORY_EXCLUSIONS)
    price_results = read_jsonl(PRICE_RESULTS)
    price_by_id = {str(row["market_id"]): row for row in price_results}
    included = []
    exclusions = []
    for row in inventory_exclusions:
        exclusions.append({
            "market_id": row.get("market_id", ""),
            "stage": "inventory",
            "reason": row.get("reason", "malformed_api_record"),
            "question": row.get("question", ""),
        })
    for candidate in candidates:
        market_id = str(candidate["market_id"])
        price = price_by_id.get(market_id)
        if price is None:
            exclusions.append({"market_id": market_id, "stage": "price", "reason": "price_collection_incomplete", "question": candidate.get("question", "")})
            continue
        if price.get("status") != "included":
            exclusions.append({"market_id": market_id, "stage": "price", "reason": price.get("exclusion_reason", "api_request_failed"), "question": candidate.get("question", "")})
            continue
        included.append({
            "market_id": market_id,
            "event_id": candidate["event_id"],
            "event_title": candidate.get("event_title", ""),
            "question": candidate.get("question", ""),
            "category": candidate.get("category", ""),
            "tags": json.dumps(candidate.get("tags", []), separators=(",", ":")),
            "yes_token_id": candidate["yes_token_id"],
            "probability": price["probability"],
            "probability_timestamp": price["probability_timestamp"],
            "snapshot_cutoff": price["snapshot_cutoff"],
            "snapshot_age_hours": price["snapshot_age_hours"],
            "resolution": candidate["resolution"],
            "resolution_timestamp": candidate["resolution_timestamp"],
            "resolution_source": candidate.get("resolution_source", ""),
            "market_url": candidate.get("market_url", ""),
            "volume": candidate.get("volume", ""),
        })
    write_csv(MARKETS_CSV, INCLUDED_FIELDS, included)
    write_csv(EXCLUSIONS_CSV, ["market_id", "stage", "reason", "question"], exclusions)
    event_counts = Counter(row["event_id"] for row in included)
    category_counts = Counter(row["category"] or "missing" for row in included)
    reason_counts = Counter(row["reason"] for row in exclusions)
    quality = {
        "inventory_candidates": len(candidates),
        "inventory_exclusions": len(inventory_exclusions),
        "price_results": len(price_results),
        "included_markets": len(included),
        "excluded_rows": len(exclusions),
        "unique_events": len(event_counts),
        "markets_per_event": Counter(event_counts.values()),
        "excluded_by_reason": reason_counts,
        "category_counts": category_counts,
        "earliest_resolution": min((row["resolution_timestamp"] for row in included), default=None),
        "latest_resolution": max((row["resolution_timestamp"] for row in included), default=None),
        "duplicate_market_ids": len(candidates) - len({row["market_id"] for row in candidates}),
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    QUALITY_JSON.write_text(json.dumps(quality, indent=2, default=dict) + "\n")
    return quality


if __name__ == "__main__":
    print(json.dumps(normalize(), indent=2, default=dict))
