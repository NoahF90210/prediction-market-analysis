from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Iterable

import requests

from src.rebuild.protocol import Protocol, parse_utc, utc_iso
from src.rebuild.provenance import RawRecord, RawResponseStore

POLYMARKET_GAMMA = "https://gamma-api.polymarket.com"
POLYMARKET_CLOB = "https://clob.polymarket.com"
POLYMARKET_EVENTS_KEYSET = f"{POLYMARKET_GAMMA}/events/keyset"


class CollectionError(RuntimeError):
    """Raised when a public response cannot be collected safely."""


@dataclass(frozen=True)
class CollectedCandidate:
    record: dict[str, Any]
    market_provenance: RawRecord
    history_provenance: RawRecord | None


class HttpJsonClient:
    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        timeout_seconds: int = 30,
        max_attempts: int = 4,
    ) -> None:
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts

    def get(self, url: str, params: dict[str, Any] | None = None) -> Any:
        for attempt in range(self.max_attempts):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    timeout=self.timeout_seconds,
                )
            except requests.RequestException as exc:
                if attempt + 1 == self.max_attempts:
                    raise CollectionError(f"Request failed after retries: {url}: {exc}") from exc
                time.sleep(2**attempt)
                continue
            if response.status_code == 429 and attempt + 1 < self.max_attempts:
                time.sleep(5 * (2**attempt))
                continue
            if response.status_code >= 500 and attempt + 1 < self.max_attempts:
                time.sleep(2**attempt)
                continue
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                raise CollectionError(f"HTTP {response.status_code} from {url}") from exc
            try:
                return response.json()
            except ValueError as exc:
                raise CollectionError(f"Non-JSON response from {url}") from exc
        raise CollectionError(f"Request failed after retries: {url}")


