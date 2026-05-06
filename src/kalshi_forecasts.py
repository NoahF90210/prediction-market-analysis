from __future__ import annotations

import json
import time
from pathlib import Path

from src.accuracy import last_non_trivial_probability, normalize_probability, to_float
from src.settings import RAW_DIR


def kalshi_volume(market: dict) -> float | None:
    for key in ("volume", "volume_dollars", "volume_fp"):
        volume = to_float(market.get(key))
        if volume is not None:
            return volume
    return None


def fetch_kalshi_history(ticker: str, historical: bool = False) -> list[dict]:
    import kalshi_client as kalshi

    prefix = "/historical" if historical else ""
    entries = []
    cursor = None
    while True:
        params = {"limit": 1000}
        if cursor:
            params["cursor"] = cursor
        data = kalshi.get(f"{prefix}/markets/{ticker}/history", params)
        batch = data.get("history", [])
        entries.extend(batch)
        cursor = data.get("cursor")
        if not cursor or not batch:
            break
        time.sleep(0.1)
    return entries


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


def kalshi_forecast(market: dict, fetch_missing_history: bool = False) -> tuple[float | None, str | None]:
    ticker = market.get("ticker")
    if not ticker:
        return None, None
    history_path = RAW_DIR / "history" / f"{ticker}.json"
    if history_path.exists():
        with history_path.open() as f:
            entries = json.load(f)
        forecast = last_non_trivial_probability(entries)
        return forecast, "history" if forecast is not None else None
    if fetch_missing_history:
        historical = bool(market.get("settlement_ts"))
        entries = fetch_kalshi_history(ticker, historical=historical)
        history_path.parent.mkdir(parents=True, exist_ok=True)
        with history_path.open("w") as f:
            json.dump(entries, f)
        forecast = last_non_trivial_probability(entries)
        return forecast, "history" if forecast is not None else None
    forecast = kalshi_snapshot_probability(market)
    return forecast, "snapshot_fallback" if forecast is not None else None
