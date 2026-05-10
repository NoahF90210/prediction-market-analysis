from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass
from typing import Iterable

from src.accuracy import NON_TRIVIAL_MAX, NON_TRIVIAL_MIN, normalize_probability

PRIMARY_FORECAST_HORIZON = "30m"
FORECAST_HORIZONS_SECONDS: dict[str, int] = {
    PRIMARY_FORECAST_HORIZON: 30 * 60,
    "1d": 24 * 60 * 60,
    "7d": 7 * 24 * 60 * 60,
}
FORECAST_HORIZONS: tuple[str, ...] = tuple(FORECAST_HORIZONS_SECONDS.keys())
SECONDARY_FORECAST_HORIZONS: tuple[str, ...] = tuple(
    horizon for horizon in FORECAST_HORIZONS if horizon != PRIMARY_FORECAST_HORIZON
)


@dataclass(frozen=True)
class ForecastSnapshot:
    probability: float | None
    source: str | None
    observed_at: str | None
    target_time: str | None
    seconds_before_close: float | None
    horizon: str
    quality: str

    def to_record(self, prefix: str = "forecast") -> dict[str, object]:
        return {
            f"{prefix}_prob": self.probability,
            f"{prefix}_source": self.source,
            f"{prefix}_observed_at": self.observed_at,
            f"{prefix}_target_time": self.target_time,
            f"{prefix}_seconds_before_close": self.seconds_before_close,
            f"{prefix}_horizon": self.horizon,
            f"{prefix}_quality": self.quality,
        }

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def parse_timestamp(value) -> dt.datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, dt.datetime):
        ts = value
    else:
        try:
            if isinstance(value, (int, float)):
                ts = dt.datetime.fromtimestamp(float(value), tz=dt.timezone.utc)
            else:
                text = str(value).strip()
                if text.isdigit():
                    ts = dt.datetime.fromtimestamp(float(text), tz=dt.timezone.utc)
                else:
                    ts = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        except (TypeError, ValueError, OSError):
            return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.timezone.utc)
    return ts.astimezone(dt.timezone.utc)


def isoformat(ts: dt.datetime | None) -> str | None:
    return ts.isoformat() if ts is not None else None


def horizon_seconds(horizon: str = PRIMARY_FORECAST_HORIZON) -> int:
    try:
        return FORECAST_HORIZONS_SECONDS[horizon]
    except KeyError as exc:
        raise ValueError(f"Unsupported forecast horizon: {horizon}") from exc


def target_time(close_time, horizon: str = PRIMARY_FORECAST_HORIZON) -> dt.datetime | None:
    close = parse_timestamp(close_time)
    if close is None:
        return None
    return close - dt.timedelta(seconds=horizon_seconds(horizon))


def _point_timestamp(point: dict, time_keys: tuple[str, ...]) -> dt.datetime | None:
    for key in time_keys:
        if key in point:
            ts = parse_timestamp(point.get(key))
            if ts is not None:
                return ts
    return None


def _point_probability(point: dict, price_keys: tuple[str, ...]) -> float | None:
    for key in price_keys:
        if key in point:
            p = normalize_probability(point.get(key))
            if p is not None:
                return p
    return None


def forecast_from_history(
    history: Iterable[dict],
    *,
    close_time,
    source: str,
    horizon: str = PRIMARY_FORECAST_HORIZON,
    time_keys: tuple[str, ...] = ("t", "created_time", "ts", "timestamp"),
    price_keys: tuple[str, ...] = ("p", "yes_price_dollars", "yes_price", "price"),
) -> ForecastSnapshot:
    close = parse_timestamp(close_time)
    cutoff = target_time(close, horizon) if close is not None else None
    points: list[tuple[dt.datetime | None, float]] = []

    for point in history or []:
        p = _point_probability(point, price_keys)
        if p is None:
            continue
        points.append((_point_timestamp(point, time_keys), p))

    if not points:
        return ForecastSnapshot(None, None, None, isoformat(cutoff), None, horizon, "missing_history")

    if cutoff is None:
        ordered = points
        quality = "missing_close_time"
    else:
        ordered = [(ts, p) for ts, p in points if ts is not None and ts <= cutoff]
        quality = "time_guarded"

    if not ordered:
        return ForecastSnapshot(None, None, None, isoformat(cutoff), None, horizon, "no_price_before_cutoff")

    ordered.sort(key=lambda item: item[0] or dt.datetime.min.replace(tzinfo=dt.timezone.utc))
    chosen_ts, chosen_p = next(
        ((ts, p) for ts, p in reversed(ordered) if NON_TRIVIAL_MIN <= p <= NON_TRIVIAL_MAX),
        ordered[-1],
    )
    if not (NON_TRIVIAL_MIN <= chosen_p <= NON_TRIVIAL_MAX):
        quality = "terminal_price_fallback" if cutoff is not None else "missing_close_time_terminal_fallback"

    seconds_before_close = None
    if close is not None and chosen_ts is not None:
        seconds_before_close = (close - chosen_ts).total_seconds()

    return ForecastSnapshot(
        probability=chosen_p,
        source=source,
        observed_at=isoformat(chosen_ts),
        target_time=isoformat(cutoff),
        seconds_before_close=seconds_before_close,
        horizon=horizon,
        quality=quality,
    )


def fallback_snapshot(
    probability: float | None,
    *,
    source: str,
    close_time=None,
    horizon: str = PRIMARY_FORECAST_HORIZON,
    quality: str = "metadata_fallback",
) -> ForecastSnapshot:
    cutoff = target_time(close_time, horizon)
    return ForecastSnapshot(
        probability=probability,
        source=source if probability is not None else None,
        observed_at=None,
        target_time=isoformat(cutoff),
        seconds_before_close=None,
        horizon=horizon,
        quality=quality if probability is not None else "missing_forecast",
    )


def summarize_snapshots(
    history: Iterable[dict],
    *,
    close_time,
    source: str,
    horizons: Iterable[str] = FORECAST_HORIZONS,
    time_keys: tuple[str, ...] = ("t", "created_time", "ts", "timestamp"),
    price_keys: tuple[str, ...] = ("p", "yes_price_dollars", "yes_price", "price"),
) -> dict[str, ForecastSnapshot]:
    snapshots: dict[str, ForecastSnapshot] = {}
    for horizon in horizons:
        snapshots[horizon] = forecast_from_history(
            history,
            close_time=close_time,
            source=source,
            horizon=horizon,
            time_keys=time_keys,
            price_keys=price_keys,
        )
    return snapshots


def snapshot_suffix(horizon: str) -> str:
    return "" if horizon == PRIMARY_FORECAST_HORIZON else f"_{horizon}"


def snapshot_to_columns(snapshot: ForecastSnapshot, *, horizon: str) -> dict[str, object]:
    suffix = snapshot_suffix(horizon)
    return {
        f"forecast_prob{suffix}": snapshot.probability,
        f"forecast_source{suffix}": snapshot.source,
        f"forecast_observed_at{suffix}": snapshot.observed_at,
        f"forecast_target_time{suffix}": snapshot.target_time,
        f"forecast_seconds_before_close{suffix}": snapshot.seconds_before_close,
        f"forecast_horizon{suffix}": snapshot.horizon,
        f"forecast_quality{suffix}": snapshot.quality,
    }
