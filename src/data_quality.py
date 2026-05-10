from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.forecast_snapshots import FORECAST_HORIZONS, PRIMARY_FORECAST_HORIZON
from src.settings import CLEAN_DIR

MIN_CATEGORY_N = 30
MIN_PLATFORM_CATEGORY_N = 30
CATEGORY_DROP_UNLESS_COMPARABLE = {"commodities", "geopolitics", "politics", "finance"}


def _horizon_column(base: str, horizon: str) -> str:
    return base if horizon == PRIMARY_FORECAST_HORIZON else f"{base}_{horizon}"


def category_eligibility(
    scored: pd.DataFrame,
    *,
    min_category_n: int = MIN_CATEGORY_N,
    min_platform_category_n: int = MIN_PLATFORM_CATEGORY_N,
) -> pd.DataFrame:
    if scored.empty:
        return pd.DataFrame(
            columns=[
                "category",
                "n",
                "n_kalshi",
                "n_polymarket",
                "share",
                "include_overall_category",
                "include_platform_comparison",
                "recommendation",
                "policy_note",
            ]
        )

    counts = (
        scored.groupby(["category", "platform"], observed=True)
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )
    for platform in ("kalshi", "polymarket"):
        if platform not in counts.columns:
            counts[platform] = 0

    counts["n"] = counts["kalshi"] + counts["polymarket"]
    counts["share"] = counts["n"] / len(scored)
    counts["include_overall_category"] = counts["n"] >= min_category_n
    counts["include_platform_comparison"] = (
        (counts["kalshi"] >= min_platform_category_n)
        & (counts["polymarket"] >= min_platform_category_n)
    )

    def recommendation(row: pd.Series) -> tuple[str, str]:
        category = str(row["category"])
        cross_platform = bool(row["include_platform_comparison"])
        descriptive = bool(row["include_overall_category"])

        if cross_platform:
            if category == "sports":
                return "include_for_cross_platform", "sports: both platforms meet n>=30"
            if category in {"crypto", "elections"}:
                return "include_for_cross_platform", f"{category}: upgraded from descriptive to cross-platform"
            return "include_for_cross_platform", "both platforms meet n>=30"

        if category in CATEGORY_DROP_UNLESS_COMPARABLE:
            return "drop_from_category_level_analysis", "policy: drop unless both platforms meet n>=30"

        if descriptive:
            if category in {"crypto", "elections"}:
                return "include_descriptively", "policy: descriptive only unless both platforms meet n>=30"
            return "include_descriptively", "overall category n>=30"

        return "drop_from_category_level_analysis", "insufficient sample"

    recs = counts.apply(recommendation, axis=1)
    counts["recommendation"] = recs.map(lambda item: item[0])
    counts["policy_note"] = recs.map(lambda item: item[1])

    counts = counts.rename(columns={"kalshi": "n_kalshi", "polymarket": "n_polymarket"})
    return counts[
        [
            "category",
            "n",
            "n_kalshi",
            "n_polymarket",
            "share",
            "include_overall_category",
            "include_platform_comparison",
            "recommendation",
            "policy_note",
        ]
    ].sort_values("n", ascending=False).reset_index(drop=True)


def platform_category_counts(scored: pd.DataFrame) -> pd.DataFrame:
    if scored.empty:
        return pd.DataFrame(columns=["platform", "category", "n"])
    return (
        scored.groupby(["platform", "category"], observed=True)
        .size()
        .rename("n")
        .reset_index()
        .sort_values(["platform", "n"], ascending=[True, False])
        .reset_index(drop=True)
    )


