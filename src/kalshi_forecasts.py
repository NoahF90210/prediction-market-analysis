from __future__ import annotations

import datetime as _dt
import json
import time
from dataclasses import replace
from pathlib import Path

from src.accuracy import normalize_probability, to_float
from src.forecast_snapshots import (
    FORECAST_HORIZONS,
    PRIMARY_FORECAST_HORIZON,
    ForecastSnapshot,
    fallback_snapshot,
    forecast_from_history,
    parse_timestamp,
)
from src.settings import RAW_DIR


def kalshi_volume(market: dict) -> float | None:
    for key in ("volume", "volume_dollars", "volume_fp"):
        volume = to_float(market.get(key))
        if volume is not None:
            return volume
    return None


def fetch_kalshi_trades(
    ticker: str,
    max_pages: int = 10,
    *,
    endpoint: str = "/markets/trades",
    min_ts: int | None = None,
    max_ts: int | None = None,
) -> list[dict]:
    """Fetch trades for a Kalshi market.

    Docs: GET /markets/trades and GET /historical/trades both support
    ticker/min_ts/max_ts plus cursor pagination.
    """
    from src import kalshi_client as kalshi

    trades: list[dict] = []
    cursor = None
    for _ in range(max_pages):
        params = {"ticker": ticker, "limit": 1000}
        if min_ts is not None:
            params["min_ts"] = min_ts
        if max_ts is not None:
            params["max_ts"] = max_ts
        if cursor:
            params["cursor"] = cursor
        data = kalshi.get(endpoint, params)
        batch = data.get("trades", [])
        trades.extend(batch)
        cursor = data.get("cursor")
        if not cursor or not batch:
            break
        time.sleep(0.1)
    return trades


def fetch_kalshi_historical_trades(
    ticker: str,
    max_pages: int = 10,
    *,
    min_ts: int | None = None,
    max_ts: int | None = None,
) -> list[dict]:
    return fetch_kalshi_trades(
        ticker,
        max_pages=max_pages,
        endpoint="/historical/trades",
        min_ts=min_ts,
        max_ts=max_ts,
    )


def fetch_kalshi_trade_history(ticker: str, max_pages_per_endpoint: int = 10) -> list[dict]:
    """Fetch both live and historical trades, de-duplicated by trade_id."""
    trades: list[dict] = []
    errors: list[Exception] = []
    for endpoint in ("/markets/trades", "/historical/trades"):
        try:
            trades.extend(
                fetch_kalshi_trades(
                    ticker,
                    max_pages=max_pages_per_endpoint,
                    endpoint=endpoint,
                )
            )
        except Exception as exc:  # noqa: BLE001 - keep partial data if one endpoint fails
            errors.append(exc)

    if not trades and errors:
        raise errors[0]

    seen: set[str] = set()
    deduped: list[dict] = []
    for trade in trades:
        key = str(trade.get("trade_id") or f"{trade.get('created_time')}:{trade.get('yes_price_dollars')}")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(trade)

    return sorted(deduped, key=lambda t: str(t.get("created_time") or ""), reverse=True)


def kalshi_snapshot_probability(market: dict) -> float | None:
    candidates: list[float] = []
    for key in (
        "previous_price_dollars",
        "previous_yes_bid_dollars",
        "previous_yes_ask_dollars",
        "last_price_dollars",
        "yes_bid_dollars",
        "yes_ask_dollars",
    ):
        p = normalize_probability(market.get(key))
        if p is not None:
            candidates.append(p)
    for p in candidates:
        if 0.02 <= p <= 0.98:
            return p
    return candidates[0] if candidates else None


def _trades_path(ticker: str) -> Path:
    return RAW_DIR / "kalshi_trades" / f"{ticker}.json"


def _load_cached_trades(ticker: str) -> list[dict]:
    trades_path = _trades_path(ticker)
    if not trades_path.exists():
        return []
    with trades_path.open() as f:
        payload = json.load(f)
    return payload if isinstance(payload, list) else []


