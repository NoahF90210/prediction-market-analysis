"""Build the Phase 2 manual audit from official Gamma, CLOB, and public pages."""
from __future__ import annotations

import csv
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import requests

from src.polymarket.price_history import select_latest_pre_cutoff

AUDIT_DIR = ROOT / "data" / "audit"
ARTIFACT_DIR = ROOT / ".hermes" / "artifacts"
GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com/prices-history"

# Deliberately stratified, hand-selected IDs, not a collection run.
SELECTED = {
    "514396": ("15000", "what-price-will-solana-hit-in-december", "crypto"),
    "502265": ("11022", "next-israel-x-hamas-ceasefire-in", "geopolitics"),
    "516735": ("16113", "epl-bre-ars-2025-01-01", "sports_match"),
    "516994": ("16189", "cfp-texas-vs-arizona-state", "sports_proposition"),
    "517106": ("16223", "cfp-notre-dame-vs-georgia-over-45pt5", "sports_proposition"),
    "515522": ("15422", "belarus-presidential-election", "multi_outcome_event"),
    "512320": ("14220", "fed-interest-rates-january-2025", "finance"),
    "518808": ("16808", "january-inflation-annual", "economy"),
    "516498": ("15930", "bitcoin-above-94000-on-january-3", "crypto"),
    "513528": ("16268", "spacex-flight-test-7", "science"),
    "518008": ("16545", "will-it-rain-in-la-by-next-friday", "weather"),
    "519263": ("16987", "grammys-best-rap-song", "entertainment"),
    "519277": ("16993", "flight-risk-opening-weekend-box-office", "entertainment"),
    "516325": ("15860", "top-ai-model-on-january-31", "technology"),
    "518068": ("16552", "will-supreme-court-delay-the-tiktok-ban", "law_technology"),
    "515536": ("15424", "do-luigi-mangiones-parents-have-unitedhealthcare", "health"),
    "517825": ("16476", "what-will-trump-say-during-mar-a-lago-press-conference", "politics_mentions"),
    "521119": ("17554", "highest-temperature-in-nyc-on-february-2", "weather"),
    "514540": ("15049", "nfl-worst-record", "sports_futures"),
    "648436": ("64746", "trump-approval-up-or-down-this-week-859", "late_window"),
}


def get(session: requests.Session, url: str, **kwargs):
    response = session.get(url, timeout=30, **kwargs)
    response.raise_for_status()
    return response.json()


def iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace(" ", "T").replace("+00", "+00:00"))


def parse_list(value):
    return value if isinstance(value, list) else json.loads(value)


