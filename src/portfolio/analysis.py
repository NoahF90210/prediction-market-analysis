from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

BUCKETS = (
    (0.0, 0.2, "0–20%"),
    (0.2, 0.4, "20–40%"),
    (0.4, 0.6, "40–60%"),
    (0.6, 0.8, "60–80%"),
    (0.8, 1.0, "80–100%"),
)


def _included(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("inclusion_status") == "included"]


def probability_buckets(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    included = _included(rows)
    buckets: list[dict[str, Any]] = []
    for lower, upper, label in BUCKETS:
        selected = [
            row
            for row in included
            if float(row["probability"]) >= lower
            and (float(row["probability"]) < upper or (upper == 1.0 and float(row["probability"]) <= 1.0))
        ]
        count = len(selected)
        buckets.append(
            {
                "label": label,
                "lower": lower,
                "upper": upper,
                "count": count,
                "average_probability": (
                    sum(float(row["probability"]) for row in selected) / count if count else None
                ),
                "observed_yes_rate": (
                    sum(int(row["outcome"]) for row in selected) / count if count else None
                ),
            }
        )
    return buckets


def simple_summary(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    materialized = list(rows)
    included = _included(materialized)
    submitted_count = len(materialized)
    included_count = len(included)
    correct = sum(
        1
        for row in included
        if (float(row["probability"]) >= 0.5 and int(row["outcome"]) == 1)
        or (float(row["probability"]) < 0.5 and int(row["outcome"]) == 0)
    )
    reason_counts = Counter(
        reason
        for row in materialized
        for reason in row.get("exclusion_reasons") or []
    )
    return {
        "submitted_count": submitted_count,
        "included_count": included_count,
        "excluded_count": submitted_count - included_count,
        "coverage_rate": included_count / submitted_count if submitted_count else 0.0,
        "directional_hit_rate": correct / included_count if included_count else None,
        "directional_threshold": 0.5,
        "average_probability": (
            sum(float(row["probability"]) for row in included) / included_count
            if included_count
            else None
        ),
        "observed_yes_rate": (
            sum(int(row["outcome"]) for row in included) / included_count
            if included_count
            else None
        ),
        "missing_data": [
            {"reason": reason, "count": count}
            for reason, count in sorted(reason_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
    }


def technical_summary(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    included = _included(rows)
    if not included:
        return {
            "brier_score": None,
            "always_50_brier": None,
            "explanation": "Brier score is kept in the optional appendix and is unavailable without included rows.",
        }
    brier = sum(
        (float(row["probability"]) - int(row["outcome"])) ** 2
        for row in included
    ) / len(included)
    return {
        "brier_score": brier,
        "always_50_brier": 0.25,
        "explanation": (
            "Brier score is the average squared distance between a probability and the final 0/1 outcome. "
            "Lower is better; always predicting 50% scores 0.25 on any binary sample."
        ),
    }


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"{row.get('platform') or 'unknown'}:{row.get('market_id') or row['input_row_number']}",
        "platform": row.get("platform"),
        "market_id": row.get("market_id"),
        "title": row.get("title"),
        "source_url": row.get("source_url"),
        "probability": row.get("probability"),
        "probability_timestamp": row.get("probability_timestamp"),
        "resolution": row.get("resolution"),
        "outcome": row.get("outcome"),
        "resolution_timestamp": row.get("resolution_timestamp"),
        "outcome_source": row.get("outcome_source"),
        "inclusion_status": row.get("inclusion_status"),
        "exclusion_reasons": row.get("exclusion_reasons") or [],
    }


def build_dashboard_payload(
    rows: Iterable[dict[str, Any]],
    *,
    corpus_kind: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    materialized = list(rows)
    included_count = len(_included(materialized))
    if corpus_kind == "fixture":
        data_status = "fixture_only"
        status_message = (
            "The dashboard is using synthetic software-test rows. The layout and calculations work, "
            "but these values are not empirical findings."
        )
        claim_boundary = "Do not use fixture probabilities, outcomes, or summary values as evidence about prediction markets."
        descriptive_claims_safe = False
    elif corpus_kind == "real" and included_count:
        data_status = "validated_real_sample"
        status_message = (
            "This is a bounded, contract-validated real sample. Results describe only the included rows "
            "and do not establish platform superiority or a trading edge."
        )
        claim_boundary = "Descriptive claims are limited to this bounded sample; no population, causal, platform-ranking, or market-edge claim is supported."
        descriptive_claims_safe = True
    elif corpus_kind == "real":
        data_status = "data_pending"
        status_message = "No supplied real row passed the fail-closed inclusion checks, so no result is shown."
        claim_boundary = "No empirical accuracy claim is supported until at least one real row passes every required field and timestamp check."
        descriptive_claims_safe = False
    else:
        raise ValueError("corpus_kind must be 'fixture' or 'real'")

    return {
        "mode": "portfolio",
        "data_status": data_status,
        "descriptive_claims_safe": descriptive_claims_safe,
        "question": "Were pre-result prediction-market probabilities informative about what happened?",
        "scope": metadata["scope"],
        "status_message": status_message,
        "claim_boundary": claim_boundary,
        "build_id": metadata["build_id"],
        "source": {
            "name": metadata["source_name"],
            "sha256": metadata["source_sha256"],
            "platform_boundary": "Polymarket normalized import only",
        },
        "method": {
            "bucket_definition": "Five fixed probability ranges from 0% to 100%.",
            "observed_rate": "Within each range, the share of included markets that resolved YES.",
            "hit_rate": "A simple direction check: probabilities of 50% or more predict YES; lower probabilities predict NO.",
            "coverage": "Included rows divided by all submitted rows. Invalid or incomplete rows remain visible as excluded.",
        },
        "buckets": probability_buckets(materialized),
        "summary": simple_summary(materialized),
        "rows": [_public_row(row) for row in materialized],
        "technical_appendix": technical_summary(materialized),
    }
