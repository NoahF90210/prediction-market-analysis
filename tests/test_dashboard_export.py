"""Honesty checks for the frozen broad-analysis dashboard payload."""

from __future__ import annotations

from src.rebuild.claims import claim_consistency_errors, load_dashboard_payload


def test_dashboard_uses_verified_real_analysis_status() -> None:
    payload = load_dashboard_payload()
    assert payload["data_status"] == "validated_real_sample"
    assert payload["summary"]["included_count"] == 75036
    assert payload["summary"]["event_count"] == 14678


def test_dashboard_exposes_primary_buckets_and_robustness() -> None:
    payload = load_dashboard_payload()
    assert len(payload["buckets"]) == 5
    assert sum(item["count"] for item in payload["buckets"]) == payload["summary"]["included_count"]
    assert payload["robustness"]["included_count"] == payload["summary"]["event_count"]
    assert payload["evidence_sample"]


def test_evidence_rows_include_auditable_public_fields() -> None:
    payload = load_dashboard_payload()
    required = {
        "market_id", "title", "probability", "resolution",
        "probability_timestamp", "resolution_timestamp", "market_url",
    }
    assert all(required <= row.keys() for row in payload["evidence_sample"])


def test_technical_values_are_secondary_to_main_summary() -> None:
    payload = load_dashboard_payload()
    assert "brier_score" in payload["summary"]
    assert "limitations" in payload
    assert "related markets" in " ".join(payload["limitations"]).lower()


def test_public_claim_surfaces_are_consistent() -> None:
    assert claim_consistency_errors() == []
