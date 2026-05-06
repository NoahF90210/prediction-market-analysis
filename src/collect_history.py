import json
import os
import sys
import time

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src import kalshi_client as kalshi
from src.accuracy import MIN_VOLUME, last_non_trivial_probability

RAW_HISTORY_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw", "history"
)
CLEAN_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cleaned")
MARKETS_CSV = os.path.join(CLEAN_DIR, "markets.csv")


def fetch_history(ticker: str, historical: bool = False) -> list[dict]:
    entries = []
    cursor = None
    prefix = "/historical" if historical else ""
    while True:
        params = {"limit": 1000}
        if cursor:
            params["cursor"] = cursor
        try:
            data = kalshi.get(f"{prefix}/markets/{ticker}/history", params)
        except Exception as e:
            print(f"  ERROR {ticker}: {e}")
            break
        batch = data.get("history", [])
        entries.extend(batch)
        cursor = data.get("cursor")
        if not cursor or not batch:
            break
        time.sleep(0.1)
    return entries


def main(min_volume: int = MIN_VOLUME):
    os.makedirs(RAW_HISTORY_DIR, exist_ok=True)

    markets = pd.read_csv(MARKETS_CSV)
    if min_volume > 0:
        before = len(markets)
        markets = markets[markets["volume"].fillna(0) >= min_volume]
        print(f"Volume filter (>=${min_volume:,}): {before} → {len(markets)} markets")
    tickers = markets["ticker"].tolist()
    print(f"Fetching history for {len(tickers)} markets...")

    rows = []
    for i, ticker in enumerate(tickers):
        raw_path = os.path.join(RAW_HISTORY_DIR, f"{ticker}.json")

        if os.path.exists(raw_path):
            with open(raw_path) as f:
                entries = json.load(f)
        else:
            entries = fetch_history(ticker)
            if not entries:
                entries = fetch_history(ticker, historical=True)
            with open(raw_path, "w") as f:
                json.dump(entries, f)
            time.sleep(0.1)

        closing_prob = last_non_trivial_probability(entries)

        for entry in entries:
            rows.append({
                "ticker": ticker,
                "ts": entry.get("ts"),
                "yes_price": entry.get("yes_price"),
                "closing_prob": closing_prob,
            })

        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(tickers)} tickers processed")

    df = pd.DataFrame(rows)
    out_path = os.path.join(CLEAN_DIR, "history.csv")
    df.to_csv(out_path, index=False)
    print(f"\nWrote {len(df)} rows to {out_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-volume", type=int, default=MIN_VOLUME)
    args = parser.parse_args()
    main(min_volume=args.min_volume)
