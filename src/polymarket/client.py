"""Small, fail-closed clients for the official Polymarket public APIs."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Protocol, cast

import requests

GAMMA_KEYSET_URL = "https://gamma-api.polymarket.com/markets/keyset"
CLOB_HISTORY_URL = "https://clob.polymarket.com/prices-history"


class PolymarketAPIError(RuntimeError):
    pass


class SessionLike(Protocol):
    def get(self, url: str, params: dict[str, Any], timeout: int) -> Any: ...


def _get_json(session: SessionLike, url: str, params: dict[str, Any], retries: int = 3) -> dict[str, Any]:
    for attempt in range(retries):
        response = session.get(url, params=params, timeout=30)
        if response.status_code == 200:
            try:
                payload = response.json()
            except ValueError as exc:
                raise PolymarketAPIError(f"malformed JSON from {url}") from exc
            if not isinstance(payload, dict):
                raise PolymarketAPIError(f"expected object from {url}")
            return payload
        if response.status_code == 429 or response.status_code >= 500:
            if attempt + 1 < retries:
                time.sleep(2**attempt)
                continue
        raise PolymarketAPIError(f"HTTP {response.status_code} from {response.url}")
    raise PolymarketAPIError(f"request failed after {retries} attempts: {url}")


def iter_market_pages(
    session: SessionLike | None = None,
    *,
    limit: int = 100,
    **filters: Any,
):
    """Yield official Gamma keyset pages and never use offset pagination."""
    if limit <= 0 or limit > 500:
        raise ValueError("limit must be between 1 and 500")
    session = session or cast(SessionLike, requests.Session())
    if "offset" in filters:
        raise PolymarketAPIError("offset pagination is not supported")
    params = {"closed": True, "limit": limit, **filters}
    retrieval_timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    while True:
        payload = _get_json(session, GAMMA_KEYSET_URL, params)
        markets = payload.get("markets")
        if not isinstance(markets, list):
            raise PolymarketAPIError("Gamma response missing markets list")
        yield {"retrieved_at": retrieval_timestamp, "params": dict(params), "payload": payload}
        cursor = payload.get("next_cursor")
        if not cursor:
            break
        params["after_cursor"] = cursor


def fetch_price_history(
    token_id: str,
    *,
    start_ts: int,
    end_ts: int,
    fidelity: int = 60,
    session: SessionLike | None = None,
) -> dict[str, Any]:
    if start_ts >= end_ts:
        raise ValueError("start_ts must precede end_ts")
    params = {"market": token_id, "startTs": start_ts, "endTs": end_ts, "fidelity": fidelity}
    return _get_json(session or cast(SessionLike, requests.Session()), CLOB_HISTORY_URL, params)


def parse_json_field(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not isinstance(value, str):
        raise PolymarketAPIError("expected JSON-encoded list field")
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise PolymarketAPIError("expected JSON-encoded list field")
    return parsed
