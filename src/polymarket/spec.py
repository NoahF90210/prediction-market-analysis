"""Validation for the explicit empirical analysis specification."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

REQUIRED = {
    "platform", "resolution_start", "resolution_end", "snapshot_hours_before_resolution",
    "maximum_snapshot_age_hours", "probability_buckets", "include_related_markets",
    "require_binary_outcomes", "require_resolved_status",
}


def load_config(path: str | Path = "config/analysis.json") -> dict:
    config = json.loads(Path(path).read_text())
    missing = REQUIRED - config.keys()
    if missing:
        raise ValueError(f"missing configuration fields: {sorted(missing)}")
    if config["platform"] != "polymarket":
        raise ValueError("platform must be polymarket")
    start = _utc(config["resolution_start"])
    end = _utc(config["resolution_end"])
    if start >= end:
        raise ValueError("resolution_start must precede resolution_end")
    if config["snapshot_hours_before_resolution"] <= 0:
        raise ValueError("snapshot_hours_before_resolution must be positive")
    if config["maximum_snapshot_age_hours"] <= 0:
        raise ValueError("maximum_snapshot_age_hours must be positive")
    buckets = config["probability_buckets"]
    if buckets != sorted(set(buckets)) or buckets[0] != 0.0 or buckets[-1] != 1.0:
        raise ValueError("probability_buckets must be unique, sorted, and span 0.0 to 1.0")
    return config


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo != timezone.utc:
        raise ValueError(f"timestamp must be UTC: {value}")
    return parsed
