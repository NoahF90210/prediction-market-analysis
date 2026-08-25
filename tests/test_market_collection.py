import requests
import pytest

from src.polymarket.client import PolymarketAPIError, iter_market_pages


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.url = "https://gamma-api.polymarket.com/markets/keyset"

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append((url, params.copy(), timeout))
        return self.responses.pop(0)


def test_keyset_pagination_follows_after_cursor_once_per_page():
    session = FakeSession([
        FakeResponse({"markets": [{"id": "1"}], "next_cursor": "cursor-1"}),
        FakeResponse({"markets": [{"id": "2"}]})
    ])
    pages = list(iter_market_pages(session, limit=2, end_date_min="2025-01-01T00:00:00Z"))
    assert [[m["id"] for m in page["payload"]["markets"]] for page in pages] == [["1"], ["2"]]
    assert session.calls[0][1]["closed"] is True
    assert session.calls[0][1]["limit"] == 2
    assert "offset" not in session.calls[0][1]
    assert session.calls[1][1]["after_cursor"] == "cursor-1"


def test_rejects_offset_pagination():
    session = FakeSession([])
    with pytest.raises(PolymarketAPIError):
        list(iter_market_pages(session, offset=10))
    assert session.calls == []


def test_fails_on_malformed_market_payload():
    session = FakeSession([FakeResponse({"next_cursor": "cursor"})])
    with pytest.raises(PolymarketAPIError, match="markets list"):
        list(iter_market_pages(session))


def test_retries_transient_status_then_succeeds():
    session = FakeSession([
        FakeResponse({}, status_code=503),
        FakeResponse({"markets": [{"id": "1"}]})
    ])
    pages = list(iter_market_pages(session))
    assert len(pages) == 1
    assert len(session.calls) == 2
