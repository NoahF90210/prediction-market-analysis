"""Honesty checks for the compact portfolio dashboard payload."""

from __future__ import annotations

import pytest

from src.build_dashboard_data import main as legacy_dashboard_main
from src.rebuild.claims import claim_consistency_errors, load_dashboard_payload


def test_dashboard_uses_explicit_portfolio_data_status() -> None:
    payload = load_dashboard_payload()
    assert payload["mode"] == "portfolio"
    assert payload["data_status"] in {
        "fixture_only",
        "data_pending",
        "validated_real_sample",
    }


def test_default_dashboard_matches_the_verified_corpus_status() -> None:
    payload = load_dashboard_payload()
    if payload["data_status"] == "fixture_only":
        assert payload["descriptive_claims_safe"] is False
        assert "synthetic" in payload["status_message"].lower()
        assert "fixture" in payload["claim_boundary"].lower()
    else:
        assert payload["data_status"] == "validated_real_sample"
        assert payload["descriptive_claims_safe"] is True
        assert payload["summary"]["included_count"] > 0
        assert "bounded sample" in payload["claim_boundary"].lower()


def test_dashboard_exposes_the_three_primary_views() -> None:
    payload = load_dashboard_payload()
    assert len(payload["buckets"]) == 5
    assert payload["summary"]["submitted_count"] == len(payload["rows"])
    assert {
        "included_count",
        "excluded_count",
        "coverage_rate",
        "directional_hit_rate",
    } <= payload["summary"].keys()
    assert payload["rows"]


def test_market_table_rows_include_auditable_public_fields() -> None:
    payload = load_dashboard_payload()
    included = [row for row in payload["rows"] if row["inclusion_status"] == "included"]
    assert included
    required = {
        "probability",
        "outcome",
        "probability_timestamp",
        "platform",
        "title",
        "source_url",
        "resolution_timestamp",
        "outcome_source",
        "inclusion_status",
    }
    assert all(required <= row.keys() for row in included)


def test_advanced_methodology_is_isolated_to_optional_appendix() -> None:
    payload = load_dashboard_payload()
    assert "technical_appendix" in payload
    assert "brier_score" in payload["technical_appendix"]
    assert "brier" not in payload["summary"]
    assert "log_loss" not in payload["summary"]


def test_legacy_result_generator_is_runtime_quarantined() -> None:
    with pytest.raises(RuntimeError, match="Legacy dashboard result generation is quarantined"):
        legacy_dashboard_main()


def test_public_claim_surfaces_are_consistent() -> None:
    assert claim_consistency_errors() == []
