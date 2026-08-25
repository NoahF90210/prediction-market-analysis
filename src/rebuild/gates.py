from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

from src.rebuild.categories import classify_market
from src.rebuild.collectors import CollectedCandidate
from src.rebuild.normalization import normalize_probability, to_float
from src.rebuild.protocol import Protocol, canonical_json_bytes, parse_utc, utc_iso
from src.rebuild.provenance import RawRecord

_CONDITIONAL_PATTERN = re.compile(
    r"\b(conditional on|conditioned on|provided that|in the event that|unless|if and only if|if)\b",
    re.IGNORECASE,
)
_RULE_CONDITIONAL_PATTERN = re.compile(
    r"\b(conditional on|conditioned on|provided that|in the event that|active only if|resolves? only if|market only if|contract only if)\b|\bif\b.{0,120}\bthen\b",
    re.IGNORECASE,
)
_PARLAY_PATTERN = re.compile(r"\b(parlay|multi[- ]?leg|same game parlay|combo)\b", re.IGNORECASE)


def _history_timestamp(point: dict[str, Any], keys: Iterable[str]):
    for key in keys:
        value = parse_utc(point.get(key))
        if value is not None:
            return value
    return None


def _history_probability(point: dict[str, Any], keys: Iterable[str]) -> float | None:
    for key in keys:
        if key in point:
            probability = normalize_probability(point.get(key))
            if probability is not None:
                return probability
    return None


def select_snapshot(record: dict[str, Any], target) -> tuple[float | None, Any, float | None]:
    if target is None:
        return None, None, None
    valid: list[tuple[Any, float]] = []
    time_keys = tuple(record.get("history_time_keys") or ())
    price_keys = tuple(record.get("history_price_keys") or ())
    for point in record.get("history") or []:
        if not isinstance(point, dict):
            continue
        observed_at = _history_timestamp(point, time_keys)
        probability = _history_probability(point, price_keys)
        if observed_at is None or probability is None or observed_at > target:
            continue
        valid.append((observed_at, probability))
    if not valid:
        return None, None, None
    observed_at, probability = max(valid, key=lambda item: item[0])
    return probability, observed_at, (target - observed_at).total_seconds()


def is_multileg(record: dict[str, Any]) -> bool:
    if bool(record.get("explicit_multileg")):
        return True
    ticker = str(record.get("market_id") or "").upper()
    if ticker.startswith("KXMVE") or record.get("mve_collection_ticker"):
        return True
    legs = record.get("mve_selected_legs")
    if isinstance(legs, str):
        try:
            legs = json.loads(legs)
        except json.JSONDecodeError:
            legs = []
    if isinstance(legs, list) and len(legs) > 1:
        return True
    return bool(_PARLAY_PATTERN.search(str(record.get("title") or "")))


def is_conditional(record: dict[str, Any]) -> bool:
    if bool(record.get("explicit_conditional")):
        return True
    title = str(record.get("title") or "")
    rules = str(record.get("rules") or "")
    return bool(_CONDITIONAL_PATTERN.search(title) or _RULE_CONDITIONAL_PATTERN.search(rules))


def _is_binary(record: dict[str, Any]) -> bool:
    market_type = str(record.get("raw_market_type") or "binary").strip().lower()
    return market_type in {"binary", "yes_no", "yes/no"}


def _contract_role(record: dict[str, Any]) -> tuple[str, bool]:
    if bool(record.get("explicit_complement")):
        return "complement", True
    relationship = str(record.get("native_group_relationship") or "unknown")
    if relationship == "standalone":
        return "standalone", False
    if relationship == "mutually_exclusive":
        return "mutually_exclusive_member", False
    if relationship == "related":
        return "related_member", False
    return "unknown", False


def _raw_record_exists(raw_root: Path, provenance: RawRecord | None) -> bool:
    if provenance is None:
        return False
    path = raw_root / provenance.raw_response_path
    if not path.exists():
        return False
    return hashlib.sha256(path.read_bytes()).hexdigest() == provenance.sha256


