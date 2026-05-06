"""
Shared helpers for building and scoring the prediction-market accuracy dataset.

The MVP intentionally scores only liquid, resolved binary sports/elections
markets. Forecast probability is the last non-trivial YES price before
resolution, so final settlement prices do not dominate the analysis.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

MIN_VOLUME = 100_000.0
VALID_CATEGORIES = {"sports", "elections"}
VALID_RESOLUTIONS = {"YES", "NO"}
NON_TRIVIAL_MIN = 0.02
NON_TRIVIAL_MAX = 0.98
EPSILON = 1e-6
BOOTSTRAP_ITERATIONS = 2_000

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "elections": [
        "election", "president", "senate", "congress", "governor",
        "parliament", "prime minister", "vote", "ballot", "primary",
        "referendum", "runoff", "mayor", "gubernatorial", "midterm",
        "democrat", "republican",
    ],
    "sports": [
        "nba", "nfl", "mlb", "nhl", "super bowl", "world series",
        "world cup", "champions league", "premier league", "la liga",
        "bundesliga", "serie a", "stanley cup", "playoffs",
        "championship", "finals", "tournament", "soccer", "football",
        "basketball", "baseball", "hockey", "tennis", "golf", "ufc",
        "mma", "boxing", "f1", "formula 1", "formula one", "cricket",
        "rugby", "olympics", "wimbledon", "masters", "grand slam",
        "counter-strike", "valorant", "league of legends", "dota",
        "esports", "cs2", "lol", "overwatch",
    ],
}


def classify_category(text: str | None) -> str | None:
    text_lower = (text or "").lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in text_lower for keyword in keywords):
            return category
    return None


def to_float(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        if isinstance(value, str):
            value = value.strip().replace("$", "").replace(",", "")
            if not value:
                return None
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_probability(value) -> float | None:
    p = to_float(value)
    if p is None:
        return None
    if 1 < p <= 100:
        p = p / 100
    if 0 <= p <= 1:
        return p
    return None


def normalize_resolution(value) -> str | None:
    result = str(value or "").strip().upper()
    return result if result in VALID_RESOLUTIONS else None


def last_non_trivial_probability(
    history: Iterable[dict],
    price_keys: tuple[str, ...] = ("p", "yes_price", "yes_price_dollars", "price"),
) -> float | None:
    prices: list[float] = []
    for point in history:
        for key in price_keys:
            if key in point:
                p = normalize_probability(point.get(key))
                if p is not None:
                    prices.append(p)
                    break
    for p in reversed(prices):
        if NON_TRIVIAL_MIN <= p <= NON_TRIVIAL_MAX:
            return p
    return prices[-1] if prices else None


def load_json(path: Path):
    with path.open() as f:
        return json.load(f)


def brier_score(probabilities: pd.Series, outcomes: pd.Series) -> float:
    return float(((probabilities - outcomes) ** 2).mean())


def log_loss(probabilities: pd.Series, outcomes: pd.Series) -> float:
    clipped = probabilities.clip(EPSILON, 1 - EPSILON)
    return float((-(outcomes * clipped.map(math.log) + (1 - outcomes) * (1 - clipped).map(math.log))).mean())


def duration_bucket(days: float) -> str:
    if pd.isna(days):
        return "unknown"
    if days < 1:
        return "<1 day"
    if days < 7:
        return "1-7 days"
    if days < 30:
        return "7-30 days"
    return "30+ days"


def volume_bucket(volume: float) -> str:
    if pd.isna(volume):
        return "unknown"
    if volume < 250_000:
        return "$100k-$250k"
    if volume < 1_000_000:
        return "$250k-$1m"
    if volume < 5_000_000:
        return "$1m-$5m"
    return "$5m+"


def add_score_columns(df: pd.DataFrame) -> pd.DataFrame:
    scored = df.copy()
    scored["open_time"] = pd.to_datetime(scored["open_time"], errors="coerce", utc=True)
    scored["close_time"] = pd.to_datetime(scored["close_time"], errors="coerce", utc=True)
    scored["outcome"] = (scored["resolution"] == "YES").astype(int)
    scored["brier"] = (scored["forecast_prob"] - scored["outcome"]) ** 2
    clipped = scored["forecast_prob"].clip(EPSILON, 1 - EPSILON)
    scored["log_loss"] = -(
        scored["outcome"] * clipped.map(math.log) +
        (1 - scored["outcome"]) * (1 - clipped).map(math.log)
    )
    scored["days_to_resolution"] = (
        (scored["close_time"] - scored["open_time"]).dt.total_seconds() / 86_400
    )
    scored["duration_bucket"] = scored["days_to_resolution"].map(duration_bucket)
    scored["volume_bucket"] = scored["volume"].map(volume_bucket)
    return scored


def add_baseline_columns(df: pd.DataFrame) -> pd.DataFrame:
    scored = add_score_columns(df)
    scored["baseline_prob_50"] = 0.5
    category_rates = (
        scored.groupby("category", observed=True)["outcome"]
        .mean()
        .to_dict()
    )
    scored["baseline_prob_category_rate"] = scored["category"].map(category_rates)
    return scored


def calibration_table(df: pd.DataFrame, bins: int = 10) -> pd.DataFrame:
    scored = add_score_columns(df)
    scored["probability_bin"] = pd.cut(
        scored["forecast_prob"],
        bins=[i / bins for i in range(bins + 1)],
        include_lowest=True,
    )
    return (
        scored.groupby("probability_bin", observed=True)
        .agg(
            n=("market_id", "count"),
            avg_forecast=("forecast_prob", "mean"),
            observed_yes_rate=("outcome", "mean"),
            brier=("brier", "mean"),
            log_loss=("log_loss", "mean"),
        )
        .reset_index()
    )


def metric_value(
    probabilities: pd.Series,
    outcomes: pd.Series,
    metric: str,
) -> float:
    if metric == "brier":
        return brier_score(probabilities, outcomes)
    if metric == "log_loss":
        return log_loss(probabilities, outcomes)
    raise ValueError(f"Unsupported metric: {metric}")


def bootstrap_metric_ci(
    probabilities: pd.Series,
    outcomes: pd.Series,
    metric: str = "brier",
    iterations: int = BOOTSTRAP_ITERATIONS,
    confidence: float = 0.95,
    seed: int = 42,
) -> tuple[float, float]:
    probs = pd.Series(probabilities).reset_index(drop=True)
    obs = pd.Series(outcomes).reset_index(drop=True)
    n = len(probs)
    if n == 0:
        return (float("nan"), float("nan"))

    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(iterations):
        indices = rng.integers(0, n, size=n)
        draws.append(metric_value(probs.iloc[indices], obs.iloc[indices], metric))

    alpha = 1 - confidence
    lower = float(np.quantile(draws, alpha / 2))
    upper = float(np.quantile(draws, 1 - alpha / 2))
    return lower, upper


def metric_ci_summary(
    df: pd.DataFrame,
    group_cols: list[str] | None = None,
    metrics: tuple[str, ...] = ("brier", "log_loss"),
    iterations: int = BOOTSTRAP_ITERATIONS,
    confidence: float = 0.95,
    seed: int = 42,
) -> pd.DataFrame:
    scored = add_score_columns(df)
    grouped = (
        [("overall", scored)]
        if not group_cols
        else list(scored.groupby(group_cols, observed=True))
    )

    rows: list[dict] = []
    for group_key, group_df in grouped:
        row: dict[str, object]
        if not group_cols:
            row = {"group": "overall"}
        else:
            if not isinstance(group_key, tuple):
                group_key = (group_key,)
            row = dict(zip(group_cols, group_key))
        row["n"] = len(group_df)
        for metric in metrics:
            point_estimate = metric_value(group_df["forecast_prob"], group_df["outcome"], metric)
            lower, upper = bootstrap_metric_ci(
                group_df["forecast_prob"],
                group_df["outcome"],
                metric=metric,
                iterations=iterations,
                confidence=confidence,
                seed=seed,
            )
            row[metric] = point_estimate
            row[f"{metric}_ci_lower"] = lower
            row[f"{metric}_ci_upper"] = upper
        rows.append(row)
    return pd.DataFrame(rows)


def baseline_comparison_table(
    df: pd.DataFrame,
    baseline_col: str,
    baseline_label: str,
    group_cols: list[str] | None = None,
    metrics: tuple[str, ...] = ("brier", "log_loss"),
) -> pd.DataFrame:
    scored = add_baseline_columns(df)
    grouped = (
        [("overall", scored)]
        if not group_cols
        else list(scored.groupby(group_cols, observed=True))
    )

    rows: list[dict] = []
    for group_key, group_df in grouped:
        row: dict[str, object]
        if not group_cols:
            row = {"group": "overall"}
        else:
            if not isinstance(group_key, tuple):
                group_key = (group_key,)
            row = dict(zip(group_cols, group_key))
        row["n"] = len(group_df)
        row["baseline"] = baseline_label
        for metric in metrics:
            market_score = metric_value(group_df["forecast_prob"], group_df["outcome"], metric)
            baseline_score = metric_value(group_df[baseline_col], group_df["outcome"], metric)
            row[f"{metric}_market"] = market_score
            row[f"{metric}_baseline"] = baseline_score
            row[f"{metric}_improvement"] = baseline_score - market_score
            row[f"{metric}_improvement_pct"] = (
                (baseline_score - market_score) / baseline_score
                if baseline_score
                else float("nan")
            )
        rows.append(row)
    return pd.DataFrame(rows)


def metric_summary(df: pd.DataFrame, group_cols: list[str] | None = None) -> pd.DataFrame:
    scored = add_score_columns(df)
    if not group_cols:
        return pd.DataFrame(
            [{
                "group": "overall",
                "n": len(scored),
                "brier": scored["brier"].mean(),
                "log_loss": scored["log_loss"].mean(),
                "avg_forecast": scored["forecast_prob"].mean(),
                "observed_yes_rate": scored["outcome"].mean(),
                "median_days_to_resolution": scored["days_to_resolution"].median(),
                "median_volume": scored["volume"].median(),
            }]
        )
    return (
        scored.groupby(group_cols, observed=True)
        .agg(
            n=("market_id", "count"),
            brier=("brier", "mean"),
            log_loss=("log_loss", "mean"),
            avg_forecast=("forecast_prob", "mean"),
            observed_yes_rate=("outcome", "mean"),
            median_days_to_resolution=("days_to_resolution", "median"),
            median_volume=("volume", "median"),
        )
        .reset_index()
    )


def apply_mvp_filters(df: pd.DataFrame, min_volume: float = MIN_VOLUME) -> pd.DataFrame:
    filtered = df.copy()
    filtered["category"] = filtered["category"].str.lower()
    filtered["resolution"] = filtered["resolution"].map(normalize_resolution)
    filtered["volume"] = pd.to_numeric(filtered["volume"], errors="coerce")
    filtered["forecast_prob"] = pd.to_numeric(filtered["forecast_prob"], errors="coerce")
    filtered = filtered[
        filtered["category"].isin(VALID_CATEGORIES)
        & filtered["resolution"].isin(VALID_RESOLUTIONS)
        & (filtered["volume"] >= min_volume)
        & filtered["forecast_prob"].between(0, 1)
    ]
    return filtered.reset_index(drop=True)
