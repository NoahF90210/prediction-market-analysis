"""Resumable, streaming Polymarket collection for the approved 2025 study."""
from __future__ import annotations

import argparse
import gzip
import json
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from src.polymarket.price_history import select_latest_pre_cutoff
from src.polymarket.spec import load_config

ROOT = Path(__file__).resolve().parents[2]
RAW_ROOT = ROOT / "data" / "raw" / "polymarket" / "rebuild_full"
CHECKPOINT_ROOT = ROOT / "data" / "checkpoints" / "polymarket"
MARKET_PAGES = RAW_ROOT / "market_pages"
PRICE_RAW = RAW_ROOT / "prices"
INVENTORY_JSONL = RAW_ROOT / "market_inventory.jsonl"
INVENTORY_EXCLUSIONS = RAW_ROOT / "inventory_exclusions.jsonl"
MARKET_CHECKPOINT = CHECKPOINT_ROOT / "market_inventory.json"
PRICE_RESULTS = RAW_ROOT / "price_results.jsonl"
PRICE_CHECKPOINT = CHECKPOINT_ROOT / "price_collection.json"
GAMMA_URL = "https://gamma-api.polymarket.com/markets/keyset"
CLOB_URL = "https://clob.polymarket.com/prices-history"
DEFAULT_PADDING_DAYS = 180
_THREAD_STATE = threading.local()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace(" ", "T").replace("+00", "+00:00"))
    except ValueError:
        return None


def parse_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def session() -> requests.Session:
    value = getattr(_THREAD_STATE, "session", None)
    if value is None:
        value = requests.Session()
        value.headers.update({"User-Agent": "prediction-market-analysis/phase3"})
        _THREAD_STATE.session = value
    return value


def get_json(url: str, params: dict[str, Any], retries: int = 5) -> dict[str, Any]:
    for attempt in range(retries):
        try:
            response = session().get(url, params=params, timeout=45)
        except requests.RequestException:
            if attempt + 1 == retries:
                raise
            time.sleep(min(2**attempt, 16))
            continue
        if response.status_code == 200:
            payload = response.json()
            if not isinstance(payload, dict):
                raise RuntimeError(f"expected JSON object from {url}")
            return payload
        if response.status_code == 429 or response.status_code >= 500:
            if attempt + 1 < retries:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else min(2**attempt, 16)
                time.sleep(delay)
                continue
        raise RuntimeError(f"HTTP {response.status_code} from {response.url}: {response.text[:200]}")
    raise RuntimeError(f"request failed after {retries} attempts: {url}")


def write_gzip_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(value, handle, separators=(",", ":"))


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
        handle.flush()


def read_jsonl_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    ids: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                if row.get("market_id"):
                    ids.add(str(row["market_id"]))
    return ids


