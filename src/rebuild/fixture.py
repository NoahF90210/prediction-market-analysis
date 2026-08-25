from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from src.rebuild.collectors import CollectedCandidate
from src.rebuild.gates import write_candidates
from src.rebuild.protocol import Protocol, load_protocol
from src.rebuild.provenance import RawResponseStore

FIXTURE_RETRIEVED_AT = dt.datetime(2026, 8, 14, 16, 0, tzinfo=dt.timezone.utc)
FIXTURE_COMMIT = "fixture-collector-v1"


def _candidate(
    store: RawResponseStore,
    protocol: Protocol,
    *,
    platform: str,
    market_id: str,
    event_id: str,
    title: str,
    category: str,
    boundary: str,
    resolved_at: str,
    resolution: str,
    probability: float,
    observed_at: str,
    relationship: str = "standalone",
    explicit_multileg: bool = False,
    explicit_conditional: bool = False,
    explicit_complement: bool = False,
) -> CollectedCandidate:
    source = "polymarket_clob_price_history"
    market_endpoint = "https://gamma-api.polymarket.com/events"
    history_endpoint = "https://clob.polymarket.com/prices-history"
    market_payload = {
        "platform": platform,
        "market_id": market_id,
        "event_id": event_id,
        "title": title,
        "category": category,
        "close_time": boundary,
        "resolved_at": resolved_at,
        "resolution": resolution,
        "final_volume": "1000.00",
    }
    history_point: dict[str, Any] = {"t": observed_at, "p": probability}
    history_payload: Any = {"history": [history_point]}
    time_keys = ["t"]
    price_keys = ["p"]

    market_provenance = store.write_response(
        platform=platform,
        record_type="market_inventory",
        endpoint=market_endpoint,
        request_params={"fixture_market_id": market_id},
        payload=market_payload,
        retrieved_at=FIXTURE_RETRIEVED_AT,
    )
    history_provenance = store.write_response(
        platform=platform,
        record_type="price_history",
        endpoint=history_endpoint,
        request_params={"fixture_market_id": market_id, "at_or_before": boundary},
        payload=history_payload,
        retrieved_at=FIXTURE_RETRIEVED_AT,
    )
    record = {
        "platform": platform,
        "market_id": market_id,
        "event_id": event_id,
        "event_group_id": event_id,
        "series_id": f"series-{category}",
        "title": title,
        "rules": f"Fixture rules for {title}",
        "market_url": f"https://example.invalid/{platform}/{market_id}",
        "raw_market_type": "binary",
        "raw_category": category,
        "raw_tags": [{"slug": category, "label": category.title()}],
        "opened_at": "2025-12-01T00:00:00Z",
        "scheduled_close_at": boundary,
        "trading_closed_at": boundary,
        "event_started_at": boundary,
        "resolved_at": resolved_at,
        "resolution": resolution,
        "resolution_source": "fixture_resolution_record",
        "history": [history_point],
        "history_time_keys": time_keys,
        "history_price_keys": price_keys,
        "price_source": source,
        "raw_yes_orientation": "YES",
        "cutoff_volume": 500.0,
        "cutoff_volume_source": "fixture_cutoff_ledger",
        "final_volume": 1000.0,
        "final_volume_source": "fixture_final_market_record",
        "volume_unit": "USD",
        "explicit_multileg": explicit_multileg,
        "explicit_conditional": explicit_conditional,
        "explicit_complement": explicit_complement,
        "native_group_relationship": relationship,
    }
    return CollectedCandidate(record, market_provenance, history_provenance)


