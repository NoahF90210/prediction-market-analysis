from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker

from src.rebuild.collectors import CollectedCandidate
from src.rebuild.evaluation import evaluation_summary
from src.rebuild.gates import candidate_records_sha256, normalize_candidates, read_candidates
from src.rebuild.protocol import Protocol, canonical_json_bytes, load_protocol
from src.rebuild.provenance import verify_manifest

ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_SCHEMA = ROOT / "schemas" / "analysis-contract.schema.json"
PROTOCOL_SCHEMA = ROOT / "schemas" / "research-protocol.schema.json"
MANIFEST_SCHEMA = ROOT / "schemas" / "raw-manifest.schema.json"
EVALUATION_SCHEMA = ROOT / "schemas" / "evaluation-summary.schema.json"


class BuildValidationError(RuntimeError):
    """Raised when a build cannot pass its declared contracts."""


def validate_schema(instance: Any, schema_path: Path) -> list[str]:
    schema = json.loads(schema_path.read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.absolute_path))
    ]


def evaluation_consistency_errors(summary: dict[str, Any], protocol: Protocol) -> list[str]:
    errors: list[str] = []
    platforms = summary.get("platforms") or []
    platform_names = [item.get("platform") for item in platforms if isinstance(item, dict)]
    if sorted(platform_names) != sorted(protocol.payload["platforms"]):
        errors.append("evaluation_platform_set_mismatch")
    if sum(int(item.get("contract_count", 0)) for item in platforms) != int(summary.get("contract_count", 0)):
        errors.append("evaluation_contract_count_mismatch")
    if sum(int(item.get("event_count", 0)) for item in platforms) != int(summary.get("event_count", 0)):
        errors.append("evaluation_event_count_mismatch")

    expected_sensitivities = {
        (int(threshold), policy)
        for threshold in protocol.payload["snapshot_staleness_sensitivity_seconds"]
        for policy in (
            protocol.payload["contract_selection"]["primary_policy"],
            protocol.payload["contract_selection"]["sensitivity_policy"],
        )
    }
    actual_sensitivities = {
        (int(item.get("max_snapshot_staleness_seconds", -1)), item.get("contract_selection_policy"))
        for item in summary.get("sensitivities") or []
        if isinstance(item, dict)
    }
    if actual_sensitivities != expected_sensitivities:
        errors.append("evaluation_sensitivity_matrix_mismatch")
    return errors


def build_analysis_rows(
    candidates: Iterable[CollectedCandidate],
    *,
    manifest: dict[str, Any],
    raw_root: Path,
    protocol: Protocol,
) -> list[dict[str, Any]]:
    materialized_candidates = list(candidates)
    candidate_hash = candidate_records_sha256(materialized_candidates)
    errors = verify_manifest(
        manifest,
        raw_root,
        protocol,
        candidate_records_sha256=candidate_hash,
    )
    manifest_records = {
        json.dumps(record, sort_keys=True, separators=(",", ":"))
        for record in manifest.get("records", [])
    }
    for index, candidate in enumerate(materialized_candidates):
        for label, provenance in (
            ("market", candidate.market_provenance),
            ("history", candidate.history_provenance),
        ):
            if provenance is None:
                continue
            serialized = json.dumps(asdict(provenance), sort_keys=True, separators=(",", ":"))
            if serialized not in manifest_records:
                errors.append(f"candidate_provenance_not_in_manifest:{index}:{label}")
    errors.extend(validate_schema(protocol.payload, PROTOCOL_SCHEMA))
    errors.extend(validate_schema(manifest, MANIFEST_SCHEMA))
    if errors:
        raise BuildValidationError("Manifest/protocol validation failed:\n- " + "\n- ".join(errors))

    rows = normalize_candidates(
        materialized_candidates,
        protocol=protocol,
        raw_root=raw_root,
        build_id=str(manifest["build_id"]),
    )
    schema_errors: list[str] = []
    for index, row in enumerate(rows):
        schema_errors.extend(f"row[{index}].{error}" for error in validate_schema(row, ANALYSIS_SCHEMA))
    if schema_errors:
        raise BuildValidationError("Analysis schema validation failed:\n- " + "\n- ".join(schema_errors))
    return sorted(rows, key=lambda row: (row["platform"], row["event_group_id"], row["market_id"]))


def _csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return value


def write_analysis_artifacts(rows: list[dict[str, Any]], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "analysis_contracts.json"
    json_path.write_bytes(canonical_json_bytes(rows) + b"\n")

    csv_path = output_dir / "analysis_contracts.csv"
    fieldnames = list(rows[0].keys()) if rows else []
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        if fieldnames:
            writer.writeheader()
            for row in rows:
                writer.writerow({key: _csv_value(value) for key, value in row.items()})

    included_path = output_dir / "analysis_included.json"
    included = [row for row in rows if row["inclusion_status"] == "included"]
    included_path.write_bytes(canonical_json_bytes(included) + b"\n")
    return {"json": json_path, "csv": csv_path, "included": included_path}


def build_fixture_analysis(
    fixture_root: Path = ROOT / "data" / "fixtures" / "provenance_complete",
    output_dir: Path = ROOT / "data" / "derived" / "rebuild",
    protocol: Protocol | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Path]]:
    protocol = protocol or load_protocol()
    manifest = json.loads((fixture_root / "manifest.json").read_text())
    candidates = read_candidates(fixture_root / "candidate_records.json")
    rows = build_analysis_rows(
        candidates,
        manifest=manifest,
        raw_root=fixture_root / "raw",
        protocol=protocol,
    )
    paths = write_analysis_artifacts(rows, output_dir)
    summary = evaluation_summary(
        rows,
        protocol=protocol,
        corpus_kind="fixture",
    )
    summary_errors = validate_schema(summary, EVALUATION_SCHEMA)
    summary_errors.extend(evaluation_consistency_errors(summary, protocol))
    if summary_errors:
        raise BuildValidationError("Evaluation schema validation failed:\n- " + "\n- ".join(summary_errors))
    evaluation_path = output_dir / "evaluation_summary.json"
    evaluation_path.write_bytes(canonical_json_bytes(summary) + b"\n")
    paths["evaluation"] = evaluation_path
    return rows, paths


def build_real_analysis(
    source_root: Path,
    output_dir: Path = ROOT / "data" / "derived" / "rebuild-real",
    protocol: Protocol | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Path]]:
    protocol = protocol or load_protocol()
    manifest = json.loads((source_root / "manifest.json").read_text())
    candidates = read_candidates(source_root / "candidate_records.json")
    rows = build_analysis_rows(
        candidates,
        manifest=manifest,
        raw_root=source_root / "raw",
        protocol=protocol,
    )
    paths = write_analysis_artifacts(rows, output_dir)
    summary = evaluation_summary(
        rows,
        protocol=protocol,
        corpus_kind="real",
    )
    summary_errors = validate_schema(summary, EVALUATION_SCHEMA)
    summary_errors.extend(evaluation_consistency_errors(summary, protocol))
    if summary_errors:
        raise BuildValidationError("Real evaluation schema validation failed:\n- " + "\n- ".join(summary_errors))
    evaluation_path = output_dir / "evaluation_summary.json"
    evaluation_path.write_bytes(canonical_json_bytes(summary) + b"\n")
    paths["evaluation"] = evaluation_path
    return rows, paths
