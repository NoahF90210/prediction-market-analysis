from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from src.rebuild.protocol import Protocol, canonical_json_bytes, utc_iso

_SECRET_KEY_PATTERN = re.compile(
    r"(^|[_-])(authorization|auth|api[_-]?key|private[_-]?key|secret|signature|token|password)([_-]|$)",
    re.IGNORECASE,
)


class ProvenanceError(RuntimeError):
    """Raised when immutable evidence cannot be written or verified."""


@dataclass(frozen=True)
class RawRecord:
    platform: str
    record_type: str
    endpoint: str
    request_params: dict[str, Any]
    retrieved_at: str
    raw_response_path: str
    sha256: str
    content_bytes: int
    schema_version: str
    collector_commit: str


def collector_commit(root: Path) -> str:
    """Fingerprint the committed revision plus the collector code actually executed."""
    try:
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        head = "unknown-collector-commit"

    source_paths = sorted((root / "src" / "rebuild").glob("*.py"))
    source_paths.extend(
        path
        for path in [
            root / "src" / "rebuild" / "normalization.py",
            root / "src" / "rebuild" / "categories.py",
            root / "config" / "research_protocol.json",
            root / "config" / "category_taxonomy.yml",
            root / "config" / "category_overrides.csv",
            root / "requirements.txt",
            *sorted((root / "schemas").glob("*.json")),
        ]
        if path.exists()
    )
    material = []
    for path in source_paths:
        material.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    tree_hash = hashlib.sha256(canonical_json_bytes(material)).hexdigest()[:16]
    return f"{head}+collector.{tree_hash}"


def _reject_secret_metadata(value: Any, path: str = "request_params") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key)
            if _SECRET_KEY_PATTERN.search(key_text):
                raise ProvenanceError(f"Secret-like request metadata is forbidden: {path}.{key_text}")
            _reject_secret_metadata(nested, f"{path}.{key_text}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_secret_metadata(nested, f"{path}[{index}]")


def deterministic_build_id(
    protocol: Protocol,
    commit: str,
    records: Iterable[RawRecord],
    candidate_records_sha256: str,
) -> str:
    material = {
        "protocol_hash": protocol.protocol_hash,
        "collector_commit": commit,
        "candidate_records_sha256": candidate_records_sha256,
        "records": [
            {
                "platform": record.platform,
                "record_type": record.record_type,
                "endpoint": record.endpoint,
                "request_params": record.request_params,
                "sha256": record.sha256,
            }
            for record in sorted(
                records,
                key=lambda item: (
                    item.platform,
                    item.record_type,
                    item.endpoint,
                    json.dumps(item.request_params, sort_keys=True),
                    item.sha256,
                ),
            )
        ],
    }
    return hashlib.sha256(canonical_json_bytes(material)).hexdigest()


class RawResponseStore:
    def __init__(
        self,
        root: Path,
        protocol: Protocol,
        *,
        commit: str,
        clock: Callable[[], dt.datetime] | None = None,
    ) -> None:
        self.root = root
        self.protocol = protocol
        self.commit = commit
        self.clock = clock or (lambda: dt.datetime.now(dt.timezone.utc))
        self.records: list[RawRecord] = []

    def write_response(
        self,
        *,
        platform: str,
        record_type: str,
        endpoint: str,
        request_params: dict[str, Any],
        payload: Any,
        retrieved_at: dt.datetime | None = None,
    ) -> RawRecord:
        if platform != "polymarket":
            raise ProvenanceError(f"Unsupported platform: {platform}")
        if not endpoint.startswith("https://"):
            raise ProvenanceError("Raw endpoints must use HTTPS")
        _reject_secret_metadata(request_params)

        content = canonical_json_bytes(payload)
        digest = hashlib.sha256(content).hexdigest()
        relative = Path(platform) / record_type / digest[:2] / f"{digest}.json"
        destination = self.root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            existing = destination.read_bytes()
            if existing != content:
                raise ProvenanceError(f"Content-address collision at {destination}")
        else:
            destination.write_bytes(content)

        record = RawRecord(
            platform=platform,
            record_type=record_type,
            endpoint=endpoint,
            request_params=dict(sorted(request_params.items())),
            retrieved_at=utc_iso(retrieved_at or self.clock()),
            raw_response_path=relative.as_posix(),
            sha256=digest,
            content_bytes=len(content),
            schema_version=str(self.protocol.payload["raw_schema_version"]),
            collector_commit=self.commit,
        )
        self.records.append(record)
        return record

    def manifest(
        self,
        *,
        candidate_records_sha256: str,
        created_at: dt.datetime | None = None,
    ) -> dict[str, Any]:
        unique = {
            (
                record.platform,
                record.record_type,
                record.endpoint,
                json.dumps(record.request_params, sort_keys=True),
                record.sha256,
            ): record
            for record in self.records
        }
        records = sorted(
            unique.values(),
            key=lambda item: (
                item.platform,
                item.record_type,
                item.endpoint,
                json.dumps(item.request_params, sort_keys=True),
                item.sha256,
            ),
        )
        return {
            "schema_version": str(self.protocol.payload["raw_schema_version"]),
            "build_id": deterministic_build_id(
                self.protocol,
                self.commit,
                records,
                candidate_records_sha256,
            ),
            "protocol_id": self.protocol.protocol_id,
            "candidate_records_sha256": candidate_records_sha256,
            "created_at": utc_iso(created_at or self.clock()),
            "collector_commit": self.commit,
            "records": [asdict(record) for record in records],
        }

    def write_manifest(
        self,
        path: Path,
        *,
        candidate_records_sha256: str,
        created_at: dt.datetime | None = None,
    ) -> dict[str, Any]:
        payload = self.manifest(
            candidate_records_sha256=candidate_records_sha256,
            created_at=created_at,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_json_bytes(payload) + b"\n")
        return payload


def verify_manifest(
    manifest: dict[str, Any] | Path,
    raw_root: Path,
    protocol: Protocol,
    *,
    candidate_records_sha256: str,
) -> list[str]:
    payload = json.loads(manifest.read_text()) if isinstance(manifest, Path) else manifest
    errors: list[str] = []
    records: list[RawRecord] = []
    for item in payload.get("records", []):
        try:
            _reject_secret_metadata(item.get("request_params", {}))
            record = RawRecord(**item)
        except (TypeError, ProvenanceError) as exc:
            errors.append(f"invalid_manifest_record:{exc}")
            continue
        relative_path = Path(record.raw_response_path)
        raw_root_resolved = raw_root.resolve()
        path = (raw_root / relative_path).resolve()
        if relative_path.is_absolute() or raw_root_resolved not in path.parents:
            errors.append(f"raw_path_outside_root:{record.raw_response_path}")
            continue
        if not path.exists():
            errors.append(f"missing_raw_response:{record.raw_response_path}")
            continue
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest != record.sha256:
            errors.append(f"raw_hash_mismatch:{record.raw_response_path}")
        if len(content) != record.content_bytes:
            errors.append(f"raw_size_mismatch:{record.raw_response_path}")
        records.append(record)

    if payload.get("candidate_records_sha256") != candidate_records_sha256:
        errors.append("candidate_records_hash_mismatch")
    expected_build_id = deterministic_build_id(
        protocol,
        str(payload.get("collector_commit", "")),
        records,
        candidate_records_sha256,
    )
    if payload.get("build_id") != expected_build_id:
        errors.append("build_id_mismatch")
    if payload.get("protocol_id") != protocol.protocol_id:
        errors.append("protocol_id_mismatch")
    return errors
