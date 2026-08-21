from __future__ import annotations

import math

import pytest

from src.rebuild.evaluation import (
    add_required_baselines,
    apply_contract_selection,
    evaluation_summary,
    event_clustered_bootstrap_interval,
    event_weighted_metrics,
    rows_at_staleness_threshold,
    temporal_event_group_folds,
)
from src.rebuild.pipeline import (
    EVALUATION_SCHEMA,
    build_fixture_analysis,
    evaluation_consistency_errors,
    validate_schema,
)
from src.rebuild.protocol import load_protocol


def _included_fixture_rows():
    rows, _ = build_fixture_analysis()
    return [row for row in rows if row["inclusion_status"] == "included"]


def test_event_weighted_brier_matches_event_level_hand_calculation() -> None:
    rows = _included_fixture_rows()
    metrics = event_weighted_metrics(rows)

    # Four independent platform/event groups. The two paired events each count once.
    expected_event_losses = [
        ((0.72 - 1) ** 2 + (0.28 - 0) ** 2) / 2,
        (0.40 - 0) ** 2,
        (0.65 - 1) ** 2,
        ((0.58 - 1) ** 2 + (0.42 - 0) ** 2) / 2,
    ]
    assert metrics["contract_count"] == 6
    assert metrics["event_count"] == 4
    assert metrics["brier"] == pytest.approx(sum(expected_event_losses) / 4)


def test_clustered_interval_resamples_events_not_contract_rows() -> None:
    rows = _included_fixture_rows()
    lower, upper = event_clustered_bootstrap_interval(rows, iterations=500, seed=7)
    assert lower is not None and upper is not None
    assert lower <= event_weighted_metrics(rows)["brier"] <= upper


def test_prior_prevalence_uses_only_earlier_event_groups() -> None:
    rows = apply_contract_selection(_included_fixture_rows())
    baseline_rows = add_required_baselines(rows)
    first_by_platform_category = {}
    for row in sorted(baseline_rows, key=lambda item: item["forecast_target_at"]):
        key = (row["platform"], row["normalized_category"])
        first_by_platform_category.setdefault(key, row)
    assert first_by_platform_category
    assert all(
        row["baseline_prob_historical_prevalence"] == 0.5
        for row in first_by_platform_category.values()
    )

    # Sibling contracts in the same event receive the same prediction; neither sees the other's outcome.
    election = [row for row in baseline_rows if row["event_group_id"] == "pm-election-event"]
    assert len(election) == 2
    assert election[0]["baseline_prob_historical_prevalence"] == election[1]["baseline_prob_historical_prevalence"]


def test_temporal_folds_keep_groups_intact_and_train_strictly_before_test() -> None:
    rows = _included_fixture_rows()
    folds = temporal_event_group_folds(rows, n_splits=2, min_train_events=2)
    assert folds
    for train, test in folds:
        train_groups = {(rows[index]["platform"], rows[index]["event_group_id"]) for index in train}
        test_groups = {(rows[index]["platform"], rows[index]["event_group_id"]) for index in test}
        assert train_groups.isdisjoint(test_groups)
        assert max(rows[index]["forecast_target_at"] for index in train) < min(
            rows[index]["forecast_target_at"] for index in test
        )


def test_staleness_sensitivity_can_admit_only_staleness_failures() -> None:
    all_rows, _ = build_fixture_analysis()
    six_hours = rows_at_staleness_threshold(all_rows, 6 * 3600)
    seventy_two_hours = rows_at_staleness_threshold(all_rows, 72 * 3600)
    assert "pm-stale-snapshot" not in {row["market_id"] for row in six_hours}
    assert "pm-stale-snapshot" in {row["market_id"] for row in seventy_two_hours}
    assert "pm-conditional" not in {row["market_id"] for row in seventy_two_hours}
    assert "KXMVEFIXTURE-PARLAY" not in {row["market_id"] for row in seventy_two_hours}


def test_one_contract_sensitivity_is_predeclared_and_deterministic() -> None:
    selected = apply_contract_selection(
        _included_fixture_rows(),
        policy="one_contract_lexicographic_market_id",
    )
    ids = {row["market_id"] for row in selected}
    assert "pm-election-a" in ids
    assert "pm-election-b" not in ids
    assert "KXFIXTURETENNIS-A" in ids
    assert "KXFIXTURETENNIS-B" not in ids
    assert all(math.isclose(row["event_weight"], 1.0) for row in selected)


def test_fixture_summary_is_explicitly_non_publishable() -> None:
    rows, _ = build_fixture_analysis()
    summary = evaluation_summary(
        rows,
        protocol=load_protocol(),
        corpus_kind="fixture",
        bootstrap_iterations=100,
    )
    assert summary["validation_status"] == "fixture_only"
    assert summary["contract_count"] == 6
    assert summary["event_count"] == 4
    assert all(platform["comparison_scope"] == "descriptive_only" for platform in summary["platforms"])


def test_evaluation_schema_and_consistency_reject_incomplete_summary() -> None:
    invalid = {
        "schema_version": "1.0.0",
        "protocol_id": load_protocol().protocol_id,
        "build_id": "a" * 64,
        "validation_status": "blocked",
        "contract_count": 1,
        "event_count": 1,
        "platforms": [{
            "platform": "polymarket",
            "contract_count": 1,
            "event_count": 1,
            "brier": -123.0,
            "log_loss": 0.1,
            "brier_ci": [0.1, 0.2],
            "log_loss_ci": [0.1, 0.2],
            "baseline_50_brier": 0.25,
            "historical_prevalence_brier": 0.25,
            "comparison_scope": "descriptive_only",
        }],
        "sensitivities": [],
    }
    assert validate_schema(invalid, EVALUATION_SCHEMA)
    assert evaluation_consistency_errors(invalid, load_protocol())


def test_small_real_corpus_cannot_be_labeled_validated_by_caller() -> None:
    rows, _ = build_fixture_analysis()
    real_rows = [dict(row, collector_commit="real-collector-fingerprint") for row in rows]
    summary = evaluation_summary(
        real_rows,
        protocol=load_protocol(),
        corpus_kind="real",
        bootstrap_iterations=50,
    )
    assert summary["validation_status"] == "blocked"
