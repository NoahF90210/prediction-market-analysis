from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from src.rebuild.protocol import Protocol, parse_utc

EPSILON = 1e-6


def _frame(rows: Iterable[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(list(rows))
    if frame.empty:
        return frame
    frame["yes_probability"] = pd.to_numeric(frame["yes_probability"], errors="coerce")
    frame["snapshot_staleness_seconds"] = pd.to_numeric(
        frame["snapshot_staleness_seconds"], errors="coerce"
    )
    frame["outcome"] = frame["resolution"].map({"YES": 1.0, "NO": 0.0})
    frame["event_weight"] = pd.to_numeric(frame["event_weight"], errors="coerce").fillna(0.0)
    return frame


def _log_loss_series(probability: pd.Series, outcome: pd.Series) -> pd.Series:
    clipped = probability.clip(EPSILON, 1 - EPSILON)
    return -(outcome * np.log(clipped) + (1 - outcome) * np.log(1 - clipped))


def apply_contract_selection(
    rows: Iterable[dict[str, Any]],
    *,
    policy: str = "event_total_weight",
) -> list[dict[str, Any]]:
    included = [dict(row) for row in rows if row.get("inclusion_status") == "included"]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in included:
        grouped[(str(row["platform"]), str(row["event_group_id"]))].append(row)

    selected: list[dict[str, Any]] = []
    for group_rows in grouped.values():
        ordered = sorted(group_rows, key=lambda row: str(row["market_id"]))
        if policy == "event_total_weight":
            weight = 1.0 / len(ordered)
            for row in ordered:
                row["event_weight"] = weight
                selected.append(row)
        elif policy == "one_contract_lexicographic_market_id":
            row = ordered[0]
            row["event_weight"] = 1.0
            selected.append(row)
        else:
            raise ValueError(f"Unsupported contract-selection policy: {policy}")
    return sorted(selected, key=lambda row: (row["platform"], row["event_group_id"], row["market_id"]))


def event_loss_table(
    rows: Iterable[dict[str, Any]],
    *,
    probability_column: str = "yes_probability",
) -> pd.DataFrame:
    frame = _frame(rows)
    if frame.empty:
        return pd.DataFrame(
            columns=["platform", "event_group_id", "contract_count", "brier", "log_loss"]
        )
    frame = frame[
        frame[probability_column].notna()
        & frame["outcome"].notna()
        & frame["event_weight"].gt(0)
    ].copy()
    if frame.empty:
        return pd.DataFrame(
            columns=["platform", "event_group_id", "contract_count", "brier", "log_loss"]
        )
    frame["brier_loss"] = (frame[probability_column] - frame["outcome"]) ** 2
    frame["log_loss_value"] = _log_loss_series(frame[probability_column], frame["outcome"])

    event_rows: list[dict[str, Any]] = []
    for (platform, event_group_id), group in frame.groupby(
        ["platform", "event_group_id"], sort=True, observed=True
    ):
        weights = group["event_weight"].astype(float)
        weights = weights / weights.sum()
        event_rows.append(
            {
                "platform": platform,
                "event_group_id": event_group_id,
                "contract_count": int(len(group)),
                "brier": float(np.average(group["brier_loss"], weights=weights)),
                "log_loss": float(np.average(group["log_loss_value"], weights=weights)),
            }
        )
    return pd.DataFrame(event_rows)


def event_weighted_metrics(
    rows: Iterable[dict[str, Any]],
    *,
    probability_column: str = "yes_probability",
) -> dict[str, Any]:
    event_losses = event_loss_table(rows, probability_column=probability_column)
    if event_losses.empty:
        return {
            "contract_count": 0,
            "event_count": 0,
            "brier": None,
            "log_loss": None,
        }
    return {
        "contract_count": int(event_losses["contract_count"].sum()),
        "event_count": int(len(event_losses)),
        "brier": float(event_losses["brier"].mean()),
        "log_loss": float(event_losses["log_loss"].mean()),
    }


def event_clustered_bootstrap_interval(
    rows: Iterable[dict[str, Any]],
    *,
    metric: str = "brier",
    probability_column: str = "yes_probability",
    iterations: int = 2_000,
    confidence: float = 0.95,
    seed: int = 42,
) -> tuple[float | None, float | None]:
    event_losses = event_loss_table(rows, probability_column=probability_column)
    if event_losses.empty:
        return None, None
    if metric not in {"brier", "log_loss"}:
        raise ValueError(f"Unsupported metric: {metric}")
    values = event_losses[metric].to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    draws = np.empty(iterations, dtype=float)
    for index in range(iterations):
        sampled = rng.integers(0, len(values), size=len(values))
        draws[index] = float(values[sampled].mean())
    alpha = 1 - confidence
    return (
        float(np.quantile(draws, alpha / 2)),
        float(np.quantile(draws, 1 - alpha / 2)),
    )


def add_required_baselines(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = [dict(row) for row in rows]
    for row in selected:
        row["baseline_prob_50"] = 0.5
        row["baseline_prob_historical_prevalence"] = 0.5

    event_blocks: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in selected:
        event_blocks[(str(row["platform"]), str(row["event_group_id"]))].append(row)

    ordered_blocks = sorted(
        event_blocks.values(),
        key=lambda block: (
            min(parse_utc(row.get("forecast_target_at")) for row in block if parse_utc(row.get("forecast_target_at")) is not None),
            str(block[0]["platform"]),
            str(block[0]["event_group_id"]),
        ),
    )
    prior_sum: dict[tuple[str, str], float] = defaultdict(float)
    prior_count: dict[tuple[str, str], int] = defaultdict(int)

    by_timestamp: dict[Any, list[list[dict[str, Any]]]] = defaultdict(list)
    for block in ordered_blocks:
        target = min(
            parse_utc(row.get("forecast_target_at"))
            for row in block
            if parse_utc(row.get("forecast_target_at")) is not None
        )
        by_timestamp[target].append(block)

    for timestamp in sorted(by_timestamp):
        blocks = by_timestamp[timestamp]
        for block in blocks:
            for row in block:
                key = (str(row["platform"]), str(row["normalized_category"]))
                if prior_count[key]:
                    row["baseline_prob_historical_prevalence"] = prior_sum[key] / prior_count[key]
        event_updates: dict[tuple[str, str], list[float]] = defaultdict(list)
        for block in blocks:
            category_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
            for row in block:
                category_groups[(str(row["platform"]), str(row["normalized_category"]))].append(row)
            for key, category_rows in category_groups.items():
                weights = np.array([float(row["event_weight"]) for row in category_rows], dtype=float)
                outcomes = np.array([1.0 if row["resolution"] == "YES" else 0.0 for row in category_rows])
                if weights.sum() <= 0:
                    continue
                event_updates[key].append(float(np.average(outcomes, weights=weights)))
        for key, outcomes in event_updates.items():
            prior_sum[key] += float(np.mean(outcomes))
            prior_count[key] += 1
    return selected


def temporal_event_group_folds(
    rows: Sequence[dict[str, Any]],
    *,
    n_splits: int = 3,
    min_train_events: int = 2,
) -> list[tuple[list[int], list[int]]]:
    if n_splits < 1:
        raise ValueError("n_splits must be positive")
    indexed_groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        indexed_groups[(str(row["platform"]), str(row["event_group_id"]))].append(index)
    ordered_groups = sorted(
        indexed_groups,
        key=lambda key: (
            min(
                parse_utc(rows[index].get("forecast_target_at"))
                for index in indexed_groups[key]
                if parse_utc(rows[index].get("forecast_target_at")) is not None
            ),
            key,
        ),
    )
    if len(ordered_groups) <= min_train_events:
        return []
    remaining = len(ordered_groups) - min_train_events
    block_size = max(1, math.ceil(remaining / n_splits))
    folds: list[tuple[list[int], list[int]]] = []
    for start in range(min_train_events, len(ordered_groups), block_size):
        test_groups = ordered_groups[start : start + block_size]
        train_groups = ordered_groups[:start]
        train_indices = sorted(index for key in train_groups for index in indexed_groups[key])
        test_indices = sorted(index for key in test_groups for index in indexed_groups[key])
        if train_indices and test_indices:
            folds.append((train_indices, test_indices))
    return folds[:n_splits]


def rows_at_staleness_threshold(
    rows: Iterable[dict[str, Any]],
    threshold_seconds: int,
) -> list[dict[str, Any]]:
    eligible: list[dict[str, Any]] = []
    for original in rows:
        row = dict(original)
        reasons = set(row.get("exclusion_reasons") or [])
        non_staleness_reasons = reasons - {"snapshot_too_stale"}
        staleness = row.get("snapshot_staleness_seconds")
        if non_staleness_reasons or staleness is None or float(staleness) > threshold_seconds:
            continue
        row["inclusion_status"] = "included"
        row["exclusion_reasons"] = []
        eligible.append(row)
    return apply_contract_selection(eligible, policy="event_total_weight")


def sensitivity_table(rows: Iterable[dict[str, Any]], protocol: Protocol) -> list[dict[str, Any]]:
    materialized = list(rows)
    results: list[dict[str, Any]] = []
    policies = (
        protocol.payload["contract_selection"]["primary_policy"],
        protocol.payload["contract_selection"]["sensitivity_policy"],
    )
    for threshold in protocol.payload["snapshot_staleness_sensitivity_seconds"]:
        threshold_rows = rows_at_staleness_threshold(materialized, int(threshold))
        for policy in policies:
            selected = apply_contract_selection(threshold_rows, policy=policy)
            metrics = event_weighted_metrics(selected)
            results.append(
                {
                    "max_snapshot_staleness_seconds": int(threshold),
                    "contract_selection_policy": policy,
                    **metrics,
                }
            )
    return results


def publication_status(
    *,
    corpus_kind: str,
    rows: Iterable[dict[str, Any]] | None = None,
    protocol: Protocol | None = None,
) -> str:
    if corpus_kind == "fixture":
        return "fixture_only"
    if corpus_kind == "real":
        materialized = list(rows or [])
        if protocol is None:
            raise ValueError("protocol is required for real publication status")
        included_events = {
            (str(row["platform"]), str(row["event_group_id"]))
            for row in materialized
            if row.get("inclusion_status") == "included"
        }
        minimum = int(protocol.payload["publication_gate"]["minimum_events_per_platform"])
        platforms = tuple(protocol.payload["platforms"])
        if any(
            sum(1 for platform, _ in included_events if platform == expected) < minimum
            for expected in platforms
        ):
            return "blocked"
        return "validated_real_sample"
    raise ValueError("corpus_kind must be 'fixture' or 'real'")


def evaluation_summary(
    rows: Iterable[dict[str, Any]],
    *,
    protocol: Protocol,
    corpus_kind: str,
    bootstrap_iterations: int = 2_000,
) -> dict[str, Any]:
    materialized = list(rows)
    validation_status = publication_status(corpus_kind=corpus_kind, rows=materialized, protocol=protocol)
    primary = apply_contract_selection(materialized, policy=protocol.payload["contract_selection"]["primary_policy"])
    with_baselines = add_required_baselines(primary)
    platforms: list[dict[str, Any]] = []
    for platform in protocol.payload["platforms"]:
        platform_rows = [row for row in with_baselines if row["platform"] == platform]
        market = event_weighted_metrics(platform_rows)
        baseline_50 = event_weighted_metrics(platform_rows, probability_column="baseline_prob_50")
        baseline_prevalence = event_weighted_metrics(
            platform_rows,
            probability_column="baseline_prob_historical_prevalence",
        )
        brier_ci = event_clustered_bootstrap_interval(
            platform_rows,
            metric="brier",
            iterations=bootstrap_iterations,
        )
        log_loss_ci = event_clustered_bootstrap_interval(
            platform_rows,
            metric="log_loss",
            iterations=bootstrap_iterations,
        )
        platforms.append(
            {
                "platform": platform,
                **market,
                "brier_ci": list(brier_ci),
                "log_loss_ci": list(log_loss_ci),
                "baseline_50_brier": baseline_50["brier"],
                "historical_prevalence_brier": baseline_prevalence["brier"],
                "comparison_scope": "descriptive_only",
            }
        )

    event_keys = {(row["platform"], row["event_group_id"]) for row in primary}
    build_ids = {str(row["build_id"]) for row in materialized}
    if len(build_ids) != 1:
        raise ValueError("Evaluation rows must share one deterministic build_id")
    return {
        "schema_version": "1.0.0",
        "protocol_id": protocol.protocol_id,
        "build_id": next(iter(build_ids)),
        "validation_status": validation_status,
        "contract_count": len(primary),
        "event_count": len(event_keys),
        "platforms": platforms,
        "sensitivities": sensitivity_table(materialized, protocol),
    }
