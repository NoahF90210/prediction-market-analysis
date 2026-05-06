"""Smoke test for the static dashboard data payload.

Validates the structural invariants the React app depends on. Catches
class of bug where the JS render dies on a null Brier or missing key.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA_JS = ROOT / "static_dashboard" / "data.js"


@pytest.fixture(scope="module")
def payload() -> dict:
    if not DATA_JS.exists():
        pytest.skip("static_dashboard/data.js not built yet")
    text = DATA_JS.read_text()
    match = re.search(r"window\.DASHBOARD_DATA\s*=\s*(\{.*\});", text, re.DOTALL)
    assert match, "data.js must assign window.DASHBOARD_DATA = {...}"
    return json.loads(match.group(1))


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not (isinstance(x, float) and math.isnan(x))


def test_top_level_keys(payload):
    for key in ("rows", "headline", "calibration", "leadTime", "volume", "categoryBreakdown"):
        assert key in payload, f"missing top-level key: {key}"


def test_headline_numbers_finite(payload):
    h = payload["headline"]
    for key in ("brier_overall", "brier_polymarket", "brier_kalshi", "baseline_logistic_brier"):
        assert _finite(h[key]), f"{key} must be a finite number"
    for key in ("polymarket_ci", "kalshi_ci"):
        ci = h[key]
        assert isinstance(ci, list) and len(ci) == 2
        assert _finite(ci[0]) and _finite(ci[1]), f"{key} must contain two finite numbers"


def test_category_breakdown_dual_platform(payload):
    """CategorySlope chart calls .toFixed on both platforms, so both must be finite."""
    for row in payload["categoryBreakdown"]:
        assert _finite(row["polymarket"]), f"{row['category']} missing polymarket"
        assert _finite(row["kalshi"]), f"{row['category']} missing kalshi"


def test_rows_have_required_fields(payload):
    required = {"id", "platform", "category", "title", "forecast_prob", "outcome", "brier"}
    for row in payload["rows"][:50]:
        missing = required - row.keys()
        assert not missing, f"row missing keys: {missing}"
        assert _finite(row["forecast_prob"]), "forecast_prob must be finite"
        assert row["outcome"] in (0, 1)