def checkpoint(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def market_candidate(market: dict[str, Any], config: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    market_id = str(market.get("id") or "")
    if not market_id:
        return None, "malformed_api_record"
    if market.get("closed") is not True or market.get("umaResolutionStatus") != "resolved":
        return None, "not_resolved"
    resolved_at = parse_time(market.get("closedTime"))
    start = parse_time(config["resolution_start"])
    end = parse_time(config["resolution_end"])
    if resolved_at is None or start is None or end is None:
        return None, "missing_resolution_timestamp"
    if not (start <= resolved_at < end):
        return None, "resolution_outside_window"
    outcomes = parse_json_list(market.get("outcomes"))
    token_ids = parse_json_list(market.get("clobTokenIds"))
    prices = parse_json_list(market.get("outcomePrices"))
    normalized_outcomes = [str(value).strip().lower() for value in outcomes]
    if len(outcomes) != 2 or normalized_outcomes != ["yes", "no"] or len(token_ids) != 2:
        return None, "not_yes_no"
    if not token_ids[0]:
        return None, "missing_yes_token"
    numeric_prices = []
    try:
        numeric_prices = [float(value) for value in prices]
    except (TypeError, ValueError):
        return None, "missing_resolution_outcome"
    if len(numeric_prices) != 2 or not (numeric_prices[0] in (0.0, 1.0) and numeric_prices[1] in (0.0, 1.0)):
        return None, "missing_resolution_outcome"
    events = market.get("events") or []
    event = events[0] if events else {}
    event_id = str(event.get("id") or "")
    if not event_id:
        return None, "missing_event_id"
    return {
        "market_id": market_id,
        "event_id": event_id,
        "event_title": event.get("title") or "",
        "event_slug": event.get("slug") or "",
        "question": market.get("question") or "",
        "slug": market.get("slug") or "",
        "category": market.get("category") or "",
        "tags": [tag.get("label") for tag in (market.get("tags") or []) if isinstance(tag, dict)],
        "condition_id": market.get("conditionId") or "",
        "yes_token_id": str(token_ids[0]),
        "no_token_id": str(token_ids[1]),
        "outcomes": outcomes,
        "outcome_prices": numeric_prices,
        "resolution": 1 if numeric_prices[0] == 1.0 else 0,
        "resolution_timestamp": resolved_at.isoformat().replace("+00:00", "Z"),
        "end_date": market.get("endDate"),
        "uma_end_date": market.get("umaEndDate"),
        "uma_resolution_status": market.get("umaResolutionStatus"),
        "resolution_source": market.get("resolutionSource") or "",
        "volume": market.get("volumeNum") or market.get("volume"),
        "market_url": f"https://polymarket.com/event/{event.get('slug') or market.get('slug')}",
    }, None


def inventory(
    padding_days: int = DEFAULT_PADDING_DAYS,
    limit: int = 500,
    max_pages: int | None = None,
    reset: bool = False,
) -> dict[str, Any]:
    config = load_config(ROOT / "config" / "analysis.json")
    start = parse_time(config["resolution_start"])
    end = parse_time(config["resolution_end"])
    assert start and end
    query_start = (start - timedelta(days=padding_days)).isoformat().replace("+00:00", "Z")
    query_end = (end + timedelta(days=padding_days)).isoformat().replace("+00:00", "Z")
    params: dict[str, Any] = {
        "closed": "true",
        "limit": limit,
        "order": "endDate",
        "ascending": "true",
        "end_date_min": query_start,
        "end_date_max": query_end,
        "include_tag": "true",
    }
    if reset:
        if MARKET_PAGES.exists():
            shutil.rmtree(MARKET_PAGES)
        for path in (INVENTORY_JSONL, INVENTORY_EXCLUSIONS, MARKET_CHECKPOINT):
            path.unlink(missing_ok=True)
    state = json.loads(MARKET_CHECKPOINT.read_text()) if MARKET_CHECKPOINT.exists() else {}
    if state.get("completed"):
        return state
    if state.get("params") and state["params"] != params:
        raise RuntimeError("existing inventory checkpoint was created with different parameters")
    cursor = state.get("next_cursor")
    page = int(state.get("page_count", 0))
    raw_count = int(state.get("raw_market_count", 0))
    duplicate_count = int(state.get("duplicate_count", 0))
    exclusion_counts = dict(state.get("exclusion_counts", {}))
    seen_ids = read_jsonl_ids(INVENTORY_JSONL) | read_jsonl_ids(INVENTORY_EXCLUSIONS)
    started = state.get("started_at") or utc_now()
    while True:
        request_params = dict(params)
        if cursor:
            request_params["after_cursor"] = cursor
        retrieved_at = utc_now()
        payload = get_json(GAMMA_URL, request_params)
        markets = payload.get("markets")
        if not isinstance(markets, list):
            raise RuntimeError("Gamma response missing markets list")
        page += 1
        raw_count += len(markets)
        write_gzip_json(MARKET_PAGES / f"page_{page:06d}.json.gz", {
            "retrieved_at": retrieved_at,
            "request_params": request_params,
            "payload": payload,
        })
        candidates = []
        exclusions = []
        for market in markets:
            market_id = str(market.get("id") or "")
            if market_id and market_id in seen_ids:
                duplicate_count += 1
                continue
            candidate, reason = market_candidate(market, config)
            row = candidate or {
                "market_id": market_id,
                "question": market.get("question") or "",
                "resolution_timestamp": market.get("closedTime"),
                "reason": reason or "malformed_api_record",
            }
            if candidate:
                candidates.append(candidate)
            else:
                exclusions.append(row)
                exclusion_counts[reason or "malformed_api_record"] = exclusion_counts.get(reason or "malformed_api_record", 0) + 1
            if market_id:
                seen_ids.add(market_id)
        append_jsonl(INVENTORY_JSONL, candidates)
        append_jsonl(INVENTORY_EXCLUSIONS, exclusions)
        cursor = payload.get("next_cursor")
        state = {
            "started_at": started,
            "updated_at": utc_now(),
            "completed": not bool(cursor),
            "params": params,
            "next_cursor": cursor or None,
            "page_count": page,
            "raw_market_count": raw_count,
            "candidate_count": len(seen_ids) - sum(exclusion_counts.values()),
            "unique_seen_count": len(seen_ids),
            "duplicate_count": duplicate_count,
            "exclusion_counts": exclusion_counts,
            "candidate_path": str(INVENTORY_JSONL),
            "exclusion_path": str(INVENTORY_EXCLUSIONS),
        }
        checkpoint(MARKET_CHECKPOINT, state)
        print(json.dumps({"page": page, "page_markets": len(markets), "candidates_total": state["candidate_count"], "raw_total": raw_count, "next_cursor": bool(cursor)}))
        if not cursor or (max_pages is not None and page >= max_pages):
            return state


def load_candidates() -> list[dict[str, Any]]:
    rows = []
    with INVENTORY_JSONL.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def price_one(row: dict[str, Any], max_age_hours: int) -> dict[str, Any]:
    resolution_at = parse_time(row["resolution_timestamp"])
    if resolution_at is None:
        raise ValueError(f"invalid resolution timestamp for {row['market_id']}")
    cutoff = resolution_at - timedelta(hours=24)
    start_ts = int((cutoff - timedelta(hours=max_age_hours)).timestamp())
    end_ts = int(cutoff.timestamp())
    params = {"market": row["yes_token_id"], "startTs": start_ts, "endTs": end_ts, "fidelity": 60}
    retrieved_at = utc_now()
    try:
        payload = get_json(CLOB_URL, params)
        history = payload.get("history")
        if not isinstance(history, list):
            raise RuntimeError("history is not a list")
        raw_path = PRICE_RAW / f"{row['market_id']}.json.gz"
        write_gzip_json(raw_path, {"retrieved_at": retrieved_at, "request_params": params, "payload": payload})
        try:
            selected = select_latest_pre_cutoff(history, cutoff, max_age_hours)
        except ValueError as exc:
            return {"market_id": row["market_id"], "status": "excluded", "exclusion_reason": "missing_price_history" if not history else "snapshot_too_stale", "error": str(exc), "request_params": params, "raw_path": str(raw_path), "retrieved_at": retrieved_at}
        return {"market_id": row["market_id"], "status": "included", "exclusion_reason": "", "probability": selected["price"], "probability_timestamp": selected["timestamp"], "snapshot_cutoff": cutoff.isoformat().replace("+00:00", "Z"), "snapshot_age_hours": selected["age_hours"], "request_params": params, "raw_path": str(raw_path), "retrieved_at": retrieved_at}
    except Exception as exc:
        return {"market_id": row["market_id"], "status": "failed", "exclusion_reason": "api_request_failed", "error": str(exc), "request_params": params, "retrieved_at": retrieved_at}


def prices(workers: int = 12, batch_size: int = 96) -> dict[str, Any]:
    config = load_config(ROOT / "config" / "analysis.json")
    candidates = load_candidates()
    done_ids = read_jsonl_ids(PRICE_RESULTS)
    pending = [row for row in candidates if row["market_id"] not in done_ids]
    state = json.loads(PRICE_CHECKPOINT.read_text()) if PRICE_CHECKPOINT.exists() else {}
    completed = int(state.get("completed_count", len(done_ids)))
    print(json.dumps({"candidates": len(candidates), "already_terminal": len(done_ids), "pending": len(pending), "workers": workers}))
    for offset in range(0, len(pending), batch_size):
        batch = pending[offset:offset + batch_size]
        results = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(price_one, row, int(config["maximum_snapshot_age_hours"])) for row in batch]
            for future in as_completed(futures):
                results.append(future.result())
        append_jsonl(PRICE_RESULTS, results)
        completed += len(results)
        state = {"updated_at": utc_now(), "completed": completed == len(candidates), "candidate_count": len(candidates), "completed_count": completed, "included_count": sum(result["status"] == "included" for result in results) + int(state.get("included_count", 0)), "excluded_count": sum(result["status"] == "excluded" for result in results) + int(state.get("excluded_count", 0)), "failed_count": sum(result["status"] == "failed" for result in results) + int(state.get("failed_count", 0)), "result_path": str(PRICE_RESULTS)}
        checkpoint(PRICE_CHECKPOINT, state)
        print(json.dumps({"completed": completed, "total": len(candidates), "batch": len(results)}))
    return state


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    inv = subparsers.add_parser("inventory")
    inv.add_argument("--padding-days", type=int, default=DEFAULT_PADDING_DAYS)
    inv.add_argument("--limit", type=int, default=500)
    inv.add_argument("--max-pages", type=int)
    inv.add_argument("--reset", action="store_true", help="Discard only this collector's local checkpoint and raw pages")
    price = subparsers.add_parser("prices")
    price.add_argument("--workers", type=int, default=12)
    price.add_argument("--batch-size", type=int, default=96)
    subparsers.add_parser("status")
    args = parser.parse_args()
    if args.command == "inventory":
        print(json.dumps(inventory(args.padding_days, args.limit, args.max_pages, args.reset), indent=2))
    elif args.command == "prices":
        print(json.dumps(prices(args.workers, args.batch_size), indent=2))
    else:
        print(json.dumps({"inventory": json.loads(MARKET_CHECKPOINT.read_text()) if MARKET_CHECKPOINT.exists() else None, "prices": json.loads(PRICE_CHECKPOINT.read_text()) if PRICE_CHECKPOINT.exists() else None}, indent=2))


if __name__ == "__main__":
    main()
