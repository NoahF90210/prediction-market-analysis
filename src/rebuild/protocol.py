from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROTOCOL_PATH = ROOT / "config" / "research_protocol.json"


def parse_utc(value: str | int | float | dt.datetime | None) -> dt.datetime | None:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, dt.datetime):
            parsed = value
        elif isinstance(value, (int, float)):
            epoch = float(value)
            if abs(epoch) >= 100_000_000_000:
                epoch /= 1000
            parsed = dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc)
        else:
            text = str(value).strip()
            try:
                epoch = float(text)
            except ValueError:
                parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
            else:
                if abs(epoch) >= 100_000_000_000:
                    epoch /= 1000
                parsed = dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc)
    except (TypeError, ValueError, OSError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def utc_iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


@dataclass(frozen=True)
class Protocol:
    payload: dict[str, Any]
    path: Path

    @property
    def protocol_id(self) -> str:
        return str(self.payload["protocol_id"])

    @property
    def start(self) -> dt.datetime:
        return parse_utc(self.payload["observation_window"]["start_inclusive"])  # type: ignore[return-value]

    @property
    def end(self) -> dt.datetime:
        return parse_utc(self.payload["observation_window"]["end_exclusive"])  # type: ignore[return-value]

    @property
    def forecast_horizon(self) -> dt.timedelta:
        return dt.timedelta(seconds=int(self.payload["forecast_horizon_seconds"]))

    @property
    def max_snapshot_staleness_seconds(self) -> int:
        return int(self.payload["max_snapshot_staleness_seconds"])

    @property
    def boundary_precedence(self) -> tuple[str, ...]:
        return tuple(self.payload["forecast_boundary_precedence"])

    @property
    def allowed_snapshot_sources(self) -> frozenset[str]:
        return frozenset(self.payload["allowed_snapshot_sources"])

    @property
    def forbidden_model_features(self) -> frozenset[str]:
        return frozenset(self.payload["forbidden_model_features"])

    @property
    def protocol_hash(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.payload)).hexdigest()

    def contains_resolution(self, value: str | dt.datetime | None) -> bool:
        timestamp = parse_utc(value)
        return bool(timestamp is not None and self.start <= timestamp < self.end)

    def forecast_boundary(self, record: dict[str, Any]) -> dt.datetime | None:
        candidates = [parse_utc(record.get(field)) for field in self.boundary_precedence]
        available = [candidate for candidate in candidates if candidate is not None]
        return min(available) if available else None

    def forecast_target(self, record: dict[str, Any]) -> dt.datetime | None:
        boundary = self.forecast_boundary(record)
        return boundary - self.forecast_horizon if boundary is not None else None


def _validate_protocol_shape(payload: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "protocol_id",
        "research_question",
        "observation_window",
        "forecast_horizon_seconds",
        "max_snapshot_staleness_seconds",
        "forecast_boundary_precedence",
        "contract_selection",
        "platforms",
        "allowed_snapshot_sources",
        "forbidden_model_features",
        "publication_gate",
    }
    missing = sorted(required - payload.keys())
    if missing:
        raise ValueError(f"Protocol is missing required keys: {', '.join(missing)}")
    start = parse_utc(payload["observation_window"]["start_inclusive"])
    end = parse_utc(payload["observation_window"]["end_exclusive"])
    if start is None or end is None or start >= end:
        raise ValueError("Protocol observation window must have start < end")
    if end - start != dt.timedelta(days=181):
        raise ValueError("Protocol window must remain the frozen 2026 H1 six-calendar-month window")
    if int(payload["forecast_horizon_seconds"]) != 86_400:
        raise ValueError("Primary forecast horizon must remain 24 hours")


def load_protocol(path: Path | str = DEFAULT_PROTOCOL_PATH) -> Protocol:
    protocol_path = Path(path)
    payload = json.loads(protocol_path.read_text())
    _validate_protocol_shape(payload)
    return Protocol(payload=payload, path=protocol_path)
