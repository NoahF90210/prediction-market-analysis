from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path

import pytest

from src.rebuild.fixture import FIXTURE_COMMIT, FIXTURE_RETRIEVED_AT, build_fixture_source
from src.rebuild.gates import (
    candidate_from_json,
    candidate_records_sha256,
    candidate_to_json,
    is_conditional,
    normalize_candidates,
    read_candidates,
)
from src.rebuild.pipeline import (
    ANALYSIS_SCHEMA,
    MANIFEST_SCHEMA,
    PROTOCOL_SCHEMA,
    BuildValidationError,
    build_analysis_rows,
    build_fixture_analysis,
    validate_schema,
)
from src.rebuild.protocol import ROOT, load_protocol, parse_utc
from src.rebuild.provenance import RawResponseStore, collector_commit, verify_manifest
from src.rebuild.validation import scan_text_for_secrets

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "provenance_complete"


def test_collector_fingerprint_includes_executed_source_hash() -> None:
    fingerprint = collector_commit(ROOT)
    assert "+collector." in fingerprint
    assert len(fingerprint.rsplit("+collector.", 1)[1]) == 16


def test_epoch_timestamps_parse_as_utc() -> None:
    assert parse_utc(1_700_000_000) == dt.datetime.fromtimestamp(1_700_000_000, tz=dt.timezone.utc)
    expected = dt.datetime.fromtimestamp(1_700_000_000, tz=dt.timezone.utc)
    assert parse_utc("1700000000") == expected
    assert parse_utc(1_700_000_000_000) == expected
    assert parse_utc("1700000000.0") == expected


def test_conditional_title_detection_is_conservative() -> None:
    assert is_conditional({"title": "Will turnout exceed 60% if the bill passes?"}) is True
    assert is_conditional({"title": "Will turnout exceed 60%?"}) is False
    assert is_conditional({
        "title": "Will the court approve the merger?",
        "rules": "This market is active only if shareholders approve.",
    }) is True


def test_protocol_is_frozen_six_month_window_and_schema_valid() -> None:
    protocol = load_protocol()
    assert protocol.start == dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    assert protocol.end == dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    assert protocol.forecast_horizon == dt.timedelta(hours=24)
    assert validate_schema(protocol.payload, PROTOCOL_SCHEMA) == []


def test_fixture_manifest_and_analysis_contracts_validate() -> None:
    protocol = load_protocol()
    manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text())
    assert validate_schema(manifest, MANIFEST_SCHEMA) == []
    candidates = read_candidates(FIXTURE_ROOT / "candidate_records.json")
    assert verify_manifest(
        manifest,
        FIXTURE_ROOT / "raw",
        protocol,
        candidate_records_sha256=candidate_records_sha256(candidates),
    ) == []

    rows = build_analysis_rows(
        candidates,
        manifest=manifest,
        raw_root=FIXTURE_ROOT / "raw",
        protocol=protocol,
    )
    assert all(validate_schema(row, ANALYSIS_SCHEMA) == [] for row in rows)


def test_fixture_build_is_byte_deterministic(tmp_path: Path) -> None:
    first_source = tmp_path / "first-source"
    second_source = tmp_path / "second-source"
    first_manifest = build_fixture_source(first_source)
    second_manifest = build_fixture_source(second_source)
    assert first_manifest["build_id"] == second_manifest["build_id"]
    assert (first_source / "manifest.json").read_bytes() == (second_source / "manifest.json").read_bytes()
    assert (first_source / "candidate_records.json").read_bytes() == (second_source / "candidate_records.json").read_bytes()

    _, first_paths = build_fixture_analysis(first_source, tmp_path / "first-output")
    _, second_paths = build_fixture_analysis(second_source, tmp_path / "second-output")
    assert first_paths["json"].read_bytes() == second_paths["json"].read_bytes()
    assert first_paths["csv"].read_bytes() == second_paths["csv"].read_bytes()
    assert first_paths["included"].read_bytes() == second_paths["included"].read_bytes()


def test_event_total_weight_and_fail_closed_exclusions() -> None:
    rows, _ = build_fixture_analysis()
    included = [row for row in rows if row["inclusion_status"] == "included"]
    event_weights: dict[tuple[str, str], float] = {}
    for row in included:
        key = (row["platform"], row["event_group_id"])
        event_weights[key] = event_weights.get(key, 0.0) + row["event_weight"]
    assert event_weights
    assert all(weight == pytest.approx(1.0) for weight in event_weights.values())

    excluded = {row["market_id"]: row["exclusion_reasons"] for row in rows if row["inclusion_status"] == "excluded"}
    assert excluded["KXMVEFIXTURE-PARLAY"] == ["excluded_multileg_parlay"]
    assert excluded["pm-conditional"] == ["excluded_conditional_contract"]
    assert excluded["pm-stale-snapshot"] == ["snapshot_too_stale"]


