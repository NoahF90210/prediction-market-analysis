from __future__ import annotations

import json

import pandas as pd

from src.data_quality import category_eligibility, snapshot_coverage
from src.settings import MIN_ANALYSIS_VOLUME
from src.warehouse_pipeline import build_dashboard_export, build_raw_inventory, normalize_market_inventory, score_markets


def sample_inventory() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "platform": "polymarket",
                "source_market_id": "pm-1",
                "source_event_id": "event-1",
                "event_title": "Will candidate A win the election?",
                "title": "Will candidate A win the election?",
                "slug": "candidate-a-election",
                "raw_platform_category": "",
                "raw_tags": json.dumps([{"slug": "elections", "label": "Elections"}]),
                "open_time": "2025-01-01T00:00:00Z",
                "close_time": "2025-11-06T00:00:00Z",
                "resolution": "YES",
                "forecast_prob": 0.62,
                "forecast_source": "history",
                "volume": MIN_ANALYSIS_VOLUME + 5000,
            },
            {
                "platform": "kalshi",
                "source_market_id": "ka-1",
                "source_event_id": "event-2",
                "event_title": "Will candidate B win the election?",
                "title": "Will candidate B win the election?",
                "slug": "KA-ELECTION-1",
                "raw_platform_category": "",
                "raw_tags": "[]",
                "open_time": "2025-01-01T00:00:00Z",
                "close_time": "2025-11-06T00:00:00Z",
                "resolution": "NO",
                "forecast_prob": 0.41,
                "forecast_source": "snapshot_fallback",
                "volume": MIN_ANALYSIS_VOLUME + 1000,
                "event_ticker": "ELECTIONS",
                "series_ticker": "PRES",
                "rules_primary": "Presidential election",
            },
            {
                "platform": "polymarket",
                "source_market_id": "pm-low",
                "source_event_id": "event-3",
                "event_title": "Will a niche team win tonight?",
                "title": "Will a niche team win tonight?",
                "slug": "niche-team-win",
                "raw_platform_category": "",
                "raw_tags": json.dumps([{"slug": "sports", "label": "Sports"}]),
                "open_time": "2025-01-01T00:00:00Z",
                "close_time": "2025-01-02T00:00:00Z",
                "resolution": "NO",
                "forecast_prob": 0.35,
                "forecast_source": "history",
                "volume": MIN_ANALYSIS_VOLUME - 1,
            },
        ]
    )


def test_low_volume_market_stays_captured_but_not_scored() -> None:
    raw = build_raw_inventory(sample_inventory().iloc[:2], sample_inventory().iloc[2:])
    normalized = normalize_market_inventory(raw)
    scored = score_markets(normalized)

    assert len(normalized) == 3
    low_volume_row = normalized.loc[normalized["source_market_id"] == "pm-low"].iloc[0]
    assert bool(low_volume_row["meets_volume_threshold"]) is False
    assert bool(low_volume_row["analysis_ready"]) is False
    assert low_volume_row["exclude_reason"] == "below_volume_threshold"
    assert "pm-low" not in set(scored["source_market_id"])


def test_scored_subset_only_contains_analysis_ready_rows() -> None:
    raw = build_raw_inventory(sample_inventory().iloc[:2], sample_inventory().iloc[2:])
    normalized = normalize_market_inventory(raw)
    scored = score_markets(normalized)

    assert set(scored["source_market_id"]) == {"pm-1", "ka-1"}
    assert scored["brier"].notna().all()
    assert scored["log_loss"].notna().all()


def test_dashboard_export_keeps_all_rows_and_scored_metrics() -> None:
    raw = build_raw_inventory(sample_inventory().iloc[:2], sample_inventory().iloc[2:])
    normalized = normalize_market_inventory(raw)
    scored = score_markets(normalized)
    dashboard = build_dashboard_export(normalized, scored)

    assert len(dashboard) == 3
    assert dashboard["analysis_ready"].sum() == 2
    low_volume = dashboard.loc[dashboard["source_market_id"] == "pm-low"].iloc[0]
    assert pd.isna(low_volume["brier"])


