from __future__ import annotations

from collections.abc import Iterable
import math


def safe_float(value: object, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def mean(values: Iterable[float]) -> float:
    data = [value for value in values if math.isfinite(value)]
    return sum(data) / len(data) if data else 0.0


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def pct_change(current: float, reference: float) -> float:
    if reference == 0:
        return 0.0
    return (current - reference) / reference


def confidence_from_score(score: float) -> float:
    centered = (score - 12.0) / 4.0
    logistic = 1.0 / (1.0 + math.exp(-centered))
    return clamp(45.0 + logistic * 50.0, 1.0, 99.0)