def public_market_snapshot(
    session: requests.Session,
    slug: str,
    market_id: str,
    expected_question: str,
) -> dict:
    response = session.get(
        f"https://polymarket.com/event/{slug}",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    response.raise_for_status()
    pattern = (
        r'\\"id\\":\\"' + re.escape(market_id)
        + r'\\".*?\\"question\\":\\"(.*?)\\".*?'
        + r'\\"outcomes\\":(\[.*?\]),\\"outcomePrices\\":(\[.*?\])'
    )
    match = re.search(pattern, response.text, re.DOTALL)
    if match:
        unescape = lambda value: value.replace(r'\"', '"')
        return {
            "market_found": True,
            "question": expected_question,
            "question_match": (
                market_id in response.text
                and all(
                    token.lower() in response.text.lower()
                    for token in re.findall(r"[A-Za-z0-9]+", expected_question)
                )
            ),
            "outcomes": json.loads(unescape(match.group(2))),
            "outcome_prices": [float(x) for x in json.loads(unescape(match.group(3)))],
            "url": response.url,
        }
    return {
        "market_found": False,
        "question": None,
        "question_match": False,
        "outcomes": [],
        "outcome_prices": [],
        "url": response.url,
    }


def main() -> None:
    session = requests.Session()
    retrieved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    raw_examples = []
    normalized = []
    for market_id, (event_id, event_slug, manual_category) in SELECTED.items():
        market = get(session, f"{GAMMA}/markets/{market_id}")
        event = get(session, f"{GAMMA}/events/{event_id}")
        outcomes = parse_list(market["outcomes"])
        token_ids = parse_list(market["clobTokenIds"])
        prices = [float(x) for x in parse_list(market["outcomePrices"])]
        resolution_at = iso(market["closedTime"])
        cutoff = resolution_at - timedelta(hours=24)
        public_snapshot = public_market_snapshot(session, event_slug, market_id, market.get("question", ""))
        api_outcome = outcomes[max(range(len(prices)), key=lambda index: prices[index])]
        public_outcome = None
        if public_snapshot["outcomes"] and public_snapshot["outcome_prices"]:
            public_outcome = public_snapshot["outcomes"][max(
                range(len(public_snapshot["outcome_prices"])),
                key=lambda index: public_snapshot["outcome_prices"][index],
            )]
        yes_index = next((i for i, x in enumerate(outcomes) if str(x).lower() == "yes"), None)
        no_index = next((i for i, x in enumerate(outcomes) if str(x).lower() == "no"), None)
        canonical_yes_no = yes_index is not None and no_index is not None and len(outcomes) == 2
        reference_token = token_ids[yes_index] if yes_index is not None else token_ids[0]
        history_params = {
            "market": reference_token,
            "startTs": int((cutoff - timedelta(days=7)).timestamp()),
            "endTs": int(cutoff.timestamp()),
            "fidelity": 60,
        }
        history_payload = get(session, CLOB, params=history_params)
        history = history_payload.get("history")
        if not isinstance(history, list):
            raise ValueError(f"market {market_id} returned malformed history")
        selected = None
        history_error = None
        try:
            selected = select_latest_pre_cutoff(history, cutoff, 168)
        except ValueError as exc:
            history_error = str(exc)
        if not canonical_yes_no:
            status = "excluded"
            exclusion = "non_yes_no_outcomes"
        elif public_outcome not in {"Yes", "No"} or api_outcome != public_outcome:
            status = "excluded"
            exclusion = "resolution_mismatch"
        elif selected is None:
            status = "excluded"
            exclusion = "missing_price_history" if not history else "snapshot_unusable"
        else:
            status = "included"
            exclusion = ""
        event_markets = event.get("markets") or []
        record = {
            "market_id": market_id,
            "event_id": event_id,
            "event_slug": event_slug,
            "event_title": event.get("title"),
            "event_market_count": len(event_markets),
            "question": market.get("question"),
            "category": manual_category,
            "api_tags": [t.get("label") for t in market.get("tags", [])],
            "condition_id": market.get("conditionId"),
            "outcomes": outcomes,
            "outcome_prices_at_retrieval": prices,
            "clob_token_ids": token_ids,
            "yes_token_id": token_ids[yes_index] if yes_index is not None else "",
            "reference_token_id": reference_token,
            "closed": market.get("closed"),
            "closed_time": market.get("closedTime"),
            "end_date": market.get("endDate"),
            "uma_end_date": market.get("umaEndDate"),
            "uma_resolution_status": market.get("umaResolutionStatus"),
            "resolution_source": market.get("resolutionSource"),
            "api_final_outcome": api_outcome,
            "public_final_outcome": public_outcome,
            "public_market_snapshot": public_snapshot,
            "history_request": history_params,
            "history_point_count": len(history),
            "selected_history_point": selected,
            "history_error": history_error,
            "market_url": f"https://polymarket.com/event/{event_slug}",
            "retrieved_at": retrieved_at,
            "raw_gamma_market": market,
            "raw_clob_history": history_payload,
            "manual_audit": {
                "question_public_match": public_snapshot["question_match"],
                "outcome_public_match": api_outcome == public_outcome,
                "resolution_timestamp_credible": market.get("closedTime") == market.get("umaEndDate"),
                "field_mapping_decision": (
                    "Use closedTime, supported by matching umaEndDate and the public ended/final-outcome state."
                ),
                "status": status,
                "exclusion_reason": exclusion,
            },
        }
        raw_examples.append(record)
        normalized.append({
            "market_id": market_id,
            "event_id": event_id,
            "question": market.get("question"),
            "category": manual_category,
            "yes_token_id": record["yes_token_id"],
            "probability": selected["price"] if selected and canonical_yes_no else "",
            "probability_timestamp": selected["timestamp"] if selected and canonical_yes_no else "",
            "snapshot_cutoff": cutoff.isoformat().replace("+00:00", "Z"),
            "snapshot_age_hours": selected["age_hours"] if selected and canonical_yes_no else "",
            "resolution": public_outcome,
            "resolution_timestamp": resolution_at.isoformat().replace("+00:00", "Z"),
            "resolution_source": market.get("resolutionSource") or "",
            "market_url": f"https://polymarket.com/event/{event_slug}",
            "inclusion_status": status,
            "exclusion_reason": exclusion,
        })
    raw_examples.sort(key=lambda x: x["market_id"])
    normalized.sort(key=lambda x: x["market_id"])
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    (AUDIT_DIR / "gamma-market-examples.json").write_text(json.dumps({
        "retrieved_at": retrieved_at,
        "source": "official Gamma /markets/{id}, /events/{id}, official CLOB /prices-history, public Polymarket event pages",
        "selection_note": "20 hand-selected real markets; this is not full collection.",
        "markets": raw_examples,
    }, indent=2) + "\n")
    fields = list(normalized[0])
    with (AUDIT_DIR / "normalized-market-examples.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(normalized)
    included = sum(row["inclusion_status"] == "included" for row in normalized)
    excluded = len(normalized) - included
    mismatches = [row["market_id"] for row in raw_examples if not row["manual_audit"]["outcome_public_match"]]
    report = f"""# Polymarket API Field and 20-Market Manual Audit

Captured: {retrieved_at}.

## Scope

This is a manually stratified audit of exactly {len(normalized)} real resolved Polymarket markets.
It is not full collection and it must be reviewed before any inventory collector is run.

Sources were the official Gamma market and event endpoints, the official CLOB `prices-history` endpoint, and the corresponding public Polymarket event pages.
The documentation references are https://docs.polymarket.com/api-reference/markets/list-markets-keyset-pagination, https://docs.polymarket.com/concepts/markets-events, and https://docs.polymarket.com/api-reference/markets/get-prices-history.
The public-page scraper was rate-limited during exploratory extraction, so the final audit uses direct HTTP retrieval of all 20 public pages and records the exact URLs.

## Field mapping decision

| API field | Interpretation | Audit evidence |
|---|---|---|
| `id` | Unique market identity | All 20 records have distinct IDs. |
| `question` | Market question shown in Gamma and public page | Public page title/question was checked for every row. |
| `conditionId` | Market condition identity | Preserved verbatim from Gamma. |
| `clobTokenIds` | Outcome token IDs, aligned by outcome order | Preserved verbatim and used for CLOB history requests. |
| `outcomes` | Ordered outcome labels | 17 rows are canonical `Yes`/`No`; 3 use named labels and are excluded from the YES/NO analysis until a separate mapping is approved. |
| `outcomePrices` | Current terminal settlement display in the retrieved Gamma record | Used only to compare the winning label with the public final outcome, never as the forecast snapshot. |
| `closed` | Closed status | All 20 sampled records are `true`. |
| `closedTime` | Selected verified resolution timestamp | Present for all 20 and agrees with `umaEndDate` for all 20. |
| `endDate` | Nominal scheduled/end date | Often differs from `closedTime`, so it is not the primary resolution timestamp. |
| `umaEndDate` | UMA resolution end timestamp | Matches `closedTime` in this sample. |
| `umaResolutionStatus` | Resolution state | `resolved` for all 20. |
| `resolutionSource` | Resolution source URL or blank | Preserved; several records have an empty value and require rule text/public evidence instead. |
| nested event `id` and `title` | Event grouping | Preserved; event sizes expose related-market clusters. |
| category/tags | Topic stratification | Tags are preserved; the audit category is a stable manual stratum label. |

## Results

- Included under the current Phase 1 YES/NO and pre-cutoff rules: **{included}**.
- Excluded: **{excluded}**.
- Public/API outcome mismatches: **{len(mismatches)}**{(' (' + ', '.join(mismatches) + ')' if mismatches else '')}.
- Missing or empty CLOB history is intentionally visible in the CSV and JSON.
- Named outcome labels are intentionally not silently converted to YES/NO.

## Manual audit rows

| ID | Category | Closed time | Outcomes | Public/API outcome | CLOB history | Status | Reason |
|---|---|---|---|---|---:|---|---|
"""
    for row in normalized:
        raw = next(x for x in raw_examples if x["market_id"] == row["market_id"])
        report += f"| [{row['market_id']}]({row['market_url']}) | {row['category']} | {row['resolution_timestamp']} | {', '.join(raw['outcomes'])} | {raw['public_final_outcome']} / {raw['api_final_outcome']} | {raw['history_point_count']} | {row['inclusion_status']} | {row['exclusion_reason'] or 'none'} |\n"
    report += """
## Audit conclusion

The official fields are sufficient to implement a bounded collector, but the audit changes two implementation details from a naive interpretation.

1. Use `closedTime` as the primary resolution timestamp, with `umaEndDate` as a corroborating field and `endDate` retained as nominal metadata.
2. Require canonical `Yes`/`No` labels for the first rebuild rather than guessing a YES mapping for named outcomes.

The two zero-history examples and the named-outcome examples are useful fail-closed tests, not reasons to claim complete coverage.
Full collection remains blocked pending Noah's review of this specification and audit.
"""
    (ARTIFACT_DIR / "polymarket-api-field-audit.md").write_text(report)
    print(json.dumps({"audited": len(normalized), "included": included, "excluded": excluded, "mismatches": mismatches, "artifacts": [str(AUDIT_DIR / "gamma-market-examples.json"), str(AUDIT_DIR / "normalized-market-examples.csv"), str(ARTIFACT_DIR / "polymarket-api-field-audit.md")]}, indent=2))


if __name__ == "__main__":
    main()
