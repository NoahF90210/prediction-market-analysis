"""Fetch and cache trade history for every Kalshi ticker in the inventory.

Reads tickers from data/cleaned/kalshi_resolved_inventory.csv (or
accuracy_markets.csv if the inventory isn't present) and writes one JSON
file per ticker under data/raw/kalshi_trades/. Skips tickers already cached.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from src.kalshi_forecasts import fetch_kalshi_trades
from src.settings import CLEAN_DIR, RAW_DIR

CACHE_DIR = RAW_DIR / "kalshi_trades"


def kalshi_tickers() -> list[str]:
    inv_path = CLEAN_DIR / "kalshi_resolved_inventory.csv"
    if inv_path.exists():
        df = pd.read_csv(inv_path)
        col = "source_market_id" if "source_market_id" in df.columns else "ticker"
        return df[col].dropna().astype(str).unique().tolist()
    df = pd.read_csv(CLEAN_DIR / "accuracy_markets.csv")
    return (
        df.loc[df["platform"] == "kalshi", "market_id"]
        .dropna().astype(str).unique().tolist()
    )


def main() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tickers = kalshi_tickers()
    print(f"{len(tickers)} Kalshi tickers")
    fetched = skipped = errors = 0
    for i, ticker in enumerate(tickers, 1):
        out = CACHE_DIR / f"{ticker}.json"
        if out.exists():
            skipped += 1
            continue
        try:
            trades = fetch_kalshi_trades(ticker)
        except Exception as e:  # noqa: BLE001 — keep going, log
            print(f"[{i}/{len(tickers)}] {ticker}: ERROR {e}", file=sys.stderr)
            errors += 1
            continue
        out.write_text(json.dumps(trades))
        fetched += 1
        if fetched % 25 == 0:
            print(f"[{i}/{len(tickers)}] fetched={fetched} skipped={skipped} errors={errors}")
    print(f"done: fetched={fetched} skipped={skipped} errors={errors}")


if __name__ == "__main__":
    main()
