from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.rebuild.protocol import canonical_json_bytes, parse_utc, utc_iso

PORTFOLIO_SCHEMA_VERSION = "1.0.0"
SUPPORTED_PLATFORM = "polymarket"

OUTPUT_FIELDS = [
    "schema_version",
    "build_id",
    "platform",
    "market_id",
    "event_id",
    "title",
    "source_url",
    "source_endpoint",
    "probability",
    "probability_timestamp",
    "resolution",
    "outcome",
    "resolution_timestamp",
    "outcome_source",
    "retrieved_at",
    "inclusion_status",
    "exclusion_reasons",
    "input_row_number",
    "input_file_sha256",
]


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_probability(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        probability = float(value)
    except (TypeError, ValueError):
        return None
    if not 0 <= probability <= 1:
        return None
    return probability


def _parse_resolution(value: Any) -> tuple[str | None, int | None]:
    if isinstance(value, bool):
        return ("YES", 1) if value else ("NO", 0)
    if isinstance(value, (int, float)) and value in {0, 1}:
        return ("YES", 1) if int(value) == 1 else ("NO", 0)
    text = str(value or "").strip().upper()
    if text in {"YES", "Y", "TRUE", "1"}:
        return "YES", 1
    if text in {"NO", "N", "FALSE", "0"}:
        return "NO", 0
    return None, None


def _valid_https_url(value: str | None) -> bool:
    if not value:
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def load_input(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows = [dict(row) for row in csv.DictReader(handle)]
        return rows, {
            "schema_version": PORTFOLIO_SCHEMA_VERSION,
            "scope": "Bounded normalized Polymarket sample supplied as CSV.",
        }
    if suffix == ".json":
        payload = json.loads(path.read_text())
        if isinstance(payload, list):
            return payload, {
                "schema_version": PORTFOLIO_SCHEMA_VERSION,
                "scope": "Bounded normalized Polymarket sample supplied as JSON.",
            }
        if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
            raise ValueError("JSON input must be a row list or an object containing a rows list")
        return payload["rows"], {
            "schema_version": str(payload.get("schema_version") or PORTFOLIO_SCHEMA_VERSION),
            "scope": str(payload.get("scope") or "Bounded normalized Polymarket sample supplied as JSON."),
        }
    raise ValueError("Normalized input must be a .csv or .json file")


def _normalize_row(raw: Any, *, row_number: int, source_sha256: str) -> dict[str, Any]:
    reasons: set[str] = set()
    record = raw if isinstance(raw, dict) else {}
    if not isinstance(raw, dict):
        reasons.add("malformed_row")

    source_reasons = record.get("exclusion_reasons")
    if isinstance(source_reasons, list):
        reasons.update(str(reason) for reason in source_reasons if reason)
    if record.get("inclusion_status") == "excluded" and not source_reasons:
        reasons.add("source_gate_exclusion")

    platform = (_clean_text(record.get("platform")) or "").lower()
    if not platform:
        reasons.add("missing_platform")
    elif platform != SUPPORTED_PLATFORM:
        reasons.add("unsupported_platform")

    market_id = _clean_text(record.get("market_id"))
    event_id = _clean_text(record.get("event_id")) or market_id
    title = _clean_text(record.get("title"))
    source_url = _clean_text(record.get("source_url"))
    source_endpoint = _clean_text(record.get("source_endpoint")) or source_url
    outcome_source = _clean_text(record.get("outcome_source"))

    if not market_id:
        reasons.add("missing_market_id")
    if not title:
        reasons.add("missing_title")
    if not _valid_https_url(source_url):
        reasons.add("missing_or_invalid_source_url")
    if not _valid_https_url(source_endpoint):
        reasons.add("missing_or_invalid_source_endpoint")
    if not outcome_source:
        reasons.add("missing_outcome_source")

    probability = _parse_probability(record.get("probability"))
    if probability is None:
        reasons.add("missing_or_invalid_probability")

    probability_at = parse_utc(record.get("probability_timestamp"))
    resolution_at = parse_utc(record.get("resolution_timestamp"))
    retrieved_at = parse_utc(record.get("retrieved_at"))
    if probability_at is None:
        reasons.add("missing_probability_timestamp")
    if resolution_at is None:
        reasons.add("missing_resolution_timestamp")
    if probability_at is not None and resolution_at is not None and probability_at >= resolution_at:
        reasons.add("post_result_probability")

    resolution, outcome = _parse_resolution(record.get("outcome", record.get("resolution")))
    if resolution is None:
        reasons.add("missing_outcome")

    return {
        "schema_version": PORTFOLIO_SCHEMA_VERSION,
        "build_id": "",
        "platform": platform or None,
        "market_id": market_id,
        "event_id": event_id,
        "title": title,
        "source_url": source_url,
        "source_endpoint": source_endpoint,
        "probability": probability,
        "probability_timestamp": utc_iso(probability_at) if probability_at else None,
        "resolution": resolution,
        "outcome": outcome,
        "resolution_timestamp": utc_iso(resolution_at) if resolution_at else None,
        "outcome_source": outcome_source,
        "retrieved_at": utc_iso(retrieved_at) if retrieved_at else None,
        "inclusion_status": "excluded" if reasons else "included",
        "exclusion_reasons": sorted(reasons),
        "input_row_number": row_number,
        "input_file_sha256": source_sha256,
    }


def _apply_duplicate_gate(rows: list[dict[str, Any]]) -> None:
    counts = Counter(
        (row["platform"], row["market_id"])
        for row in rows
        if row.get("platform") and row.get("market_id")
    )
    for row in rows:
        key = (row.get("platform"), row.get("market_id"))
        if row.get("market_id") and counts[key] > 1:
            reasons = set(row["exclusion_reasons"])
            reasons.add("duplicate_market_id")
            row["exclusion_reasons"] = sorted(reasons)
            row["inclusion_status"] = "excluded"


def normalize_input(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw_rows, metadata = load_input(path)
    source_sha256 = _file_sha256(path)
    rows = [
        _normalize_row(raw, row_number=index, source_sha256=source_sha256)
        for index, raw in enumerate(raw_rows, start=1)
    ]
    _apply_duplicate_gate(rows)

    build_material = {
        "schema_version": PORTFOLIO_SCHEMA_VERSION,
        "source_sha256": source_sha256,
        "rows": [{key: value for key, value in row.items() if key != "build_id"} for row in rows],
    }
    build_id = hashlib.sha256(canonical_json_bytes(build_material)).hexdigest()
    for row in rows:
        row["build_id"] = build_id

    rows.sort(
        key=lambda row: (
            row.get("probability_timestamp") or "",
            row.get("market_id") or "",
            row["input_row_number"],
        )
    )
    return rows, {
        **metadata,
        "source_name": path.name,
        "source_sha256": source_sha256,
        "build_id": build_id,
    }
