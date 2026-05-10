"""
Collect resolved binary markets from Polymarket and preserve the full resolved
inventory locally before analysis filters are applied.

Category is inferred by keyword matching on the event title.

For each market the closing probability is taken from the CLOB price history
of the YES token — specifically the last price point before the market
converges past 98%/2% (i.e. before the outcome is certain). This gives a
meaningful pre-resolution forecast rather than the trivial post-resolution 1/0.

Outputs:
  data/raw/polymarket/events_NNNN.json         — raw paginated event pages
  data/raw/polymarket/history/<token_id>.json  — CLOB price history per market
  data/cleaned/polymarket_markets.csv          — one row per resolved binary market
  data/cleaned/polymarket_history.csv          — full (t, p) time-series per market

Usage:
  python3 src/collect_polymarket.py
  python3 src/collect_polymarket.py --markets-only
  python3 src/collect_polymarket.py --min-volume 0
"""

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace

import pandas as pd
import requests

from src.accuracy import MIN_VOLUME
from src.category_mapping import classify_market
from src.forecast_snapshots import (
    FORECAST_HORIZONS,
    PRIMARY_FORECAST_HORIZON,
    ForecastSnapshot,
    forecast_from_history,
    snapshot_to_columns,
    target_time,
)

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(ROOT, "data", "raw", "polymarket")
RAW_HIST_DIR = os.path.join(RAW_DIR, "history")
CLEAN_DIR = os.path.join(ROOT, "data", "cleaned")
MARKETS_CSV = os.path.join(CLEAN_DIR, "polymarket_markets.csv")
HISTORY_CSV = os.path.join(CLEAN_DIR, "polymarket_history.csv")

SESSION = requests.Session()

# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _get(base: str, path: str, params: dict | None = None) -> dict | list:
    url = f"{base}{path}"
    for attempt in range(4):
        try:
            r = SESSION.get(url, params=params, timeout=30)
        except requests.RequestException as e:
            print(f"  request error ({e}), retry {attempt + 1}")
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 429:
            wait = 2 ** attempt * 5
            print(f"  rate limited, waiting {wait}s...")
            time.sleep(wait)
            continue
        if not r.ok:
            print(f"  HTTP {r.status_code} {url}: {r.text[:200]}")
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"Failed after retries: {url}")


def _parse_list_field(val) -> list:
    """Polymarket sometimes returns list fields as JSON strings."""
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, ValueError):
            return []
    return []


def load_cached_events() -> list[dict]:
    pages = sorted(
        file_name for file_name in os.listdir(RAW_DIR)
        if file_name.startswith("events_") and file_name.endswith(".json")
    )
    events: list[dict] = []
    for file_name in pages:
        path = os.path.join(RAW_DIR, file_name)
        with open(path) as f:
            page = json.load(f)
        if isinstance(page, list):
            events.extend(page)
    return events


# ---------------------------------------------------------------------------
# Events + market extraction
# ---------------------------------------------------------------------------

def fetch_events(min_volume: float) -> list[dict]:
    """Paginate closed events ordered by volume descending."""
    events: list[dict] = []
    offset = 0
    limit = 100
    page = 0

    while True:
        params = {
            "closed": "true",
            "limit": limit,
            "offset": offset,
            "order": "volume",
            "ascending": "false",
        }
        try:
            batch = _get(GAMMA_BASE, "/events", params)
        except Exception as exc:
            cached = load_cached_events()
            if cached:
                print(f"  event API unavailable ({exc}); using {len(cached)} cached events")
                return cached
            raise
        if not isinstance(batch, list):
            batch = []

        if min_volume > 0:
            batch = [e for e in batch if float(e.get("volume") or 0) >= min_volume]
            if not batch:
                print(f"  volume threshold reached at offset {offset}, stopping")
                break

        raw_path = os.path.join(RAW_DIR, f"events_{page:04d}.json")
        with open(raw_path, "w") as f:
            json.dump(batch, f)

        events.extend(batch)
        print(f"  page {page + 1}: {len(batch)} events (total: {len(events)})")

        if len(batch) < limit:
            break
        offset += limit
        page += 1
        time.sleep(0.2)

    return events