def build_fixture_source(root: Path, protocol: Protocol | None = None) -> dict[str, Any]:
    protocol = protocol or load_protocol()
    raw_root = root / "raw"
    store = RawResponseStore(
        raw_root,
        protocol,
        commit=FIXTURE_COMMIT,
        clock=lambda: FIXTURE_RETRIEVED_AT,
    )
    candidates = [
        _candidate(
            store,
            protocol,
            platform="polymarket",
            market_id="pm-election-a",
            event_id="pm-election-event",
            title="Will Candidate A win the fixture election?",
            category="elections",
            boundary="2026-02-10T20:00:00Z",
            resolved_at="2026-02-10T22:00:00Z",
            resolution="YES",
            probability=0.72,
            observed_at="2026-02-09T19:00:00Z",
            relationship="mutually_exclusive",
        ),
        _candidate(
            store,
            protocol,
            platform="polymarket",
            market_id="pm-election-b",
            event_id="pm-election-event",
            title="Will Candidate B win the fixture election?",
            category="elections",
            boundary="2026-02-10T20:00:00Z",
            resolved_at="2026-02-10T22:00:00Z",
            resolution="NO",
            probability=0.28,
            observed_at="2026-02-09T19:00:00Z",
            relationship="mutually_exclusive",
        ),
        _candidate(
            store,
            protocol,
            platform="polymarket",
            market_id="pm-sports-1",
            event_id="pm-sports-event",
            title="Will the home team win the fixture match?",
            category="sports",
            boundary="2026-03-15T18:00:00Z",
            resolved_at="2026-03-15T21:00:00Z",
            resolution="NO",
            probability=0.40,
            observed_at="2026-03-14T17:30:00Z",
        ),
        _candidate(
            store,
            protocol,
            platform="polymarket",
            market_id="KXFIXTUREGDP-26JUN",
            event_id="KXFIXTUREGDP-26JUN",
            title="Will fixture GDP growth exceed two percent?",
            category="economics",
            boundary="2026-04-30T12:00:00Z",
            resolved_at="2026-04-30T13:00:00Z",
            resolution="YES",
            probability=0.65,
            observed_at="2026-04-29T10:00:00Z",
        ),
        _candidate(
            store,
            protocol,
            platform="polymarket",
            market_id="KXFIXTURETENNIS-A",
            event_id="KXFIXTURETENNIS",
            title="Will Player A win the fixture tennis match?",
            category="sports",
            boundary="2026-05-20T16:00:00Z",
            resolved_at="2026-05-20T19:00:00Z",
            resolution="YES",
            probability=0.58,
            observed_at="2026-05-19T15:00:00Z",
            relationship="mutually_exclusive",
        ),
        _candidate(
            store,
            protocol,
            platform="polymarket",
            market_id="KXFIXTURETENNIS-B",
            event_id="KXFIXTURETENNIS",
            title="Will Player B win the fixture tennis match?",
            category="sports",
            boundary="2026-05-20T16:00:00Z",
            resolved_at="2026-05-20T19:00:00Z",
            resolution="NO",
            probability=0.42,
            observed_at="2026-05-19T15:00:00Z",
            relationship="mutually_exclusive",
        ),
        _candidate(
            store,
            protocol,
            platform="polymarket",
            market_id="KXMVEFIXTURE-PARLAY",
            event_id="KXMVEFIXTURE",
            title="Fixture parlay: Team A and Team B both win",
            category="sports",
            boundary="2026-06-01T20:00:00Z",
            resolved_at="2026-06-01T22:00:00Z",
            resolution="NO",
            probability=0.30,
            observed_at="2026-05-31T19:00:00Z",
            explicit_multileg=True,
        ),
        _candidate(
            store,
            protocol,
            platform="polymarket",
            market_id="pm-stale-snapshot",
            event_id="pm-stale-event",
            title="Will the fixture science result be positive?",
            category="science_tech",
            boundary="2026-06-10T20:00:00Z",
            resolved_at="2026-06-10T21:00:00Z",
            resolution="YES",
            probability=0.55,
            observed_at="2026-06-09T08:00:00Z",
        ),
        _candidate(
            store,
            protocol,
            platform="polymarket",
            market_id="pm-conditional",
            event_id="pm-conditional-event",
            title="If the fixture bill passes, then will turnout exceed 60 percent?",
            category="politics",
            boundary="2026-06-20T20:00:00Z",
            resolved_at="2026-06-20T22:00:00Z",
            resolution="NO",
            probability=0.45,
            observed_at="2026-06-19T19:00:00Z",
            explicit_conditional=True,
        ),
    ]
    candidate_hash = write_candidates(root / "candidate_records.json", candidates)
    manifest = store.write_manifest(
        root / "manifest.json",
        candidate_records_sha256=candidate_hash,
        created_at=FIXTURE_RETRIEVED_AT,
    )
    return manifest