def normalize_candidates(
    candidates: Iterable[CollectedCandidate],
    *,
    protocol: Protocol,
    raw_root: Path,
    build_id: str,
    feature_columns: Iterable[str] = ("platform", "normalized_category", "snapshot_staleness_seconds"),
) -> list[dict[str, Any]]:
    features = tuple(feature_columns)
    rows: list[dict[str, Any]] = []

    for candidate in candidates:
        source = candidate.record
        reasons: set[str] = set()
        platform = str(source.get("platform") or "")
        market_id = str(source.get("market_id") or "")
        event_id = str(source.get("event_id") or "")
        event_group_id = str(source.get("event_group_id") or "")

        if platform not in protocol.payload["platforms"]:
            reasons.add("missing_platform_identity")
        if not market_id:
            reasons.add("missing_market_identity")
        if not event_id or not event_group_id:
            reasons.add("missing_event_identity")
        if not _is_binary(source):
            reasons.add("non_binary_contract")

        multileg = is_multileg(source)
        conditional = is_conditional(source)
        if multileg:
            reasons.add("excluded_multileg_parlay")
        if conditional:
            reasons.add("excluded_conditional_contract")

        resolved_at = parse_utc(source.get("resolved_at"))
        if source.get("resolution") not in {"YES", "NO"}:
            reasons.add("missing_resolution")
        if resolved_at is None:
            reasons.add("missing_resolution_timestamp")
        elif not protocol.contains_resolution(resolved_at):
            reasons.add("outside_observation_window")

        boundary = protocol.forecast_boundary(source)
        target = protocol.forecast_target(source)
        if boundary is None:
            reasons.add("missing_forecast_boundary")
        if target is None:
            reasons.add("missing_forecast_target")

        probability, observed_at, staleness = select_snapshot(source, target)
        if observed_at is None:
            reasons.add("missing_snapshot_timestamp")
        elif target is not None and observed_at > target:
            reasons.add("snapshot_after_cutoff")
        if staleness is not None and staleness > protocol.max_snapshot_staleness_seconds:
            reasons.add("snapshot_too_stale")
        if probability is None:
            reasons.add("missing_forecast_probability")
        elif not 0 <= probability <= 1:
            reasons.add("invalid_forecast_probability")

        price_source = source.get("price_source")
        if price_source not in protocol.allowed_snapshot_sources:
            reasons.add("metadata_or_terminal_snapshot")

        market_ok = _raw_record_exists(raw_root, candidate.market_provenance)
        history_ok = _raw_record_exists(raw_root, candidate.history_provenance)
        if not market_ok:
            reasons.add("missing_raw_market_provenance")
        if not history_ok:
            reasons.add("missing_raw_history_provenance")

        forbidden = {feature for feature in features if feature in protocol.forbidden_model_features}
        if forbidden:
            reasons.add("post_cutoff_feature")

        role, complement = _contract_role(source)
        if role == "unknown":
            reasons.add("complement_relationship_unresolved")

        raw_tags = source.get("raw_tags")
        if not isinstance(raw_tags, list):
            raw_tags = []
        category = classify_market(
            platform=platform,
            market_id=market_id,
            title=str(source.get("title") or ""),
            slug=market_id,
            raw_platform_category=str(source.get("raw_category") or ""),
            raw_tags=raw_tags,
            context_fields=[str(source.get("rules") or ""), str(source.get("series_id") or "")],
        ).canonical_category

        final_volume = to_float(source.get("final_volume"))
        cutoff_volume = to_float(source.get("cutoff_volume"))
        provenance = candidate.history_provenance or candidate.market_provenance
        row = {
            "schema_version": str(protocol.payload["analysis_schema_version"]),
            "build_id": build_id,
            "platform": platform,
            "market_id": market_id,
            "event_id": event_id,
            "event_group_id": event_group_id,
            "series_id": source.get("series_id") or None,
            "title": str(source.get("title") or ""),
            "rules": source.get("rules") or None,
            "market_url": source.get("market_url") or None,
            "raw_market_type": source.get("raw_market_type") or None,
            "raw_category": source.get("raw_category") or None,
            "normalized_category": category,
            "contract_role": role,
            "is_complement": complement,
            "is_multileg": multileg,
            "is_conditional": conditional,
            "event_weight": 0.0,
            "opened_at": utc_iso(parse_utc(source.get("opened_at"))) if parse_utc(source.get("opened_at")) else None,
            "scheduled_close_at": utc_iso(parse_utc(source.get("scheduled_close_at"))) if parse_utc(source.get("scheduled_close_at")) else None,
            "trading_closed_at": utc_iso(parse_utc(source.get("trading_closed_at"))) if parse_utc(source.get("trading_closed_at")) else None,
            "event_started_at": utc_iso(parse_utc(source.get("event_started_at"))) if parse_utc(source.get("event_started_at")) else None,
            "resolved_at": utc_iso(resolved_at) if resolved_at else None,
            "forecast_boundary_at": utc_iso(boundary) if boundary else None,
            "forecast_target_at": utc_iso(target) if target else None,
            "forecast_observed_at": utc_iso(observed_at) if observed_at else None,
            "snapshot_staleness_seconds": float(staleness) if staleness is not None else None,
            "yes_probability": float(probability) if probability is not None else None,
            "price_source": price_source or None,
            "raw_yes_orientation": source.get("raw_yes_orientation") or None,
            "resolution": source.get("resolution") if source.get("resolution") in {"YES", "NO"} else None,
            "resolution_source": source.get("resolution_source") or None,
            "cutoff_volume": cutoff_volume,
            "final_volume": final_volume,
            "volume_unit": source.get("volume_unit") or None,
            "cutoff_volume_source": source.get("cutoff_volume_source") or None,
            "final_volume_source": source.get("final_volume_source") or None,
            "raw_market_response_path": candidate.market_provenance.raw_response_path if candidate.market_provenance else None,
            "raw_market_sha256": candidate.market_provenance.sha256 if candidate.market_provenance else None,
            "raw_history_response_path": candidate.history_provenance.raw_response_path if candidate.history_provenance else None,
            "raw_history_sha256": candidate.history_provenance.sha256 if candidate.history_provenance else None,
            "retrieval_timestamp": provenance.retrieved_at if provenance else None,
            "endpoint": provenance.endpoint if provenance else None,
            "request_params": provenance.request_params if provenance else {},
            "collector_commit": provenance.collector_commit if provenance else None,
            "inclusion_status": "excluded" if reasons else "included",
            "exclusion_reasons": sorted(reasons),
            "feature_columns": list(features),
        }
        rows.append(row)

    _apply_duplicate_gates(rows)
    _apply_event_weights(rows)
    return rows


