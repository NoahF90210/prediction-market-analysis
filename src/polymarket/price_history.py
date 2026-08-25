"""Selection rules for a pre-cutoff YES price."""
from __future__ import annotations

from datetime import datetime, timezone


def select_latest_pre_cutoff(history: list[dict], cutoff: datetime, max_age_hours: int) -> dict:
    cutoff = cutoff.astimezone(timezone.utc)
    candidates = []
    for point in history:
        try:
            timestamp = datetime.fromtimestamp(float(point["t"]), tz=timezone.utc)
            price = float(point["p"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("malformed price-history point") from exc
        if not 0 <= price <= 1:
            raise ValueError("price must be between 0 and 1")
        if timestamp <= cutoff:
            candidates.append((timestamp, price))
    if not candidates:
        raise ValueError("no price at or before cutoff")
    timestamp, price = max(candidates)
    age_hours = (cutoff - timestamp).total_seconds() / 3600
    if age_hours > max_age_hours:
        raise ValueError("latest pre-cutoff price is too stale")
    return {"timestamp": timestamp.isoformat().replace("+00:00", "Z"), "price": price, "age_hours": age_hours}