def test_missing_history_provenance_never_scores() -> None:
    protocol = load_protocol()
    manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text())
    candidate = read_candidates(FIXTURE_ROOT / "candidate_records.json")[0]
    payload = candidate_to_json(candidate)
    payload["history_provenance"] = None
    unsafe = candidate_from_json(payload)
    rows = normalize_candidates(
        [unsafe],
        protocol=protocol,
        raw_root=FIXTURE_ROOT / "raw",
        build_id=manifest["build_id"],
    )
    assert rows[0]["inclusion_status"] == "excluded"
    assert "missing_raw_history_provenance" in rows[0]["exclusion_reasons"]


def test_secret_scanner_catches_common_assignments_and_tokens() -> None:
    long_value = "a" * 32
    examples = [
        f'API_KEY="{long_value}"',
        f'PASSWORD="{long_value}"',
        f'GITHUB_TOKEN="{long_value}"',
        f'api_key="{long_value}"',
        f'db_password="{long_value}"',
        "OPENAI_API_KEY" + "=" + f'"sk-{long_value}"',
    ]
    for example in examples:
        assert scan_text_for_secrets(example, "probe")
    assert scan_text_for_secrets('API_KEY="example-placeholder"', "probe") == []


def test_candidate_record_tampering_invalidates_build_id(tmp_path: Path) -> None:
    source = tmp_path / "fixture"
    manifest = build_fixture_source(source)
    candidates = read_candidates(source / "candidate_records.json")
    payload = candidate_to_json(candidates[0])
    payload["record"]["resolution"] = "NO"
    candidates[0] = candidate_from_json(payload)
    with pytest.raises(BuildValidationError, match="candidate_records_hash_mismatch"):
        build_analysis_rows(
            candidates,
            manifest=manifest,
            raw_root=source / "raw",
            protocol=load_protocol(),
        )


def test_manifest_path_traversal_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "fixture"
    manifest = build_fixture_source(source)
    candidates = read_candidates(source / "candidate_records.json")
    tampered = copy.deepcopy(manifest)
    record = tampered["records"][0]
    original = source / "raw" / record["raw_response_path"]
    outside = source / "outside.json"
    outside.write_bytes(original.read_bytes())
    record["raw_response_path"] = "../outside.json"
    errors = verify_manifest(
        tampered,
        source / "raw",
        load_protocol(),
        candidate_records_sha256=candidate_records_sha256(candidates),
    )
    assert "raw_path_outside_root:../outside.json" in errors


def test_manifest_tampering_is_detected(tmp_path: Path) -> None:
    source = tmp_path / "fixture"
    manifest = build_fixture_source(source)
    record = manifest["records"][0]
    raw_path = source / "raw" / record["raw_response_path"]
    raw_path.write_text("{}")
    candidates = read_candidates(source / "candidate_records.json")
    errors = verify_manifest(
        manifest,
        source / "raw",
        load_protocol(),
        candidate_records_sha256=candidate_records_sha256(candidates),
    )
    assert any(error.startswith("raw_hash_mismatch") for error in errors)


def test_terminal_probabilities_are_not_filtered_by_value(tmp_path: Path) -> None:
    source = tmp_path / "fixture"
    manifest = build_fixture_source(source)
    candidates = read_candidates(source / "candidate_records.json")
    payload = candidate_to_json(candidates[0])
    payload["record"]["history"][0]["p"] = 1.0
    raw_history = source / "raw" / payload["history_provenance"]["raw_response_path"]
    history_body = json.loads(raw_history.read_text())
    history_body["history"][0]["p"] = 1.0

    # Re-address the changed history through the immutable store instead of mutating provenance.
    store = RawResponseStore(
        source / "raw",
        load_protocol(),
        commit=FIXTURE_COMMIT,
        clock=lambda: FIXTURE_RETRIEVED_AT,
    )
    new_provenance = store.write_response(
        platform="polymarket",
        record_type="price_history",
        endpoint=payload["history_provenance"]["endpoint"],
        request_params=payload["history_provenance"]["request_params"],
        payload=history_body,
    )
    payload["history_provenance"] = {
        "platform": new_provenance.platform,
        "record_type": new_provenance.record_type,
        "endpoint": new_provenance.endpoint,
        "request_params": new_provenance.request_params,
        "retrieved_at": new_provenance.retrieved_at,
        "raw_response_path": new_provenance.raw_response_path,
        "sha256": new_provenance.sha256,
        "content_bytes": new_provenance.content_bytes,
        "schema_version": new_provenance.schema_version,
        "collector_commit": new_provenance.collector_commit,
    }
    row = normalize_candidates(
        [candidate_from_json(payload)],
        protocol=load_protocol(),
        raw_root=source / "raw",
        build_id=manifest["build_id"],
    )[0]
    assert row["yes_probability"] == 1.0
    assert row["inclusion_status"] == "included"