def _add_reason(row: dict[str, Any], reason: str) -> None:
    reasons = set(row["exclusion_reasons"])
    reasons.add(reason)
    row["exclusion_reasons"] = sorted(reasons)
    row["inclusion_status"] = "excluded"
    row["event_weight"] = 0.0


def _apply_duplicate_gates(rows: list[dict[str, Any]]) -> None:
    market_counts = Counter((row["platform"], row["market_id"]) for row in rows)
    definition_counts = Counter(
        (
            row["platform"],
            row["event_group_id"],
            " ".join(str(row["title"]).lower().split()),
            row["forecast_boundary_at"],
        )
        for row in rows
    )
    for row in rows:
        if market_counts[(row["platform"], row["market_id"])] > 1:
            _add_reason(row, "duplicate_market_id")
        definition_key = (
            row["platform"],
            row["event_group_id"],
            " ".join(str(row["title"]).lower().split()),
            row["forecast_boundary_at"],
        )
        if definition_counts[definition_key] > 1:
            _add_reason(row, "duplicate_contract_definition")


def _apply_event_weights(rows: list[dict[str, Any]]) -> None:
    included_counts = Counter(
        (row["platform"], row["event_group_id"])
        for row in rows
        if row["inclusion_status"] == "included"
    )
    for row in rows:
        if row["inclusion_status"] != "included":
            row["event_weight"] = 0.0
            continue
        count = included_counts[(row["platform"], row["event_group_id"])]
        row["event_weight"] = 1.0 / count


def candidate_to_json(candidate: CollectedCandidate) -> dict[str, Any]:
    return {
        "record": candidate.record,
        "market_provenance": asdict(candidate.market_provenance),
        "history_provenance": asdict(candidate.history_provenance) if candidate.history_provenance else None,
    }


def candidate_from_json(payload: dict[str, Any]) -> CollectedCandidate:
    return CollectedCandidate(
        record=payload["record"],
        market_provenance=RawRecord(**payload["market_provenance"]),
        history_provenance=RawRecord(**payload["history_provenance"]) if payload.get("history_provenance") else None,
    )


def serialized_candidates(candidates: Iterable[CollectedCandidate]) -> list[dict[str, Any]]:
    return [candidate_to_json(candidate) for candidate in candidates]


def candidate_records_sha256(candidates: Iterable[CollectedCandidate]) -> str:
    return hashlib.sha256(canonical_json_bytes(serialized_candidates(candidates))).hexdigest()


def write_candidates(path: Path, candidates: Iterable[CollectedCandidate]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = serialized_candidates(candidates)
    content = canonical_json_bytes(serialized)
    path.write_bytes(content + b"\n")
    return hashlib.sha256(content).hexdigest()


def read_candidates(path: Path) -> list[CollectedCandidate]:
    payload = json.loads(path.read_text())
    return [candidate_from_json(item) for item in payload]
