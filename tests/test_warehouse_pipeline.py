from __future__ import annotations

import json

import pandas as pd

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
