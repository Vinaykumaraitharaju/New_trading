from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class TickData:
    symbol: str
    instrument_token: str
    exchange_segment: str
    timestamp: datetime
    price: float
    volume: float
    bid: float
    ask: float
    bid_size: float
    ask_size: float
    vwap: float
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def spread(self) -> float:
        if self.bid > 0 and self.ask > 0:
            return max(self.ask - self.bid, 0.0)
        return 0.0

    @property
    def imbalance(self) -> float:
        total = self.bid_size + self.ask_size
        if total <= 0:
            return 0.0
        return (self.bid_size - self.ask_size) / total


@dataclass(slots=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float


@dataclass(slots=True)
class MarketEvent:
    event_type: str
    timestamp: datetime
    price: float
    trigger_value: float
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ReactionResult:
    classification: str
    score: int
    reasons: list[str]
    breakout_level: float
    confirmation_level: float
    failure_level: float


@dataclass(slots=True)
class StructureResult:
    trend: str
    structure_label: str
    score: int
    bos: bool
    choch: bool
    swing_high: float
    swing_low: float
    reasons: list[str]


@dataclass(slots=True)
class ComponentScore:
    name: str
    score: int
    reasons: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TradeSignal:
    stock: str
    event: str
    reaction: str
    signal: str
    direction: str
    setup_type: str
    regime: str
    trend: str
    score: int
    entry: float
    sl: float
    t1: float
    t2: float
    expected_move: str
    confidence: str
    reason: list[str]
    timestamp: str
    components: dict[str, int] = field(default_factory=dict)
    probability: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    raw_confidence: float = 0.0
    state: str = "ACTIVE"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["updated_at"] = self.timestamp
        return payload