def extract_markets(events: list[dict]) -> pd.DataFrame:
    """
    Flatten events → individual binary markets, classify category,
    and extract resolution from outcomePrices.
    """
    rows = []

    for event in events:
        event_title = event.get("title", "")
        for m in event.get("markets", []):
            outcomes = _parse_list_field(m.get("outcomes", []))
            token_ids = _parse_list_field(m.get("clobTokenIds", []))
            outcome_prices = _parse_list_field(m.get("outcomePrices", []))

            if len(outcomes) != 2 or len(token_ids) != 2:
                continue
            if m.get("umaResolutionStatus") != "resolved":
                continue

            try:
                yes_price = float(outcome_prices[0]) if outcome_prices else None
            except (ValueError, TypeError):
                yes_price = None

            if yes_price is None:
                continue
            if yes_price >= 0.99:
                resolution = "YES"
            elif yes_price <= 0.01:
                resolution = "NO"
            else:
                continue  # ambiguous

            category = classify_market(
                platform="polymarket",
                market_id=str(m.get("id") or ""),
                title=m.get("question", "") or event_title,
                slug=m.get("slug", "") or event.get("slug", ""),
                raw_platform_category=str(event.get("category") or ""),
                raw_tags=event.get("tags") or [],
                context_fields=[
                    event_title,
                    str(event.get("slug") or ""),
                    str(event.get("ticker") or ""),
                    str(event.get("description") or ""),
                ],
            )

            rows.append({
                "id": m.get("id", ""),
                "event_id": event.get("id"),
                "event_title": event_title,
                "question": m.get("question", ""),
                "category": category.canonical_category,
                "category_source": category.category_source,
                "category_confidence": category.category_confidence,
                "needs_review": category.needs_review,
                "review_reason": category.review_reason,
                "raw_platform_category": category.raw_platform_category,
                "raw_tags": category.raw_tags,
                "slug": m.get("slug", ""),
                "source_event_id": event.get("id") or event.get("slug"),
                "yes_token_id": token_ids[0],
                "no_token_id": token_ids[1],
                "start_date": m.get("startDate") or m.get("startDateIso") or event.get("startDate"),
                "end_date": (
                    m.get("closedTime")
                    or m.get("endDate")
                    or m.get("endDateIso")
                    or event.get("closedTime")
                    or event.get("endDate")
                ),
                "resolution": resolution,
                "volume": float(m.get("volume") or 0),
                "enable_order_book": bool(m.get("enableOrderBook")) if m.get("enableOrderBook") is not None else None,
                "market_type": m.get("marketType"),
                # closing_prob filled in after history fetch
                "closing_prob": None,
            })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# CLOB price history
# ---------------------------------------------------------------------------

def fetch_price_history(
    token_id: str,
    *,
    start_ts: int | None = None,
    end_ts: int | None = None,
    interval: str | None = "max",
    fidelity: int | None = 1,
) -> list[dict]:
    params: dict[str, object] = {"market": token_id}
    if interval is not None:
        params["interval"] = interval
    if fidelity is not None:
        params["fidelity"] = fidelity
    if start_ts is not None:
        params["startTs"] = start_ts
    if end_ts is not None:
        params["endTs"] = end_ts
    data = _get(CLOB_BASE, "/prices-history", params)
    return data.get("history", [])


def forecast_snapshot_from_history(
    history: list[dict],
    close_time,
    *,
    horizon: str = PRIMARY_FORECAST_HORIZON,
) -> ForecastSnapshot:
    return forecast_from_history(
        history,
        close_time=close_time,
        source="history",
        horizon=horizon,
        time_keys=("t",),
        price_keys=("p",),
    )


def closing_probability(
    history: list[dict],
    close_time=None,
    *,
    horizon: str = PRIMARY_FORECAST_HORIZON,
) -> float | None:
    """
    Last meaningful YES price before the forecast cutoff. If close_time is
    missing, this falls back to the old behavior of using the last non-trivial
    point in the cached history.
    """
    return forecast_snapshot_from_history(history, close_time, horizon=horizon).probability


def _load_cached_histories(token_id: str) -> dict[str, list[dict]]:
    raw_path = os.path.join(RAW_HIST_DIR, f"{token_id}.json")
    if not os.path.exists(raw_path):
        return {}

    with open(raw_path) as f:
        payload = json.load(f)

    if isinstance(payload, list):
        return {PRIMARY_FORECAST_HORIZON: payload}
    if isinstance(payload, dict):
        if "horizons" in payload and isinstance(payload["horizons"], dict):
            return {
                str(horizon): points
                for horizon, points in payload["horizons"].items()
                if isinstance(points, list)
            }
        return {
            str(horizon): points
            for horizon, points in payload.items()
            if isinstance(points, list)
        }
    return {}


def _save_cached_histories(token_id: str, histories: dict[str, list[dict]]) -> None:
    raw_path = os.path.join(RAW_HIST_DIR, f"{token_id}.json")
    with open(raw_path, "w") as f:
        json.dump({"horizons": histories}, f)


def _snapshot_with_labels(snapshot: ForecastSnapshot, *, source: str, quality: str | None = None) -> ForecastSnapshot:
    return replace(
        snapshot,
        source=source if snapshot.probability is not None else None,
        quality=quality or snapshot.quality,
    )


def _fetch_horizon_history(token_id: str, close_time, horizon: str) -> tuple[list[dict], str]:
    cutoff = target_time(close_time, horizon)
    if cutoff is None:
        history = fetch_price_history(token_id, interval="max", fidelity=1)
        return history, "clob_history_missing_close_time"

    end_ts = int(cutoff.timestamp())
    history = fetch_price_history(
        token_id,
        end_ts=end_ts,
        interval="max",
        fidelity=1,
    )
    if history:
        return history, "clob_history_endts"

    # Fallback path when the endTs query returns empty. We still score using
    # target-time filtering from forecast_from_history.
    history = fetch_price_history(token_id, interval="max", fidelity=1)
    return history, "clob_history_endts_fallback_full"


