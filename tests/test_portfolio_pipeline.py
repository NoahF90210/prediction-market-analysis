from __future__ import annotations

import json
from pathlib import Path

from src.portfolio.pipeline import build_fixture_portfolio, build_portfolio, validate_portfolio_row


def _valid_row(**overrides):
    row = {
        "platform": "polymarket",
        "market_id": "real-market-1",
        "event_id": "real-event-1",
        "title": "Will the bounded example resolve YES?",
        "source_url": "https://example.com/markets/real-market-1",
        "source_endpoint": "https://api.example.com/markets/real-market-1",
        "probability": 0.64,
        "probability_timestamp": "2026-06-01T12:00:00Z",
        "outcome": "YES",
        "resolution_timestamp": "2026-06-02T12:00:00Z",
        "outcome_source": "https://example.com/resolutions/real-market-1",
        "retrieved_at": "2026-06-03T12:00:00Z",
    }
    row.update(overrides)
    return row


def _write_input(path: Path, rows) -> Path:
    path.write_text(json.dumps({"scope": "Test-bounded normalized sample.", "rows": rows}))
    return path


def test_fixture_portfolio_is_byte_deterministic(tmp_path: Path) -> None:
    first_output = tmp_path / "first"
    second_output = tmp_path / "second"
    first_dashboard = tmp_path / "first.js"
    second_dashboard = tmp_path / "second.js"

    _, first_payload, first_paths = build_fixture_portfolio(
        output_dir=first_output,
        dashboard_output=first_dashboard,
    )
    _, second_payload, second_paths = build_fixture_portfolio(
        output_dir=second_output,
        dashboard_output=second_dashboard,
    )

    assert first_payload == second_payload
    for key in ("rows_json", "rows_csv", "summary"):
        assert first_paths[key].read_bytes() == second_paths[key].read_bytes()
    assert first_dashboard.read_bytes() == second_dashboard.read_bytes()
    assert first_payload["data_status"] == "fixture_only"
    assert first_payload["descriptive_claims_safe"] is False


def test_valid_real_input_becomes_bounded_validated_sample(tmp_path: Path) -> None:
    input_path = _write_input(tmp_path / "real.json", [_valid_row()])
    rows, payload, _ = build_portfolio(
        input_path,
        corpus_kind="real",
        output_dir=tmp_path / "output",
        dashboard_output=None,
    )
    assert rows[0]["inclusion_status"] == "included"
    assert rows[0]["source_url"].startswith("https://")
    assert rows[0]["probability_timestamp"] < rows[0]["resolution_timestamp"]
    assert payload["data_status"] == "validated_real_sample"
    assert payload["summary"]["coverage_rate"] == 1.0
    assert payload["descriptive_claims_safe"] is True


def test_malformed_row_fails_closed(tmp_path: Path) -> None:
    input_path = _write_input(tmp_path / "malformed.json", ["not-an-object"])
    rows, payload, _ = build_portfolio(
        input_path,
        corpus_kind="real",
        output_dir=tmp_path / "output",
        dashboard_output=None,
    )
    assert rows[0]["inclusion_status"] == "excluded"
    assert "malformed_row" in rows[0]["exclusion_reasons"]
    assert payload["data_status"] == "data_pending"


def test_missing_timestamps_fail_closed(tmp_path: Path) -> None:
    input_path = _write_input(
        tmp_path / "missing-timestamps.json",
        [_valid_row(probability_timestamp=None, resolution_timestamp=None)],
    )
    rows, _, _ = build_portfolio(
        input_path,
        corpus_kind="real",
        output_dir=tmp_path / "output",
        dashboard_output=None,
    )
    assert rows[0]["inclusion_status"] == "excluded"
    assert "missing_probability_timestamp" in rows[0]["exclusion_reasons"]
    assert "missing_resolution_timestamp" in rows[0]["exclusion_reasons"]


def test_post_result_probability_fails_closed(tmp_path: Path) -> None:
    input_path = _write_input(
        tmp_path / "post-result.json",
        [_valid_row(probability_timestamp="2026-06-03T12:00:00Z")],
    )
    rows, _, _ = build_portfolio(
        input_path,
        corpus_kind="real",
        output_dir=tmp_path / "output",
        dashboard_output=None,
    )
    assert rows[0]["inclusion_status"] == "excluded"
    assert rows[0]["exclusion_reasons"] == ["post_result_probability"]


def test_invalid_probability_fails_closed(tmp_path: Path) -> None:
    input_path = _write_input(tmp_path / "invalid-probability.json", [_valid_row(probability=1.5)])
    rows, _, _ = build_portfolio(
        input_path,
        corpus_kind="real",
        output_dir=tmp_path / "output",
        dashboard_output=None,
    )
    assert rows[0]["inclusion_status"] == "excluded"
    assert "missing_or_invalid_probability" in rows[0]["exclusion_reasons"]


def test_missing_outcome_fails_closed(tmp_path: Path) -> None:
    input_path = _write_input(tmp_path / "missing-outcome.json", [_valid_row(outcome=None)])
    rows, _, _ = build_portfolio(
        input_path,
        corpus_kind="real",
        output_dir=tmp_path / "output",
        dashboard_output=None,
    )
    assert rows[0]["inclusion_status"] == "excluded"
    assert "missing_outcome" in rows[0]["exclusion_reasons"]


def test_duplicate_market_ids_are_all_excluded(tmp_path: Path) -> None:
    input_path = _write_input(
        tmp_path / "duplicates.json",
        [_valid_row(), _valid_row(title="Duplicate definition")],
    )
    rows, payload, _ = build_portfolio(
        input_path,
        corpus_kind="real",
        output_dir=tmp_path / "output",
        dashboard_output=None,
    )
    assert all(row["inclusion_status"] == "excluded" for row in rows)
    assert all("duplicate_market_id" in row["exclusion_reasons"] for row in rows)
    assert payload["data_status"] == "data_pending"


def test_fixture_analysis_is_plain_and_coverage_explicit(tmp_path: Path) -> None:
    _, payload, _ = build_fixture_portfolio(
        output_dir=tmp_path / "output",
        dashboard_output=None,
    )
    assert [bucket["label"] for bucket in payload["buckets"]] == [
        "0–20%",
        "20–40%",
        "40–60%",
        "60–80%",
        "80–100%",
    ]
    assert sum(bucket["count"] for bucket in payload["buckets"]) == 8
    assert payload["summary"]["submitted_count"] == 10
    assert payload["summary"]["included_count"] == 8
    assert payload["summary"]["coverage_rate"] == 0.8
    assert payload["summary"]["directional_threshold"] == 0.5
    assert payload["technical_appendix"]["always_50_brier"] == 0.25
    assert "fixture" in payload["claim_boundary"].lower()


def test_all_portfolio_rows_match_the_schema(tmp_path: Path) -> None:
    rows, _, _ = build_fixture_portfolio(
        output_dir=tmp_path / "output",
        dashboard_output=None,
    )
    assert all(validate_portfolio_row(row) == [] for row in rows)
