from __future__ import annotations

import datetime as dt
import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Protocol

import requests

from src.rebuild.protocol import Protocol, parse_utc, utc_iso
from src.rebuild.provenance import RawRecord, RawResponseStore

POLYMARKET_GAMMA = "https://gamma-api.polymarket.com"
POLYMARKET_CLOB = "https://clob.polymarket.com"
POLYMARKET_EVENTS_KEYSET = f"{POLYMARKET_GAMMA}/events/keyset"
KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2"


class CollectionError(RuntimeError):
    """Raised when a public response cannot be collected safely."""


class CredentialRequiredError(CollectionError):
    """Raised instead of fabricating data when an endpoint requires credentials."""


class KalshiAuthenticator(Protocol):
    def headers(self, method: str, api_path: str) -> Mapping[str, str]:
        """Return signed KALSHI-ACCESS-* headers without logging secret material."""


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
        header_factory: Callable[[str, str], Mapping[str, str]] | None = None,
        timeout_seconds: int = 30,
        max_attempts: int = 4,
    ) -> None:
        self.session = session or requests.Session()
        self.header_factory = header_factory
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts

    def get(self, url: str, params: dict[str, Any] | None = None, *, api_path: str | None = None) -> Any:
        headers = dict(self.header_factory("GET", api_path or url)) if self.header_factory else {}
        for attempt in range(self.max_attempts):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
            except requests.RequestException as exc:
                if attempt + 1 == self.max_attempts:
                    raise CollectionError(f"Request failed after retries: {url}: {exc}") from exc
                time.sleep(2**attempt)
                continue
            if response.status_code in {401, 403}:
                raise CredentialRequiredError(
                    "Kalshi collection requires authentication for this endpoint. "
                    "Provide a KalshiAuthenticator that signs timestamp + HTTP method + /trade-api/v2 path "
                    "and returns KALSHI-ACCESS-KEY, KALSHI-ACCESS-TIMESTAMP, and "
                    "KALSHI-ACCESS-SIGNATURE headers. Keep the key and private key outside git and do not "
                    "pass them on the command line. Collection stopped; no rows were mocked."
                )
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
        """Collect closed events chronologically and filter locally by verified resolution time.

        The market inventory endpoint is dominated by high-frequency recent contracts.
        Events keyset pagination in ascending close-time order reaches historical windows
        without scanning millions of newer market rows first.
        """
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


