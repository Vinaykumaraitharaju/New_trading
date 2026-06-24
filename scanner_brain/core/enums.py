from __future__ import annotations

from enum import Enum


class Bias(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class MarketStateLabel(str, Enum):
    STRONG_BULL = "strong_bull"
    BULL = "bull"
    NEUTRAL = "neutral"
    BEAR = "bear"
    STRONG_BEAR = "strong_bear"


class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class Grade(str, Enum):
    A_PLUS = "A+"
    A = "A"
    B = "B"
    C = "C"
    REJECT = "Reject"


class Decision(str, Enum):
    SELECTED = "selected"
    WATCHLIST = "watchlist"
    REJECTED = "rejected"


class EntryType(str, Enum):
    IDEAL = "IDEAL"
    ACCEPTABLE = "ACCEPTABLE"
    RISKY = "RISKY"
    CHASING = "CHASING"