def _fetch_one(row: dict) -> tuple[str, dict[str, list[dict]], dict[str, ForecastSnapshot]]:
    token_id = row["yes_token_id"]
    close_time = row.get("end_date")
    cached = _load_cached_histories(token_id)
    histories: dict[str, list[dict]] = {}
    snapshots: dict[str, ForecastSnapshot] = {}

    try:
        for horizon in FORECAST_HORIZONS:
            history = cached.get(horizon)
            source = "clob_history_cache"
            if history is None:
                history, source = _fetch_horizon_history(token_id, close_time, horizon)
                time.sleep(0.02)
            histories[horizon] = history
            snapshot = forecast_snapshot_from_history(history, close_time, horizon=horizon)
            if source == "clob_history_endts_fallback_full" and snapshot.probability is not None:
                snapshot = _snapshot_with_labels(snapshot, source=source, quality="target_time_fallback_full_history")
            else:
                snapshot = _snapshot_with_labels(snapshot, source=source)
            snapshots[horizon] = snapshot
    except Exception as exc:
        print(f"  ERROR {token_id}: {exc}")
        for horizon in FORECAST_HORIZONS:
            history = histories.get(horizon, [])
            snapshots[horizon] = _snapshot_with_labels(
                forecast_snapshot_from_history(history, close_time, horizon=horizon),
                source="clob_history_error",
                quality="history_fetch_error",
            )

    _save_cached_histories(token_id, histories)
    return token_id, histories, snapshots


def collect_history(df_markets: pd.DataFrame, workers: int = 10) -> tuple[pd.DataFrame, pd.DataFrame]:
    history_rows: list[dict] = []
    forecast_metadata: dict[str, dict[str, ForecastSnapshot]] = {}
    total = len(df_markets)
    records = df_markets.to_dict("records")
    token_to_market_id = {r["yes_token_id"]: r["id"] for r in records}
    done = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_fetch_one, r): r for r in records}
        for future in as_completed(futures):
            token_id, histories, snapshots = future.result()
            market_id = token_to_market_id[token_id]
            forecast_metadata[market_id] = snapshots
            for horizon, history in histories.items():
                for point in history:
                    history_rows.append({
                        "market_id": market_id,
                        "yes_token_id": token_id,
                        "horizon": horizon,
                        "t": point.get("t"),
                        "p": point.get("p"),
                    })
            done += 1
            if done % 100 == 0:
                print(f"  {done}/{total} markets processed")

    df_markets = df_markets.copy()
    for horizon in FORECAST_HORIZONS:
        records_for_horizon = {
            market_id: snapshots[horizon]
            for market_id, snapshots in forecast_metadata.items()
            if horizon in snapshots
        }
        columns = {
            market_id: snapshot_to_columns(snapshot, horizon=horizon)
            for market_id, snapshot in records_for_horizon.items()
        }
        for field in (
            "forecast_prob",
            "forecast_source",
            "forecast_observed_at",
            "forecast_target_time",
            "forecast_seconds_before_close",
            "forecast_horizon",
            "forecast_quality",
        ):
            suffix = "" if horizon == PRIMARY_FORECAST_HORIZON else f"_{horizon}"
            column_name = f"{field}{suffix}"
            df_markets[column_name] = df_markets["id"].map(
                lambda market_id: columns.get(market_id, {}).get(column_name)
            )

    df_markets["closing_prob"] = df_markets["forecast_prob"]
    return df_markets, pd.DataFrame(history_rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(markets_only: bool = False, min_volume: float = 0.0) -> None:
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(RAW_HIST_DIR, exist_ok=True)
    os.makedirs(CLEAN_DIR, exist_ok=True)

    threshold_note = f"${min_volume:,.0f}" if min_volume > 0 else "no raw inventory filter"
    print(f"Fetching closed Polymarket events (min volume: {threshold_note})...")
    events = fetch_events(min_volume=min_volume)
    print(f"Events fetched: {len(events)}")

    df_markets = extract_markets(events)
    print(f"Binary resolved markets after category filter: {len(df_markets)}")
    if not df_markets.empty:
        print(df_markets["category"].value_counts().to_string())
        print(df_markets["resolution"].value_counts().to_string())

    if markets_only:
        df_markets.to_csv(MARKETS_CSV, index=False)
        print(f"Wrote {len(df_markets)} rows to {MARKETS_CSV}")
        return

    print("\nFetching CLOB price history...")
    df_markets, df_history = collect_history(df_markets)

    df_markets.to_csv(MARKETS_CSV, index=False)
    print(f"Wrote {len(df_markets)} rows to {MARKETS_CSV}")

    df_history.to_csv(HISTORY_CSV, index=False)
    print(f"Wrote {len(df_history)} rows to {HISTORY_CSV}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--markets-only", action="store_true")
    parser.add_argument("--min-volume", type=float, default=0.0)
    args = parser.parse_args()
    main(markets_only=args.markets_only, min_volume=args.min_volume)
