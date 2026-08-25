from datetime import datetime, timedelta, timezone

import pytest

from src.polymarket.price_history import select_latest_pre_cutoff

CUTOFF = datetime(2025, 1, 2, tzinfo=timezone.utc)


def test_selects_latest_point_at_or_before_cutoff():
    result = select_latest_pre_cutoff([
        {"t": (CUTOFF - timedelta(hours=3)).timestamp(), "p": 0.4},
        {"t": CUTOFF.timestamp(), "p": 0.6},
        {"t": (CUTOFF + timedelta(hours=1)).timestamp(), "p": 0.9},
    ], CUTOFF, 168)
    assert result["price"] == 0.6
    assert result["age_hours"] == 0


def test_rejects_post_cutoff_only():
    with pytest.raises(ValueError, match="no price"):
        select_latest_pre_cutoff([{"t": (CUTOFF + timedelta(hours=1)).timestamp(), "p": 0.5}], CUTOFF, 168)


def test_rejects_stale_history():
    with pytest.raises(ValueError, match="stale"):
        select_latest_pre_cutoff([{"t": (CUTOFF - timedelta(hours=169)).timestamp(), "p": 0.5}], CUTOFF, 168)


def test_accepts_boundary_prices():
    assert select_latest_pre_cutoff([{"t": CUTOFF.timestamp(), "p": 0}], CUTOFF, 168)["price"] == 0
    assert select_latest_pre_cutoff([{"t": CUTOFF.timestamp(), "p": 1}], CUTOFF, 168)["price"] == 1


def test_rejects_out_of_range_price():
    with pytest.raises(ValueError, match="between 0 and 1"):
        select_latest_pre_cutoff([{"t": CUTOFF.timestamp(), "p": 1.1}], CUTOFF, 168)
