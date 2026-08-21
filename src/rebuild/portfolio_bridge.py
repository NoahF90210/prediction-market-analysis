from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from src.rebuild.protocol import canonical_json_bytes


def _portfolio_row(row: dict[str, Any]) -> dict[str, Any]:
    market_url = row.get("market_url")
    endpoint = row.get("endpoint") or market_url
    return {
        "platform": row.get("platform"),
        "market_id": row.get("market_id"),
        "event_id": row.get("event_group_id") or row.get("event_id"),
        "title": row.get("title"),
        "source_url": market_url,
        "source_endpoint": endpoint,
        "probability": row.get("yes_probability"),
        "probability_timestamp": row.get("forecast_observed_at"),
        "outcome": row.get("resolution"),
        "resolution_timestamp": row.get("resolved_at"),
        "outcome_source": market_url,
        "retrieved_at": row.get("retrieval_timestamp"),
        "inclusion_status": row.get("inclusion_status"),
        "exclusion_reasons": row.get("exclusion_reasons") or [],
    }


def write_portfolio_input(rows: Iterable[dict[str, Any]], path: Path) -> Path:
    payload = {
        "schema_version": "1.0.0",
        "scope": "Bounded real Polymarket sample selected by the provenance-safe 24-hour pre-result protocol.",
        "rows": [_portfolio_row(row) for row in rows],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(payload) + b"\n")
    return path


def load_analysis_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, list):
        raise ValueError("Analysis rows must be a JSON list")
    return [row for row in payload if isinstance(row, dict)]
