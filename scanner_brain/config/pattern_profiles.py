from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PatternProfile:
    doji_body_ratio: float = 0.14
    marubozu_body_ratio: float = 0.72
    hammer_wick_ratio: float = 0.55
    shooting_star_wick_ratio: float = 0.55
    base_weight: float = 3.0
    contextual_weight: float = 7.0
    conflict_weight: float = -7.0
    weak_pattern_weight: float = 2.0