def _list_field(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _resolution_from_prices(value: Any) -> str | None:
    prices = _list_field(value)
    if not prices:
        return None
    try:
        yes = float(prices[0])
    except (TypeError, ValueError):
        return None
    if yes >= 0.99:
        return "YES"
    if yes <= 0.01:
        return "NO"
    return None


def _first_timestamp(record: dict[str, Any], keys: Iterable[str]) -> str | None:
    for key in keys:
        parsed = parse_utc(record.get(key))
        if parsed is not None:
            return utc_iso(parsed)
    return None


class PolymarketCollector:
    def __init__(self, protocol: Protocol, store: RawResponseStore, client: HttpJsonClient | None = None) -> None:
        self.protocol = protocol
        self.store = store
        self.client = client or HttpJsonClient()

    def collect(
        self,
        *,
        max_event_pages: int | None = None,
        max_markets: int | None = None,
        after_cursor: str | None = None,
    ) -> list[CollectedCandidate]:
        """Collect closed events chronologically and filter locally by verified resolution time."""
        candidates: list[CollectedCandidate] = []
        page = 0
        passed_window = False
        while max_event_pages is None or page < max_event_pages:
            params = {
                "closed": "true",
                "limit": 100,
                "order": "closedTime",
                "ascending": "true",
            }
            if after_cursor:
                params["after_cursor"] = after_cursor
            payload = self.client.get(POLYMARKET_EVENTS_KEYSET, params)
            if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
                raise CollectionError("Polymarket events keyset response must contain an events list")
            inventory_provenance = self.store.write_response(
                platform="polymarket",
                record_type="event_inventory",
                endpoint=POLYMARKET_EVENTS_KEYSET,
                request_params=params,
                payload=payload,
            )
            events = payload["events"]
            for event in events:
                if not isinstance(event, dict):
                    continue
                event_closed = parse_utc(event.get("closedTime"))
                if event_closed is not None:
                    if event_closed >= self.protocol.end:
                        passed_window = True
                    if passed_window and event_closed >= self.protocol.end:
                        continue
                for market in event.get("markets") or []:
                    if not isinstance(market, dict):
                        continue
                    candidate = self._collect_market(event, market, inventory_provenance)
                    if candidate is not None:
                        candidates.append(candidate)
                        if max_markets is not None and len(candidates) >= max_markets:
                            return candidates
            after_cursor = str(payload.get("next_cursor") or "") or None
            page += 1
            if passed_window or not after_cursor or not events:
                break
        return candidates

    def _collect_market(
        self,
        event: dict[str, Any],
        market: dict[str, Any],
        market_provenance: RawRecord,
    ) -> CollectedCandidate | None:
        outcomes = _list_field(market.get("outcomes"))
        token_ids = _list_field(market.get("clobTokenIds"))
        resolved_at = _first_timestamp(market, ("umaEndDate",))
        if (
            len(outcomes) != 2
            or len(token_ids) != 2
            or str(market.get("umaResolutionStatus") or "").lower() != "resolved"
            or not self.protocol.contains_resolution(resolved_at)
        ):
            return None

        resolution = _resolution_from_prices(market.get("outcomePrices"))
        provisional = {
            "trading_closed_at": _first_timestamp(market, ("closedTime",)),
            "event_started_at": _first_timestamp(
                market,
                ("eventStartTime", "gameStartTime", "startTime", "event_start_time"),
            ),
            "scheduled_close_at": _first_timestamp(market, ("endDate", "endDateIso")),
            "resolved_at": resolved_at,
        }
        target = self.protocol.forecast_target(provisional)
        if target is None:
            history_payload: dict[str, Any] = {"history": []}
            history_provenance = None
        else:
            max_staleness = max(self.protocol.payload["snapshot_staleness_sensitivity_seconds"])
            history_params = {
                "market": str(token_ids[0]),
                "startTs": int(target.timestamp()) - int(max_staleness),
                "endTs": int(target.timestamp()),
                "fidelity": 1,
            }
            history_payload = self.client.get(f"{POLYMARKET_CLOB}/prices-history", history_params)
            if not isinstance(history_payload, dict):
                raise CollectionError("Polymarket price-history response must be an object")
            history_provenance = self.store.write_response(
                platform="polymarket",
                record_type="price_history",
                endpoint=f"{POLYMARKET_CLOB}/prices-history",
                request_params=history_params,
                payload=history_payload,
            )

        record = {
            "platform": "polymarket",
            "market_id": str(market.get("id") or ""),
            "event_id": str(event.get("id") or event.get("slug") or ""),
            "event_group_id": str(event.get("id") or event.get("slug") or ""),
            "series_id": str(event.get("ticker") or "") or None,
            "title": str(market.get("question") or event.get("title") or ""),
            "rules": market.get("description") or event.get("description"),
            "market_url": f"https://polymarket.com/event/{event.get('slug')}" if event.get("slug") else None,
            "raw_market_type": market.get("marketType") or "binary",
            "raw_category": event.get("category"),
            "raw_tags": event.get("tags") or [],
            "opened_at": _first_timestamp(market, ("startDate", "createdAt")),
            **provisional,
            "resolution": resolution,
            "resolution_source": "gamma_outcomePrices_with_verified_uma_resolution",
            "history": history_payload.get("history", []) if isinstance(history_payload, dict) else [],
            "history_time_keys": ["t"],
            "history_price_keys": ["p"],
            "price_source": "polymarket_clob_price_history",
            "raw_yes_orientation": str(outcomes[0]) if outcomes else None,
            "cutoff_volume": None,
            "cutoff_volume_source": None,
            "final_volume": market.get("volumeNum") or market.get("volume"),
            "final_volume_source": "gamma_market.volumeNum",
            "volume_unit": "USD",
            "explicit_multileg": str(market.get("comboStatus") or "").lower() not in {"", "disabled", "none"},
            "explicit_conditional": bool(market.get("negRiskOther")),
            "explicit_complement": False,
            "native_group_relationship": (
                "mutually_exclusive"
                if bool(market.get("negRisk") or event.get("enableNegRisk"))
                else ("related" if event.get("id") else "standalone")
            ),
        }
        return CollectedCandidate(record, market_provenance, history_provenance)
