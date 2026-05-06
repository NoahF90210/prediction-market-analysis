from __future__ import annotations

import math

import pandas as pd

from src.accuracy import (
    add_baseline_columns,
    bootstrap_metric_ci,
    brier_score,
    calibration_table,
    last_non_trivial_probability,
    log_loss,
    baseline_comparison_table,
)


def sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "platform": "polymarket",
                "market_id": "m1",
                "title": "Market 1",
                "category": "sports",
                "open_time": "2025-01-01T00:00:00Z",
                "close_time": "2025-01-03T00:00:00Z",
                "resolution": "YES",
                "forecast_prob": 0.8,
                "forecast_source": "history",
                "volume": 150_000,
            },
            {
                "platform": "kalshi",
                "market_id": "m2",
                "title": "Market 2",
                "category": "sports",
                "open_time": "2025-01-01T00:00:00Z",
                "close_time": "2025-01-02T00:00:00Z",
                "resolution": "NO",
                "forecast_prob": 0.3,
                "forecast_source": "snapshot_fallback",
                "volume": 200_000,
            },
            {
                "platform": "polymarket",
                "market_id": "m3",
                "title": "Market 3",
                "category": "elections",
                "open_time": "2025-01-01T00:00:00Z",
                "close_time": "2025-02-10T00:00:00Z",
                "resolution": "NO",
                "forecast_prob": 0.2,
                "forecast_source": "history",
                "volume": 1_000_000,
            },
        ]
    )


def test_brier_score_matches_hand_calculation() -> None:
    probabilities = pd.Series([0.8, 0.3, 0.2])
    outcomes = pd.Series([1, 0, 0])
    expected = ((0.8 - 1) ** 2 + (0.3 - 0) ** 2 + (0.2 - 0) ** 2) / 3
    assert math.isclose(brier_score(probabilities, outcomes), expected)


def test_log_loss_matches_hand_calculation() -> None:
    probabilities = pd.Series([0.8, 0.3])
    outcomes = pd.Series([1, 0])
    expected = -((math.log(0.8) + math.log(0.7)) / 2)
    assert math.isclose(log_loss(probabilities, outcomes), expected)


def test_calibration_table_returns_expected_columns() -> None:
    calibration = calibration_table(sample_df(), bins=2)
    assert list(calibration.columns) == [
        "probability_bin",
        "n",
        "avg_forecast",
        "observed_yes_rate",
        "brier",
        "log_loss",
    ]
    assert calibration["n"].sum() == 3


def test_last_non_trivial_probability_skips_terminal_extremes() -> None:
    history = [{"p": 0.55}, {"p": 0.99}, {"p": 1.0}]
    assert last_non_trivial_probability(history, ("p",)) == 0.55


def test_last_non_trivial_probability_falls_back_to_last_price() -> None:
    history = [{"p": 0.0}, {"p": 1.0}]
    assert last_non_trivial_probability(history, ("p",)) == 1.0


def test_add_baseline_columns_adds_expected_benchmarks() -> None:
    scored = add_baseline_columns(sample_df())
    assert scored["baseline_prob_50"].eq(0.5).all()
    sports_rate = scored.loc[scored["category"] == "sports", "outcome"].mean()
    assert scored.loc[scored["category"] == "sports", "baseline_prob_category_rate"].eq(sports_rate).all()


def test_bootstrap_metric_ci_contains_point_estimate() -> None:
    probabilities = pd.Series([0.8, 0.3, 0.2, 0.7, 0.4])
    outcomes = pd.Series([1, 0, 0, 1, 0])
    point = brier_score(probabilities, outcomes)
    lower, upper = bootstrap_metric_ci(probabilities, outcomes, metric="brier", iterations=250, seed=7)
    assert lower <= point <= upper


def test_baseline_comparison_table_reports_improvement_columns() -> None:
    comparison = baseline_comparison_table(
        sample_df(),
        baseline_col="baseline_prob_50",
        baseline_label="always_50",
    )
    assert comparison.loc[0, "baseline"] == "always_50"
    assert "brier_improvement" in comparison.columns
    assert "log_loss_improvement_pct" in comparison.columns
