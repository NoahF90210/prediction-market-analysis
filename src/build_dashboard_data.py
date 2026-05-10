"""
Generate static_dashboard/data.js from the real scored dataset.

Replaces the mock-data version of data.js with a JS file that exposes
window.DASHBOARD_DATA backed by data/cleaned/accuracy_markets_scored.csv,
plus a logistic-regression baseline trained on volume + lead time + category.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import KFold
from sklearn.preprocessing import OrdinalEncoder, StandardScaler

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data_quality import (
    category_eligibility,
    excluded_reason_counts,
    forecast_quality_counts,
    forecast_source_counts,
    missing_timestamp_counts,
    multileg_exclusion_counts,
    platform_category_counts,
    quality_summary,
    snapshot_coverage,
)

SCORED_CSV = ROOT / "data" / "cleaned" / "accuracy_markets_scored.csv"
ALL_CSV = ROOT / "data" / "cleaned" / "accuracy_markets.csv"
OUT_PATH = ROOT / "static_dashboard" / "data.js"


def logistic_oof_brier(scored: pd.DataFrame) -> float:
    df = scored.dropna(subset=["volume", "outcome"]).copy()
    df["log_volume"] = np.log(df["volume"].astype(float).clip(lower=1))
    df["days"] = pd.to_numeric(df["days_to_resolution"], errors="coerce")
    df["days"] = df["days"].fillna(df["days"].median())
    cats = pd.get_dummies(df["category"], drop_first=True, dtype=float)
    X = pd.concat([df[["log_volume", "days"]].astype(float), cats], axis=1).values
    y = df["outcome"].astype(int).values
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    oof = np.zeros(len(y), dtype=float)
    for tr, te in kf.split(X):
        scaler = StandardScaler()
        Xtr = scaler.fit_transform(X[tr])
        Xte = scaler.transform(X[te])
        model = LogisticRegression(max_iter=2000, C=1.0)
        model.fit(Xtr, y[tr])
        oof[te] = model.predict_proba(Xte)[:, 1]
    return float(((oof - y) ** 2).mean())


def gbm_oof_brier(scored: pd.DataFrame) -> float:
    df = scored.dropna(subset=["volume", "outcome"]).copy()
    df["log_volume"] = np.log(df["volume"].astype(float).clip(lower=1))
    df["days"] = pd.to_numeric(df["days_to_resolution"], errors="coerce")
    df["days"] = df["days"].fillna(df["days"].median())
    enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
    cat_arr = enc.fit_transform(df[["category", "platform"]].astype(str).fillna("unknown"))
    X = np.concatenate(
        [df[["log_volume", "days"]].astype(float).values, cat_arr], axis=1
    )
    y = df["outcome"].astype(int).values
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    oof = np.zeros(len(y), dtype=float)
    for tr, te in kf.split(X):
        model = HistGradientBoostingClassifier(
            categorical_features=[2, 3], random_state=42
        )
        model.fit(X[tr], y[tr])
        oof[te] = model.predict_proba(X[te])[:, 1]
    return float(((oof - y) ** 2).mean())


def calibration(df: pd.DataFrame) -> list[dict]:
    bins = [(i, i + 10) for i in range(0, 100, 10)]
    out = []
    for lo, hi in bins:
        if hi == 100:
            mask = (df["forecast_prob"] * 100 >= lo) & (df["forecast_prob"] * 100 <= hi)
        else:
            mask = (df["forecast_prob"] * 100 >= lo) & (df["forecast_prob"] * 100 < hi)
        sub = df[mask]
        n = int(len(sub))
        observed = float(sub["outcome"].mean()) if n else None
        out.append({"bucket": f"{lo}–{hi}%", "midpoint": (lo + hi) / 200, "observed": observed, "n": n})
    return out


def lead_time_buckets(df: pd.DataFrame) -> list[dict]:
    def bucket(d):
        if pd.isna(d):
            return "unknown"
        if d < 1:
            return "<1 day"
        if d < 7:
            return "1–7 days"
        if d < 30:
            return "7–30 days"
        return "30+ days"

    df = df.copy()
    df["lt"] = df["days_to_resolution"].map(bucket)
    g = df.groupby("lt").agg(brier=("brier", "mean"), n=("brier", "size")).reset_index()
    order = ["<1 day", "1–7 days", "7–30 days", "30+ days", "unknown"]
    g["o"] = g["lt"].map({o: i for i, o in enumerate(order)})
    g = g.sort_values("o")
    return [{"bucket": r["lt"], "brier": float(r["brier"]), "n": int(r["n"])} for _, r in g.iterrows()]


def volume_buckets(df: pd.DataFrame) -> list[dict]:
    def bucket(v):
        if pd.isna(v):
            return "unknown"
        if v < 250_000:
            return "$100k–$250k"
        if v < 1_000_000:
            return "$250k–$1M"
        if v < 5_000_000:
            return "$1M–$5M"
        return "$5M+"

    df = df.copy()
    df["vb"] = df["volume"].map(bucket)
    g = df.groupby("vb").agg(brier=("brier", "mean"), n=("brier", "size")).reset_index()
    order = ["$100k–$250k", "$250k–$1M", "$1M–$5M", "$5M+", "unknown"]
    g["o"] = g["vb"].map({o: i for i, o in enumerate(order)})
    g = g.sort_values("o")
    return [{"bucket": r["vb"], "brier": float(r["brier"]), "n": int(r["n"])} for _, r in g.iterrows()]


def category_breakdown(df: pd.DataFrame) -> list[dict]:
    g = df.groupby(["category", "platform"], observed=True).agg(brier=("brier", "mean"), n=("brier", "size")).reset_index()
    pivot = g.pivot(index="category", columns="platform", values=["brier", "n"]).fillna(0)
    out = []
    for cat in pivot.index:
        row = {"category": cat}
        for plat in ("polymarket", "kalshi"):
            try:
                row[plat] = float(pivot.loc[cat, ("brier", plat)]) if pivot.loc[cat, ("n", plat)] > 0 else None
                row[f"n_{plat[:5]}"] = int(pivot.loc[cat, ("n", plat)])
            except KeyError:
                row[plat] = None
                row[f"n_{plat[:5]}"] = 0
        if row["polymarket"] is not None and row["kalshi"] is not None:
            out.append(row)
    out.sort(key=lambda r: -(r.get("n_poly", 0) + r.get("n_kalsh", 0)))
    return out


def _safe_iso(value) -> str | None:
    ts = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(ts):
        return None
    return ts.isoformat()


def _safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def to_rows(df: pd.DataFrame) -> list[dict]:
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "id": f"{r['platform']}_{r['market_id']}",
            "platform": r["platform"],
            "category": r["category"],
            "title": str(r.get("title") or "")[:160],
            "forecast_prob": _safe_float(r.get("forecast_prob")),
            "resolution": r["resolution"],
            "outcome": int(r["outcome"]),
            "brier": _safe_float(r.get("brier")),
            "log_loss": _safe_float(r.get("log_loss")),
            "volume": _safe_float(r.get("volume")),
            "days_to_resolution": _safe_float(r.get("days_to_resolution")),
            "open_time": _safe_iso(r.get("open_time")),
            "close_time": _safe_iso(r.get("close_time")),
            "forecast_source": r.get("forecast_source") or "history",
        })
    return rows


def headline_block(scored: pd.DataFrame, all_markets: pd.DataFrame, log_brier: float, gbm_brier: float) -> dict:
    overall_brier = float(scored["brier"].mean())
    overall_log_loss = float(scored["log_loss"].mean())
    by_plat = scored.groupby("platform")["brier"].agg(["mean", "size"])

    # Bootstrap CI helper
    def boot_ci(values: np.ndarray, n_iter: int = 2000, alpha: float = 0.05, seed: int = 42) -> tuple[float, float]:
        rng = np.random.default_rng(seed)
        idx = rng.integers(0, len(values), size=(n_iter, len(values)))
        means = values[idx].mean(axis=1)
        return float(np.quantile(means, alpha / 2)), float(np.quantile(means, 1 - alpha / 2))

    poly_brier = float(by_plat.loc["polymarket", "mean"]) if "polymarket" in by_plat.index else None
    kalshi_brier = float(by_plat.loc["kalshi", "mean"]) if "kalshi" in by_plat.index else None
    poly_ci = boot_ci(scored.loc[scored["platform"] == "polymarket", "brier"].values) if poly_brier is not None else (None, None)
    kalshi_ci = boot_ci(scored.loc[scored["platform"] == "kalshi", "brier"].values) if kalshi_brier is not None else (None, None)

    # Kalshi history-only Brier (the apples-to-apples comparison)
    kalshi = scored[scored["platform"] == "kalshi"]
    kalshi_hist = kalshi[kalshi["forecast_source"] == "history"]
    kalshi_hist_brier = float(kalshi_hist["brier"].mean()) if len(kalshi_hist) else None
    kalshi_hist_ci = boot_ci(kalshi_hist["brier"].values) if len(kalshi_hist) else (None, None)

    # Baselines
    baseline_50 = 0.25
    cat_rates = scored.groupby("category")["outcome"].mean()
    cat_baseline_pred = scored["category"].map(cat_rates)
    baseline_cat = float(((cat_baseline_pred - scored["outcome"]) ** 2).mean())

    return {
        "n_markets": int(len(scored)),
        "n_captured": int(len(all_markets)) if not all_markets.empty else int(len(scored)),
        "n_polymarket": int(by_plat.loc["polymarket", "size"]) if "polymarket" in by_plat.index else 0,
        "n_kalshi": int(by_plat.loc["kalshi", "size"]) if "kalshi" in by_plat.index else 0,
        "n_kalshi_history": int(len(kalshi_hist)),
        "kalshi_history_share": (float(len(kalshi_hist) / len(kalshi)) if len(kalshi) else 0.0),
        "brier_overall": overall_brier,
        "brier_polymarket": poly_brier,
        "brier_kalshi": kalshi_brier,
        "brier_kalshi_history_only": kalshi_hist_brier,
        "log_loss_overall": overall_log_loss,
        "baseline_50_brier": baseline_50,
        "baseline_category_brier": baseline_cat,
        "baseline_logistic_brier": log_brier,
        "baseline_gbm_brier": gbm_brier,
        "pct_better_than_50": (baseline_50 - overall_brier) / baseline_50,
        "pct_better_than_category": (baseline_cat - overall_brier) / baseline_cat,
        "pct_better_than_logistic": (log_brier - overall_brier) / log_brier,
        "pct_better_than_gbm": (gbm_brier - overall_brier) / gbm_brier,
        "polymarket_ci": list(poly_ci),
        "kalshi_ci": list(kalshi_ci),
        "kalshi_history_ci": list(kalshi_hist_ci),
        "avg_forecast": float(scored["forecast_prob"].mean()),
        "median_lead_time_days": float(scored["days_to_resolution"].median()),
        "total_volume": float(scored["volume"].sum()),
        "last_updated": pd.Timestamp.now("UTC").isoformat(),
    }


def main() -> None:
    scored = pd.read_csv(SCORED_CSV)
    all_markets = pd.read_csv(ALL_CSV) if ALL_CSV.exists() else pd.DataFrame()
    print(f"Scored rows: {len(scored)} · captured rows: {len(all_markets)}")

    log_brier = logistic_oof_brier(scored)
    print(f"Logistic-regression OOF Brier: {log_brier:.4f}")
    gbm_brier = gbm_oof_brier(scored)
    print(f"Gradient-boosted OOF Brier: {gbm_brier:.4f}")

    normalized_for_quality = all_markets if not all_markets.empty else scored
    payload = {
        "rows": to_rows(scored),
        "headline": headline_block(scored, all_markets, log_brier, gbm_brier),
        "calibration": calibration(scored),
        "leadTime": lead_time_buckets(scored),
        "volume": volume_buckets(scored),
        "categoryBreakdown": category_breakdown(scored),
        "categoryEligibility": category_eligibility(scored).to_dict("records"),
        "qualitySummary": quality_summary(scored, normalized=normalized_for_quality).to_dict("records"),
        "platformCategoryCounts": platform_category_counts(scored).to_dict("records"),
        "forecastSourceCounts": forecast_source_counts(scored).to_dict("records"),
        "forecastQualityCounts": forecast_quality_counts(scored).to_dict("records"),
        "missingTimestampCounts": missing_timestamp_counts(normalized_for_quality).to_dict("records"),
        "excludedReasonCounts": excluded_reason_counts(normalized_for_quality).to_dict("records"),
        "multilegExclusionCounts": multileg_exclusion_counts(normalized_for_quality).to_dict("records"),
        "snapshotCoverage": pd.concat(
            [
                snapshot_coverage(scored, label="scored"),
                snapshot_coverage(normalized_for_quality, label="captured"),
            ],
            ignore_index=True,
            sort=False,
        ).to_dict("records"),
    }

    js = "// Built by src/build_dashboard_data.py from cleaned analysis data.\n"
    js += "// Source: data/cleaned/accuracy_markets_scored.csv\n"
    js += f"window.DASHBOARD_DATA = {json.dumps(payload, default=str, allow_nan=False)};\n"
    OUT_PATH.write_text(js)
    print(f"Wrote {OUT_PATH} ({OUT_PATH.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
