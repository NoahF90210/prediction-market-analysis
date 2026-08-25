from datetime import datetime, timezone

from src.polymarket.full_collection import market_candidate

CONFIG = {
    "resolution_start": "2025-01-01T00:00:00Z",
    "resolution_end": "2026-01-01T00:00:00Z",
}


def market(**overrides):
    value = {
        "id": "1",
        "closed": True,
        "umaResolutionStatus": "resolved",
        "closedTime": "2025-01-02 00:00:00+00",
        "endDate": "2025-01-01T12:00:00Z",
        "umaEndDate": "2025-01-02T00:00:00Z",
        "outcomes": '["Yes", "No"]',
        "clobTokenIds": '["yes-token", "no-token"]',
        "outcomePrices": '["1", "0"]',
        "question": "Will it happen?",
        "events": [{"id": "event-1", "title": "Event", "slug": "event"}],
    }
    value.update(overrides)
    return value


def test_market_candidate_preserves_broad_category_agnostic_row():
    candidate, reason = market_candidate(market(category="Sports"), CONFIG)
    assert reason is None
    assert candidate is not None
    assert candidate["market_id"] == "1"
    assert candidate["yes_token_id"] == "yes-token"
    assert candidate["resolution"] == 1


def test_market_candidate_rejects_named_outcomes_before_price_collection():
    candidate, reason = market_candidate(market(outcomes='["Texas", "ASU"]'), CONFIG)
    assert candidate is None
    assert reason == "not_yes_no"


def test_market_candidate_rejects_outside_resolution_window():
    candidate, reason = market_candidate(market(closedTime="2024-12-31 23:59:59+00"), CONFIG)
    assert candidate is None
    assert reason == "resolution_outside_window"