class KalshiCollector:
    def __init__(
        self,
        protocol: Protocol,
        store: RawResponseStore,
        client: HttpJsonClient | None = None,
        authenticator: KalshiAuthenticator | None = None,
    ) -> None:
        header_factory = authenticator.headers if authenticator else None
        self.protocol = protocol
        self.store = store
        self.client = client or HttpJsonClient(header_factory=header_factory)

    def collect(self, *, max_market_pages: int | None = None, max_markets: int | None = None) -> list[CollectedCandidate]:
        cutoff_payload = self.client.get(f"{KALSHI_API}/historical/cutoff", api_path="/trade-api/v2/historical/cutoff")
        if not isinstance(cutoff_payload, dict):
            raise CollectionError("Kalshi historical cutoff response must be an object")
        self.store.write_response(
            platform="kalshi",
            record_type="historical_cutoff",
            endpoint=f"{KALSHI_API}/historical/cutoff",
            request_params={},
            payload=cutoff_payload,
        )
        trades_cutoff = parse_utc(cutoff_payload.get("trades_created_ts"))

        markets: dict[str, tuple[dict[str, Any], RawRecord]] = {}
        sources = [
            ("/historical/markets", {}),
            ("/markets", {"status": "settled"}),
        ]
        for api_path, base_params in sources:
            cursor: str | None = None
            page = 0
            while max_market_pages is None or page < max_market_pages:
                params: dict[str, Any] = {**base_params, "limit": 1000}
                if cursor:
                    params["cursor"] = cursor
                payload = self.client.get(f"{KALSHI_API}{api_path}", params, api_path=f"/trade-api/v2{api_path}")
                if not isinstance(payload, dict):
                    raise CollectionError("Kalshi markets response must be an object")
                provenance = self.store.write_response(
                    platform="kalshi",
                    record_type="market_inventory",
                    endpoint=f"{KALSHI_API}{api_path}",
                    request_params=params,
                    payload=payload,
                )
                batch = payload.get("markets") or []
                for market in batch:
                    if not isinstance(market, dict):
                        continue
                    settlement = parse_utc(market.get("settlement_ts"))
                    ticker = str(market.get("ticker") or "")
                    if ticker and self.protocol.contains_resolution(settlement):
                        markets[ticker] = (market, provenance)
                cursor = str(payload.get("cursor") or "") or None
                page += 1
                if not cursor or not batch:
                    break

        candidates: list[CollectedCandidate] = []
        for ticker in sorted(markets):
            market, market_provenance = markets[ticker]
            candidate = self._collect_market(market, market_provenance, trades_cutoff)
            candidates.append(candidate)
            if max_markets is not None and len(candidates) >= max_markets:
                break
        return candidates

    def _collect_market(
        self,
        market: dict[str, Any],
        market_provenance: RawRecord,
        trades_cutoff: dt.datetime | None,
    ) -> CollectedCandidate:
        provisional = {
            "trading_closed_at": _first_timestamp(market, ("close_time", "expiration_time")),
            "event_started_at": _first_timestamp(
                market,
                ("event_start_time", "expected_expiration_time"),
            ),
            "scheduled_close_at": _first_timestamp(market, ("expected_expiration_time", "latest_expiration_time")),
            "resolved_at": _first_timestamp(market, ("settlement_ts",)),
        }
        target = self.protocol.forecast_target(provisional)
        ticker = str(market.get("ticker") or "")
        history: list[dict[str, Any]] = []
        history_provenance: RawRecord | None = None
        if target is not None:
            api_path = "/historical/trades" if trades_cutoff is not None and target < trades_cutoff else "/markets/trades"
            base_params = {"ticker": ticker, "limit": 1000, "max_ts": int(target.timestamp())}
            cursor: str | None = None
            page_hashes: list[str] = []
            while True:
                params = dict(base_params)
                if cursor:
                    params["cursor"] = cursor
                payload = self.client.get(
                    f"{KALSHI_API}{api_path}",
                    params,
                    api_path=f"/trade-api/v2{api_path}",
                )
                if not isinstance(payload, dict):
                    raise CollectionError("Kalshi trades response must be an object")
                page_provenance = self.store.write_response(
                    platform="kalshi",
                    record_type="trade_history",
                    endpoint=f"{KALSHI_API}{api_path}",
                    request_params=params,
                    payload=payload,
                )
                page_hashes.append(page_provenance.sha256)
                batch = [trade for trade in payload.get("trades", []) if isinstance(trade, dict)]
                history.extend(batch)
                cursor = str(payload.get("cursor") or "") or None
                if not cursor or not batch:
                    break

            deduplicated = {
                str(trade.get("trade_id") or f"{trade.get('created_time')}:{trade.get('yes_price_dollars')}"): trade
                for trade in history
            }
            history = sorted(
                deduplicated.values(),
                key=lambda trade: (str(trade.get("created_time") or ""), str(trade.get("trade_id") or "")),
            )
            bundle_payload = {
                "page_sha256": page_hashes,
                "trades": history,
            }
            history_provenance = self.store.write_response(
                platform="kalshi",
                record_type="trade_history_bundle",
                endpoint=f"{KALSHI_API}{api_path}",
                request_params={**base_params, "pagination": "cursor_exhausted", "page_count": len(page_hashes)},
                payload=bundle_payload,
            )

        result = str(market.get("result") or "").upper()
        resolution = result if result in {"YES", "NO"} else None
        selected_legs = market.get("mve_selected_legs")
        record = {
            "platform": "kalshi",
            "market_id": ticker,
            "event_id": str(market.get("event_ticker") or ticker),
            "event_group_id": str(market.get("event_ticker") or ticker),
            "series_id": str(market.get("series_ticker") or "") or None,
            "title": str(market.get("title") or market.get("yes_sub_title") or ticker),
            "rules": market.get("rules_primary"),
            "market_url": f"https://kalshi.com/markets/{ticker.lower()}" if ticker else None,
            "raw_market_type": market.get("market_type") or "binary",
            "raw_category": market.get("category"),
            "raw_tags": [],
            "opened_at": _first_timestamp(market, ("open_time", "created_time")),
            **provisional,
            "resolution": resolution,
            "resolution_source": "kalshi_market.result_with_settlement_ts",
            "history": history,
            "history_time_keys": ["created_time"],
            "history_price_keys": ["yes_price_dollars", "yes_price"],
            "price_source": "kalshi_trade_history",
            "raw_yes_orientation": market.get("yes_sub_title") or "YES",
            "cutoff_volume": None,
            "cutoff_volume_source": None,
            "final_volume": market.get("volume_fp") or market.get("volume"),
            "final_volume_source": "kalshi_market.volume_fp",
            "volume_unit": "contracts",
            "explicit_multileg": bool(
                ticker.startswith("KXMVE")
                or market.get("mve_collection_ticker")
                or (isinstance(selected_legs, list) and len(selected_legs) > 1)
            ),
            "explicit_conditional": False,
            "explicit_complement": False,
            "native_group_relationship": "mutually_exclusive" if market.get("event_ticker") else "standalone",
            "mve_selected_legs": selected_legs,
            "mve_collection_ticker": market.get("mve_collection_ticker"),
        }
        return CollectedCandidate(record, market_provenance, history_provenance)
