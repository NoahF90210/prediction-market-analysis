from __future__ import annotations

import math
from typing import Any


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        if isinstance(value, str):
            value = value.strip().replace("$", "").replace(",", "")
            if not value:
                return None
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_probability(value: object) -> float | None:
    probability = to_float(value)
    if probability is None:
        return None
    if 1 < probability <= 100:
        probability /= 100
    if 0 <= probability <= 1:
        return probability
    return None
