from __future__ import annotations

import json

import pandas as pd

from src.accuracy import VALID_RESOLUTIONS, add_score_columns, normalize_probability, normalize_resolution, to_float
from src.category_mapping import classify_market, comparable_categories
from src.settings import CATEGORY_CONFIDENCE_THRESHOLD, CROSS_PLATFORM_MIN_MARKETS, MIN_ANALYSIS_VOLUME


def ensure_market_id_column(df: pd.DataFrame) -> pd.DataFrame:
    renamed = df.copy()
    if "market_id" not in renamed.columns and "source_market_id" in renamed.columns:
        renamed["market_id"] = renamed["source_market_id"]
    if "source_market_id" not in renamed.columns and "market_id" in renamed.columns:
        renamed["source_market_id"] = renamed["market_id"]
    return renamed


def build_raw_inventory(polymarket_df: pd.DataFrame, kalshi_df: pd.DataFrame) -> pd.DataFrame:
    frames = [frame for frame in [polymarket_df, kalshi_df] if frame is not None and not frame.empty]
    if not frames:
        return pd.DataFrame()
    raw = pd.concat(frames, ignore_index=True, sort=False)
    raw = ensure_market_id_column(raw)
    raw["volume"] = pd.to_numeric(raw.get("volume"), errors="coerce")
    raw["forecast_prob"] = raw.get("forecast_prob").map(normalize_probability)
    raw["resolution"] = raw.get("resolution").map(normalize_resolution)
    raw["raw_tags"] = raw.get("raw_tags", "[]").fillna("[]")
    raw["raw_platform_category"] = raw.get("raw_platform_category", "").fillna("")
    raw["title"] = raw.get("title", "").fillna("")
    raw["slug"] = raw.get("slug", raw["source_market_id"]).fillna(raw["source_market_id"])
    raw["source_event_id"] = raw.get("source_event_id")
    raw["event_title"] = raw.get("event_title")
    raw["forecast_source"] = raw.get("forecast_source")
    raw["ingested_at"] = pd.Timestamp.now(tz="UTC")
    raw["updated_at"] = pd.Timestamp.now(tz="UTC")
    return raw.drop_duplicates(subset=["platform", "source_market_id"]).reset_index(drop=True)


def _parse_tags(value) -> list[dict]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _classify_row(row: pd.Series):
    return classify_market(
        platform=str(row.get("platform") or ""),
        market_id=str(row.get("source_market_id") or ""),
        title=str(row.get("title") or ""),
        slug=str(row.get("slug") or ""),
        raw_platform_category=str(row.get("raw_platform_category") or ""),
        raw_tags=_parse_tags(row.get("raw_tags")),
        context_fields=[
            str(row.get("event_title") or ""),
            str(row.get("subtitle") or ""),
            str(row.get("series_ticker") or ""),
            str(row.get("event_ticker") or ""),
            str(row.get("rules_primary") or ""),
            str(row.get("slug") or ""),
        ],
    )


def _exclude_reason(row: pd.Series) -> str:
    if not bool(row.get("meets_volume_threshold")):
        return "below_volume_threshold"
    if row.get("resolution") not in VALID_RESOLUTIONS:
        return "invalid_resolution"
    if pd.isna(row.get("forecast_prob")):
        return "missing_forecast_probability"
    if str(row.get("category") or "") == "unclassified":
        return "unclassified_category"
    if bool(row.get("needs_review")):
        return "category_needs_review"
    if float(row.get("category_confidence") or 0.0) < CATEGORY_CONFIDENCE_THRESHOLD:
        return "low_category_confidence"
    return ""


def normalize_market_inventory(raw_df: pd.DataFrame) -> pd.DataFrame:
    raw_df = ensure_market_id_column(raw_df)
    if raw_df.empty:
        return pd.DataFrame()

    records: list[dict] = []
    for row in raw_df.to_dict("records"):
        series = pd.Series(row)
        classification = _classify_row(series)
        volume = to_float(series.get("volume"))
        record = {
            **row,
            "market_id": row["source_market_id"],
            "category": classification.canonical_category,
            "canonical_category": classification.canonical_category,
            "category_source": classification.category_source,
            "category_confidence": classification.category_confidence,
            "needs_review": classification.needs_review,
            "review_reason": classification.review_reason,
            "raw_platform_category": classification.raw_platform_category,
            "raw_tags": classification.raw_tags,
            "volume": volume,
            "meets_volume_threshold": bool(volume is not None and volume >= MIN_ANALYSIS_VOLUME),
            "normalized_at": pd.Timestamp.now(tz="UTC"),
        }
        records.append(record)

    normalized = pd.DataFrame(records)
    normalized["exclude_reason"] = normalized.apply(_exclude_reason, axis=1)
    normalized["include_in_analysis"] = normalized["exclude_reason"].eq("")
    comparable = comparable_categories(
        normalized.assign(include_in_analysis=normalized["include_in_analysis"]),
        min_markets_per_platform=CROSS_PLATFORM_MIN_MARKETS,
    )
    normalized["is_cross_platform_comparable"] = normalized["category"].isin(comparable)
    normalized["analysis_ready"] = normalized["include_in_analysis"]
    return normalized.reset_index(drop=True)


def score_markets(normalized_df: pd.DataFrame) -> pd.DataFrame:
    normalized_df = ensure_market_id_column(normalized_df)
    if normalized_df.empty:
        return pd.DataFrame()

    eligible = normalized_df[normalized_df["analysis_ready"]].copy()
    if eligible.empty:
        return pd.DataFrame(columns=list(normalized_df.columns) + ["outcome", "brier", "log_loss", "days_to_resolution", "duration_bucket", "volume_bucket"])

    scored = add_score_columns(eligible)
    scored["scored_at"] = pd.Timestamp.now(tz="UTC")
    scored["source_market_id"] = scored["market_id"]
    return scored.reset_index(drop=True)


def build_review_queue(normalized_df: pd.DataFrame) -> pd.DataFrame:
    if normalized_df.empty:
        return normalized_df.copy()
    queue = normalized_df[
        normalized_df["needs_review"]
        | normalized_df["category"].eq("unclassified")
        | ~normalized_df["include_in_analysis"]
    ].copy()
    return queue.sort_values(["volume", "category_confidence"], ascending=[False, True]).reset_index(drop=True)


def build_dashboard_export(normalized_df: pd.DataFrame, scored_df: pd.DataFrame) -> pd.DataFrame:
    normalized_df = ensure_market_id_column(normalized_df)
    scored_df = ensure_market_id_column(scored_df)
    if normalized_df.empty:
        return normalized_df.copy()

    score_cols = [
        "platform",
        "market_id",
        "outcome",
        "brier",
        "log_loss",
        "days_to_resolution",
        "duration_bucket",
        "volume_bucket",
    ]
    merged = normalized_df.merge(
        scored_df[score_cols] if not scored_df.empty else pd.DataFrame(columns=score_cols),
        on=["platform", "market_id"],
        how="left",
    )
    return merged.reset_index(drop=True)
