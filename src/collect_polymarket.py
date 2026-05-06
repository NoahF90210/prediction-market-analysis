"""
Collect resolved binary markets from Polymarket, filtered to liquid elections
and sports markets.

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
  python3 src/collect_polymarket.py --min-volume 100000
"""

import argparse
import json
import os
import time

import pandas as pd
import requests

from accuracy import MIN_VOLUME

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
# Category classification
# ---------------------------------------------------------------------------

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "elections": [
        "election", "president", "senate", "congress", "governor", "parliament",
        "prime minister", "vote", "ballot", "primary", "referendum", "runoff",
        "mayor", "gubernatorial", "midterm", "democrat", "republican",
    ],
    "sports": [
        "nba", "nfl", "mlb", "nhl", "super bowl", "world series", "world cup",
        "champions league", "premier league", "la liga", "bundesliga", "serie a",
        "stanley cup", "playoffs", "championship", "finals", "tournament",
        "soccer", "football", "basketball", "baseball", "hockey", "tennis",
        "golf", "ufc", "mma", "boxing", "f1", "formula 1", "formula one",
        "cricket", "rugby", "olympics", "wimbledon", "masters", "grand slam",
        "counter-strike", "valorant", "league of legends", "dota", "esports",
        "cs2", "lol", "overwatch",
    ],
}


def classify_category(title: str) -> str | None:
    title_lower = title.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in title_lower for kw in keywords):
            return category
    return None


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
        batch = _get(GAMMA_BASE, "/events", params)
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
    skipped_category = 0

    for event in events:
        event_title = event.get("title", "")
        category = classify_category(event_title)
        if category is None:
            skipped_category += 1
            continue

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

            rows.append({
                "id": m.get("id", ""),
                "event_title": event_title,
                "question": m.get("question", ""),
                "category": category,
                "slug": m.get("slug", ""),
                "yes_token_id": token_ids[0],
                "no_token_id": token_ids[1],
                "start_date": m.get("startDate") or event.get("startDate"),
                "end_date": m.get("endDate") or event.get("endDate"),
                "resolution": resolution,
                "volume": float(m.get("volume") or 0),
                # closing_prob filled in after history fetch
                "closing_prob": None,
            })

    print(f"  ({skipped_category} events skipped — no matching category)")
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# CLOB price history
# ---------------------------------------------------------------------------

def fetch_price_history(token_id: str) -> list[dict]:
    data = _get(CLOB_BASE, "/prices-history", {
        "market": token_id,
        "interval": "max",
        "fidelity": 60,
    })
    return data.get("history", [])


def closing_probability(history: list[dict]) -> float | None:
    """
    The last price point where the market still had meaningful uncertainty
    (between 2% and 98%). Falls back to the very last price if none found.
    """
    if not history:
        return None
    for point in reversed(history):
        p = point.get("p")
        if p is None:
            continue
        p = float(p)
        if 0.02 <= p <= 0.98:
            return p
    # all points are trivial (market was never uncertain or already resolved)
    last = history[-1].get("p")
    return float(last) if last is not None else None


def collect_history(df_markets: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    history_rows: list[dict] = []
    closing_probs: dict[str, float | None] = {}
    total = len(df_markets)

    for i, (_, row) in enumerate(df_markets.iterrows()):
        token_id = row["yes_token_id"]
        raw_path = os.path.join(RAW_HIST_DIR, f"{token_id}.json")

        if os.path.exists(raw_path):
            with open(raw_path) as f:
                history = json.load(f)
        else:
            try:
                history = fetch_price_history(token_id)
            except Exception as e:
                print(f"  ERROR {token_id}: {e}")
                history = []
            with open(raw_path, "w") as f:
                json.dump(history, f)
            time.sleep(0.15)

        closing_probs[row["id"]] = closing_probability(history)

        for point in history:
            history_rows.append({
                "market_id": row["id"],
                "yes_token_id": token_id,
                "t": point.get("t"),
                "p": point.get("p"),
            })

        if (i + 1) % 100 == 0:
            print(f"  {i + 1}/{total} markets processed")

    df_markets = df_markets.copy()
    df_markets["closing_prob"] = df_markets["id"].map(closing_probs)
    return df_markets, pd.DataFrame(history_rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(markets_only: bool = False, min_volume: float = MIN_VOLUME) -> None:
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(RAW_HIST_DIR, exist_ok=True)
    os.makedirs(CLEAN_DIR, exist_ok=True)

    print(f"Fetching closed Polymarket events (min volume: ${min_volume:,.0f})...")
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
    parser.add_argument("--min-volume", type=float, default=MIN_VOLUME)
    args = parser.parse_args()
    main(markets_only=args.markets_only, min_volume=args.min_volume)