def test_category_eligibility_separates_descriptive_from_cross_platform() -> None:
    rows = (
        [{"platform": "polymarket", "category": "sports"} for _ in range(35)]
        + [{"platform": "kalshi", "category": "sports"} for _ in range(32)]
        + [{"platform": "kalshi", "category": "crypto"} for _ in range(31)]
        + [{"platform": "polymarket", "category": "finance"}]
    )
    scored = pd.DataFrame(rows)
    eligibility = category_eligibility(scored, min_category_n=30, min_platform_category_n=30)

    sports = eligibility.loc[eligibility["category"] == "sports"].iloc[0]
    crypto = eligibility.loc[eligibility["category"] == "crypto"].iloc[0]
    finance = eligibility.loc[eligibility["category"] == "finance"].iloc[0]

    assert bool(sports["include_platform_comparison"]) is True
    assert crypto["recommendation"] == "include_descriptively"
    assert finance["recommendation"] == "drop_from_category_level_analysis"


def test_category_policy_drops_commodities_without_cross_platform_support() -> None:
    rows = (
        [{"platform": "kalshi", "category": "commodities"} for _ in range(45)]
        + [{"platform": "polymarket", "category": "sports"} for _ in range(35)]
        + [{"platform": "kalshi", "category": "sports"} for _ in range(35)]
    )
    scored = pd.DataFrame(rows)
    eligibility = category_eligibility(scored, min_category_n=30, min_platform_category_n=30)

    commodities = eligibility.loc[eligibility["category"] == "commodities"].iloc[0]
    assert commodities["recommendation"] == "drop_from_category_level_analysis"


def test_kalshi_multileg_market_is_flagged_and_excluded() -> None:
    multileg = pd.DataFrame(
        [
            {
                "platform": "kalshi",
                "source_market_id": "KXMVESPORTSMULTIGAMEEXTENDED-ABC123",
                "source_event_id": "event-4",
                "event_title": "Parlay market",
                "title": "yes Team A,yes Team B,no Team C",
                "slug": "KXMVESPORTSMULTIGAMEEXTENDED-ABC123",
                "raw_platform_category": "sports",
                "raw_tags": "[]",
                "open_time": "2025-01-01T00:00:00Z",
                "close_time": "2025-01-02T00:00:00Z",
                "resolution": "NO",
                "forecast_prob": 0.33,
                "forecast_source": "trade_history",
                "volume": MIN_ANALYSIS_VOLUME + 1000,
                "event_ticker": "NBA",
                "series_ticker": "NBA",
            }
        ]
    )
    raw = build_raw_inventory(pd.DataFrame(), multileg)
    normalized = normalize_market_inventory(raw)
    row = normalized.iloc[0]
    assert bool(row["is_multileg_market"]) is True
    assert row["exclude_reason"] == "excluded_multileg_parlay"
    assert bool(row["analysis_ready"]) is False


def test_snapshot_coverage_reports_primary_and_secondary_horizons() -> None:
    scored = pd.DataFrame(
        [
            {"forecast_prob": 0.5, "forecast_prob_1d": 0.45, "forecast_prob_7d": 0.4},
            {"forecast_prob": 0.6, "forecast_prob_1d": None, "forecast_prob_7d": 0.35},
            {"forecast_prob": None, "forecast_prob_1d": None, "forecast_prob_7d": None},
        ]
    )
    coverage = snapshot_coverage(scored, label="scored")
    assert set(coverage["horizon"]) == {"30m", "1d", "7d"}
    cov_30m = coverage.loc[coverage["horizon"] == "30m", "valid_snapshots"].iloc[0]
    cov_1d = coverage.loc[coverage["horizon"] == "1d", "valid_snapshots"].iloc[0]
    cov_7d = coverage.loc[coverage["horizon"] == "7d", "valid_snapshots"].iloc[0]
    assert cov_30m == 2
    assert cov_1d == 1
    assert cov_7d == 2