def _save_cached_trades(ticker: str, trades: list[dict]) -> None:
    trades_path = _trades_path(ticker)
    trades_path.parent.mkdir(parents=True, exist_ok=True)
    with trades_path.open("w") as f:
        json.dump(trades, f)


def _snapshot_from_trades(trades: list[dict], close_time, *, horizon: str) -> ForecastSnapshot:
    return forecast_from_history(
        trades,
        close_time=close_time,
        source="trade_history",
        horizon=horizon,
        time_keys=("created_time",),
        price_keys=("yes_price_dollars", "yes_price"),
    )


def _metadata_fallback_quality(history_quality: str | None) -> str:
    if history_quality == "missing_history":
        return "metadata_fallback_no_trade_history"
    if history_quality == "no_price_before_cutoff":
        return "metadata_fallback_no_trade_before_target"
    if history_quality == "missing_close_time":
        return "metadata_fallback_missing_close_time"
    if history_quality == "history_fetch_error":
        return "metadata_fallback_history_fetch_error"
    return "metadata_fallback"


def _metadata_fallback_snapshot(
    market: dict,
    *,
    close_time,
    horizon: str,
    history_quality: str | None,
) -> ForecastSnapshot:
    forecast = kalshi_snapshot_probability(market)
    if forecast is None:
        quality = history_quality or "missing_forecast"
        if quality == "no_price_before_cutoff":
            quality = "missing_forecast_no_trade_before_target"
        return fallback_snapshot(
            None,
            source="market_metadata",
            close_time=close_time,
            horizon=horizon,
            quality=quality,
        )

    return fallback_snapshot(
        forecast,
        source="market_metadata",
        close_time=close_time,
        horizon=horizon,
        quality=_metadata_fallback_quality(history_quality),
    )


def kalshi_forecast_snapshot(
    market: dict,
    *,
    horizon: str = PRIMARY_FORECAST_HORIZON,
    fetch_missing_history: bool = False,
) -> ForecastSnapshot:
    ticker = str(market.get("ticker") or "")
    if not ticker:
        return fallback_snapshot(None, source="missing_ticker", horizon=horizon, quality="missing_ticker")

    close_time = parse_timestamp(market.get("close_time") or market.get("settlement_ts"))
    trades = _load_cached_trades(ticker)

    if not trades and fetch_missing_history:
        try:
            trades = fetch_kalshi_trade_history(ticker)
        except Exception:
            trades = []
        if trades:
            _save_cached_trades(ticker, trades)

    history_snapshot: ForecastSnapshot | None = None
    if trades:
        history_snapshot = _snapshot_from_trades(trades, close_time, horizon=horizon)
        if history_snapshot.probability is not None:
            return replace(history_snapshot, source="trade_history")

    return _metadata_fallback_snapshot(
        market,
        close_time=close_time,
        horizon=horizon,
        history_quality=(history_snapshot.quality if history_snapshot else "missing_history"),
    )


def kalshi_forecast_snapshots(
    market: dict,
    *,
    fetch_missing_history: bool = False,
) -> dict[str, ForecastSnapshot]:
    return {
        horizon: kalshi_forecast_snapshot(
            market,
            horizon=horizon,
            fetch_missing_history=fetch_missing_history,
        )
        for horizon in FORECAST_HORIZONS
    }


def last_non_trivial_trade_before(trades: list[dict], close_time: _dt.datetime | None) -> float | None:
    snapshot = _snapshot_from_trades(trades, close_time, horizon=PRIMARY_FORECAST_HORIZON)
    return snapshot.probability


def kalshi_forecast(market: dict, fetch_missing_history: bool = False) -> tuple[float | None, str | None]:
    snapshot = kalshi_forecast_snapshot(market, fetch_missing_history=fetch_missing_history)
    return snapshot.probability, snapshot.source