def forecast_source_counts(scored: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if scored.empty:
        return pd.DataFrame(columns=["horizon", "platform", "forecast_source", "n"])

    for horizon in FORECAST_HORIZONS:
        source_col = _horizon_column("forecast_source", horizon)
        if source_col not in scored.columns:
            continue
        grouped = scored.groupby(["platform", source_col], dropna=False).size()
        for (platform, source), n in grouped.items():
            rows.append(
                {
                    "horizon": horizon,
                    "platform": platform,
                    "forecast_source": str(source) if pd.notna(source) else "missing",
                    "n": int(n),
                }
            )
    if not rows:
        return pd.DataFrame(columns=["horizon", "platform", "forecast_source", "n"])
    return pd.DataFrame(rows).sort_values(["horizon", "platform", "n"], ascending=[True, True, False]).reset_index(drop=True)


def forecast_quality_counts(scored: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if scored.empty:
        return pd.DataFrame(columns=["horizon", "forecast_quality", "n"])

    for horizon in FORECAST_HORIZONS:
        quality_col = _horizon_column("forecast_quality", horizon)
        if quality_col not in scored.columns:
            continue
        for quality, n in scored[quality_col].fillna("missing").value_counts().items():
            rows.append(
                {
                    "horizon": horizon,
                    "forecast_quality": str(quality),
                    "n": int(n),
                }
            )
    if not rows:
        return pd.DataFrame(columns=["horizon", "forecast_quality", "n"])
    return pd.DataFrame(rows).sort_values(["horizon", "n"], ascending=[True, False]).reset_index(drop=True)


def missing_timestamp_counts(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if df.empty:
        return pd.DataFrame(columns=["field", "horizon", "missing", "total", "missing_share"])

    total = len(df)
    base_fields = [("open_time", None), ("close_time", None)]
    for field, horizon in base_fields:
        if field not in df.columns:
            continue
        missing = int(df[field].isna().sum())
        rows.append(
            {
                "field": field,
                "horizon": horizon,
                "missing": missing,
                "total": total,
                "missing_share": missing / total if total else 0.0,
            }
        )

    for horizon in FORECAST_HORIZONS:
        for base in ("forecast_observed_at", "forecast_target_time"):
            field = _horizon_column(base, horizon)
            if field not in df.columns:
                continue
            missing = int(df[field].isna().sum())
            rows.append(
                {
                    "field": base,
                    "horizon": horizon,
                    "missing": missing,
                    "total": total,
                    "missing_share": missing / total if total else 0.0,
                }
            )

    return pd.DataFrame(rows)


def excluded_reason_counts(normalized: pd.DataFrame) -> pd.DataFrame:
    if normalized.empty or "exclude_reason" not in normalized.columns:
        return pd.DataFrame(columns=["exclude_reason", "n"])
    excluded = normalized[normalized["exclude_reason"].fillna("") != ""]
    if excluded.empty:
        return pd.DataFrame(columns=["exclude_reason", "n"])
    return (
        excluded["exclude_reason"]
        .value_counts()
        .rename_axis("exclude_reason")
        .rename("n")
        .reset_index()
    )


def multileg_exclusion_counts(normalized: pd.DataFrame) -> pd.DataFrame:
    if normalized.empty or "is_multileg_market" not in normalized.columns:
        return pd.DataFrame(columns=["multileg_reason", "include_in_analysis", "n"])

    multileg = normalized[normalized["is_multileg_market"].fillna(False)]
    if multileg.empty:
        return pd.DataFrame(columns=["multileg_reason", "include_in_analysis", "n"])

    return (
        multileg.groupby(["multileg_reason", "include_in_analysis"], dropna=False)
        .size()
        .rename("n")
        .reset_index()
        .sort_values(["multileg_reason", "include_in_analysis"], ascending=[True, True])
        .reset_index(drop=True)
    )


def snapshot_coverage(df: pd.DataFrame, *, label: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    total = len(df)
    for horizon in FORECAST_HORIZONS:
        field = _horizon_column("forecast_prob", horizon)
        valid = int(df[field].notna().sum()) if field in df.columns else 0
        rows.append(
            {
                "dataset": label,
                "horizon": horizon,
                "valid_snapshots": valid,
                "total_rows": total,
                "coverage": (valid / total) if total else 0.0,
            }
        )
    return pd.DataFrame(rows)


def quality_summary(scored: pd.DataFrame, normalized: pd.DataFrame | None = None) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    rows.append({"metric": "scored_rows", "value": int(len(scored))})
    if normalized is not None:
        rows.append({"metric": "captured_rows", "value": int(len(normalized))})

    for horizon in FORECAST_HORIZONS:
        field = _horizon_column("forecast_prob", horizon)
        if field in scored.columns:
            rows.append(
                {
                    "metric": f"snapshot_valid_{horizon}",
                    "value": int(scored[field].notna().sum()),
                }
            )

    if not scored.empty:
        for platform, count in scored["platform"].value_counts().items():
            rows.append({"metric": f"rows_platform_{platform}", "value": int(count)})

    if normalized is not None and not normalized.empty:
        excluded = excluded_reason_counts(normalized)
        for _, row in excluded.iterrows():
            rows.append({"metric": f"excluded_{row['exclude_reason']}", "value": int(row["n"])})

    category = category_eligibility(scored)
    rows.append(
        {
            "metric": "categories_cross_platform_comparable",
            "value": int(category["include_platform_comparison"].sum()) if not category.empty else 0,
        }
    )
    rows.append(
        {
            "metric": "categories_descriptive_or_better",
            "value": int((category["recommendation"] != "drop_from_category_level_analysis").sum()) if not category.empty else 0,
        }
    )
    return pd.DataFrame(rows)


def write_quality_outputs(
    scored: pd.DataFrame,
    normalized: pd.DataFrame | None = None,
    *,
    output_dir: Path = CLEAN_DIR,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    output_dir.mkdir(parents=True, exist_ok=True)

    normalized = normalized if normalized is not None else pd.DataFrame()
    category = category_eligibility(scored)
    platform_counts = platform_category_counts(scored)
    source_counts = forecast_source_counts(scored)
    quality_counts = forecast_quality_counts(scored)
    missing_counts = missing_timestamp_counts(scored if not scored.empty else normalized)
    excluded_counts = excluded_reason_counts(normalized)
    multileg_counts = multileg_exclusion_counts(normalized)
    coverage_scored = snapshot_coverage(scored, label="scored")
    coverage_captured = snapshot_coverage(normalized, label="captured") if not normalized.empty else pd.DataFrame()
    coverage = pd.concat([coverage_scored, coverage_captured], ignore_index=True, sort=False)
    summary = quality_summary(scored, normalized=normalized)

    category.to_csv(output_dir / "data_quality_category_eligibility.csv", index=False)
    platform_counts.to_csv(output_dir / "data_quality_platform_category_counts.csv", index=False)
    source_counts.to_csv(output_dir / "data_quality_forecast_source_counts.csv", index=False)
    quality_counts.to_csv(output_dir / "data_quality_forecast_quality_counts.csv", index=False)
    missing_counts.to_csv(output_dir / "data_quality_missing_timestamp_counts.csv", index=False)
    excluded_counts.to_csv(output_dir / "data_quality_excluded_reason_counts.csv", index=False)
    multileg_counts.to_csv(output_dir / "data_quality_multileg_exclusion_counts.csv", index=False)
    coverage.to_csv(output_dir / "data_quality_snapshot_coverage.csv", index=False)
    summary.to_csv(output_dir / "data_quality_summary.csv", index=False)

    return category, summary


def main() -> None:
    scored_path = CLEAN_DIR / "accuracy_markets_scored.csv"
    normalized_path = CLEAN_DIR / "normalized_markets.csv"
    scored = pd.read_csv(scored_path) if scored_path.exists() else pd.DataFrame()
    normalized = pd.read_csv(normalized_path) if normalized_path.exists() else pd.DataFrame()
    category, summary = write_quality_outputs(scored, normalized=normalized)
    print("Category eligibility")
    print(category.to_string(index=False))
    print("\nQuality summary")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
