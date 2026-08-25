from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_CLAIM_SURFACES = (
    ROOT / "README.md",
    ROOT / "static_dashboard" / "app.jsx",
)
QUARANTINED_CLAIMS = (
    "769",
    "0.1397",
    "0.4216",
    "0.2405",
    "$815.1M",
    "$815M",
    "leakage-resistant forecasts",
    "markets beat baselines",
)
PORTFOLIO_STATUSES = {"fixture_only", "data_pending", "validated_real_sample"}


def load_dashboard_payload(path: Path = ROOT / "static_dashboard" / "data.js") -> dict[str, Any]:
    text = path.read_text()
    match = re.search(r"window\.DASHBOARD_DATA\s*=\s*(\{.*\});\s*$", text, re.DOTALL)
    if not match:
        raise ValueError("static_dashboard/data.js must assign window.DASHBOARD_DATA")
    return json.loads(match.group(1))


def _parse_timestamp(value: Any) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def claim_consistency_errors() -> list[str]:
    errors: list[str] = []
    for path in PUBLIC_CLAIM_SURFACES:
        text = path.read_text()
        for claim in QUARANTINED_CLAIMS:
            if claim.lower() in text.lower():
                errors.append(f"quarantined_claim:{path.relative_to(ROOT)}:{claim}")
    try:
        payload = load_dashboard_payload()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"invalid_dashboard_payload:{exc}"]
    if payload.get("data_status") not in PORTFOLIO_STATUSES:
        errors.append("dashboard_data_status_invalid")
    summary = payload.get("summary")
    buckets = payload.get("buckets")
    robustness = payload.get("robustness")
    evidence = payload.get("evidence_sample")
    if not isinstance(summary, dict) or not isinstance(buckets, list) or not isinstance(robustness, dict) or not isinstance(evidence, list):
        return errors + ["dashboard_public_views_missing"]
    required_summary = {"included_count", "submitted_count", "event_count", "average_probability", "observed_yes_rate", "gap", "directional_hit_rate", "brier_score"}
    if not required_summary <= summary.keys():
        errors.append("dashboard_summary_fields_missing")
    if len(buckets) != 5:
        errors.append("dashboard_bucket_count_invalid")
    if sum(int(bucket.get("count", 0)) for bucket in buckets if isinstance(bucket, dict)) != int(summary.get("included_count", -1)):
        errors.append("dashboard_bucket_total_mismatch")
    if robustness.get("included_count") != summary.get("event_count"):
        errors.append("dashboard_robustness_event_count_mismatch")
    required_evidence = {"market_id", "title", "probability", "resolution", "probability_timestamp", "resolution_timestamp", "market_url"}
    if not evidence or any(not required_evidence <= row.keys() for row in evidence if isinstance(row, dict)):
        errors.append("dashboard_evidence_sample_invalid")
    for index, row in enumerate(evidence):
        probability_at = _parse_timestamp(row.get("probability_timestamp"))
        resolution_at = _parse_timestamp(row.get("resolution_timestamp"))
        if probability_at is None or resolution_at is None or probability_at >= resolution_at:
            errors.append(f"dashboard_evidence_row_not_pre_result:{index}")
    if not isinstance(payload.get("limitations"), list) or not payload["limitations"]:
        errors.append("dashboard_limitations_missing")
    if payload.get("data_status") == "validated_real_sample" and int(summary.get("included_count", 0)) <= 0:
        errors.append("validated_dashboard_requires_included_rows")
    return errors
