from __future__ import annotations

import ast
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_CLAIM_SURFACES = (
    ROOT / "README.md",
    ROOT / "static_dashboard" / "app.jsx",
    ROOT / "docs" / "assets" / "dashboard-overview.svg",
    ROOT / "docs" / "assets" / "calibration-audit-placeholder.svg",
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


def _legacy_generator_errors() -> list[str]:
    errors: list[str] = []
    legacy_generator = (ROOT / "src" / "build_dashboard_data.py").read_text()
    try:
        tree = ast.parse(legacy_generator)
        main_function = next(
            node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main"
        )
    except (SyntaxError, StopIteration):
        return ["legacy_dashboard_generator_invalid"]
    if not main_function.body or not isinstance(main_function.body[0], ast.Raise):
        errors.append("legacy_dashboard_generator_not_quarantined")
    return errors


def claim_consistency_errors() -> list[str]:
    errors: list[str] = []
    for path in PUBLIC_CLAIM_SURFACES:
        text = path.read_text()
        for claim in QUARANTINED_CLAIMS:
            if claim.lower() in text.lower():
                errors.append(f"quarantined_claim:{path.relative_to(ROOT)}:{claim}")

    errors.extend(_legacy_generator_errors())
    try:
        payload = load_dashboard_payload()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"invalid_dashboard_payload:{exc}")
        return errors

    if payload.get("mode") != "portfolio":
        errors.append("dashboard_mode_must_be_portfolio")
    status = payload.get("data_status")
    if status not in PORTFOLIO_STATUSES:
        errors.append("dashboard_data_status_invalid")

    rows = payload.get("rows")
    buckets = payload.get("buckets")
    summary = payload.get("summary")
    if not isinstance(rows, list) or not isinstance(buckets, list) or not isinstance(summary, dict):
        errors.append("dashboard_primary_views_missing")
        return errors

    included = [row for row in rows if isinstance(row, dict) and row.get("inclusion_status") == "included"]
    excluded = [row for row in rows if isinstance(row, dict) and row.get("inclusion_status") == "excluded"]
    if int(summary.get("submitted_count", -1)) != len(rows):
        errors.append("dashboard_submitted_count_mismatch")
    if int(summary.get("included_count", -1)) != len(included):
        errors.append("dashboard_included_count_mismatch")
    if int(summary.get("excluded_count", -1)) != len(excluded):
        errors.append("dashboard_excluded_count_mismatch")

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"dashboard_row_not_object:{index}")
            continue
        if row.get("inclusion_status") not in {"included", "excluded"}:
            errors.append(f"dashboard_row_status_invalid:{index}")
        if row.get("inclusion_status") == "included":
            required = (
                "market_id",
                "source_url",
                "probability",
                "probability_timestamp",
                "resolution",
                "resolution_timestamp",
                "outcome_source",
            )
            missing = [field for field in required if row.get(field) is None]
            if missing:
                errors.append(f"dashboard_included_row_missing:{index}:{','.join(missing)}")
            probability_at = _parse_timestamp(row.get("probability_timestamp"))
            resolution_at = _parse_timestamp(row.get("resolution_timestamp"))
            if probability_at is None or resolution_at is None or probability_at >= resolution_at:
                errors.append(f"dashboard_included_row_not_pre_result:{index}")

    safe = payload.get("descriptive_claims_safe")
    boundary = str(payload.get("claim_boundary") or "").lower()
    message = str(payload.get("status_message") or "").lower()
    if status == "fixture_only":
        if safe is not False:
            errors.append("fixture_dashboard_must_mark_claims_unsafe")
        if "fixture" not in boundary or "synthetic" not in message:
            errors.append("fixture_dashboard_boundary_missing")
    elif status == "data_pending":
        if safe is not False or included:
            errors.append("data_pending_dashboard_cannot_publish_rows")
    elif status == "validated_real_sample":
        if safe is not True or not included:
            errors.append("validated_real_sample_requires_included_rows")
        if "bounded sample" not in boundary:
            errors.append("validated_real_sample_boundary_missing")
    return errors
