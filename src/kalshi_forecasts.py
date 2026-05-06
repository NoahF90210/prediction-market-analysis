from __future__ import annotations

import datetime as _dt
import json
import time
from pathlib import Path

from src.accuracy import NON_TRIVIAL_MAX, NON_TRIVIAL_MIN, last_non_trivial_probability, normalize_probability, to_float
from src.settings import RAW_DIR

# Lead-time guard: ignore trades within this many seconds of close_time when
# deriving a "forecast" price. Sports markets trade up to the final second when
# the outcome is essentially decided; scoring those would measure clairvoyance,
# not forecasting. 30 minutes is a defensible cutoff that still preserves most
# liquid markets.
LEAD_TIME_GUARD_SECONDS = 1800


def kalshi_volume(market: dict) -> float | None:
    for key in ("volume", "volume_dollars", "volume_fp"):
        volume = to_float(market.get(key))
        if volume is not None:
            return volume
    return None


def fetch_kalshi_trades(ticker: str, max_pages: int = 4) -> list[dict]:
    """Fetch trades for a settled Kalshi market, newest first.

    The /markets/trades endpoint paginates with a cursor and returns at most
    1000 trades per page. We cap pages to keep backfill bounded; the most
    recent ~4000 trades are far more than enough to find the last
    non-trivial pre-resolution price for any market in our universe.
    """
    import kalshi_client as kalshi

    trades: list[dict] = []
    cursor = None
    for _ in range(max_pages):
        params = {"ticker": ticker, "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        data = kalshi.get("/markets/trades", params)
        batch = data.get("trades", [])
        trades.extend(batch)
        cursor = data.get("cursor")
        if not cursor or not batch:
            break
        time.sleep(0.1)
    return trades


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
    return None


def _parse_ts(value) -> _dt.datetime | None:
    if not value:
        return None
    try:
        return _dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def last_non_trivial_trade_before(trades: list[dict], close_time: _dt.datetime | None) -> float | None:
    """Trades are newest-first. Return the most recent non-trivial yes_price
    observed at least LEAD_TIME_GUARD_SECONDS before close_time."""
    if close_time is None:
        return last_non_trivial_probability(list(reversed(trades)))
    cutoff = close_time - _dt.timedelta(seconds=LEAD_TIME_GUARD_SECONDS)
    for t in trades:  # newest first → first match is most recent qualifying
        ts = _parse_ts(t.get("created_time"))
        if ts is None or ts > cutoff:
            continue
        p = normalize_probability(t.get("yes_price_dollars") or t.get("yes_price"))
        if p is not None and NON_TRIVIAL_MIN <= p <= NON_TRIVIAL_MAX:
            return p
    return None


def kalshi_forecast(market: dict, fetch_missing_history: bool = False) -> tuple[float | None, str | None]:
    ticker = market.get("ticker")
    if not ticker:
        return None, None
    close_time = _parse_ts(market.get("close_time") or market.get("settlement_ts"))
    trades_path = RAW_DIR / "kalshi_trades" / f"{ticker}.json"
    if trades_path.exists():
        with trades_path.open() as f:
            trades = json.load(f)
        forecast = last_non_trivial_trade_before(trades, close_time)
        if forecast is not None:
            return forecast, "history"
    if fetch_missing_history:
        trades = fetch_kalshi_trades(ticker)
        trades_path.parent.mkdir(parents=True, exist_ok=True)
        with trades_path.open("w") as f:
            json.dump(trades, f)
        forecast = last_non_trivial_trade_before(trades, close_time)
        if forecast is not None:
            return forecast, "history"
    forecast = kalshi_snapshot_probability(market)
    return forecast, "snapshot_fallback" if forecast is not None else None
