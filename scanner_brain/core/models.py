from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from scanner_brain.core.enums import Bias, Decision, EntryType, Grade, MarketStateLabel, Side


@dataclass(frozen=True)
class StockSnapshot:
    symbol: str
    name: str = ""
    sector: str = "Unknown"
    ltp: float = 0.0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    prev_close: float = 0.0
    volume: float = 0.0
    change_pct: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def vwap_proxy(self) -> float:
        raw_vwap = self.raw.get("vwap") or self.raw.get("average_price") or self.raw.get("avgPrice")
        try:
            value = float(raw_vwap)
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
        return self.open or self.prev_close or self.ltp

    @property
    def day_range(self) -> float:
        return max(self.high - self.low, self.ltp * 0.003, 0.01)

    @property
    def intraday_move_pct(self) -> float:
        return ((self.ltp - self.open) / self.open) * 100.0 if self.open > 0 else 0.0

    @property
    def gap_pct(self) -> float:
        return ((self.open - self.prev_close) / self.prev_close) * 100.0 if self.prev_close > 0 else 0.0

    @property
    def price_position(self) -> float:
        return max(0.0, min(1.0, (self.ltp - self.low) / self.day_range))


@dataclass(frozen=True)
class MarketRegime:
    state: MarketStateLabel
    score: float
    bias: Bias
    reasons: list[str]
    label: str = "Neutral"
    confidence: float = 50.0
    difficulty: str = "Medium"
    day_type: str = "Neutral"
    volatility_regime: str = "Normal"
    gap_environment: str = "Flat"
    risk_mood: str = "neutral"
    explanation: str = ""


@dataclass(frozen=True)
class MarketContext:
    market_bias: str
    market_strength: float
    sector_support_map: dict[str, str]
    risk_state: str
    explanation: str
    reasons: list[str]
    regime: MarketRegime


@dataclass(frozen=True)
class SectorAssessment:
    sector: str
    score: float
    bias: Bias
    rank: int
    reasons: list[str]


@dataclass(frozen=True)
class TechnicalAssessment:
    side: Side
    setup_type: str
    score: float
    entry_type: EntryType
    entry_reason: str
    passed: list[str]
    missing: list[str]
    failed: list[str]
    contradictions: list[str]
    reasons: list[str]
    support: float
    resistance: float
    trigger: float
    atr_proxy: float
    vwap_distance_pct: float = 0.0
    vwap_distance_atr: float = 0.0


@dataclass(frozen=True)
class PatternAssessment:
    detected: list[str]
    bias: Bias
    score_adjustment: float
    reasons: list[str]
    contradictions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class NewsAssessment:
    bias: Bias
    score_adjustment: float
    confidence: float
    reasons: list[str]


@dataclass(frozen=True)
class PredictionAssessment:
    bias: str
    strength: float
    status: str
    grade: str
    breakout_probability: str
    trap_risk: str
    structure_state: str
    compression_state: str
    pressure_state: str
    vwap_state: str
    volume_state: str
    exhaustion_state: str
    level_tests: int
    level_test_quality: str
    time_quality: str
    explanation: str
    key_level: float
    pressure_side: str
    ideal_scenario: str
    invalid_scenario: str
    preparation_signals: list[str]
    contradictions: list[str]
    validation_factors: list[str]
    warnings: list[str]
    snapshot_mode: bool = False


@dataclass(frozen=True)
class ExecutionAssessment:
    state: str
    direction: str
    grade: str
    entry_trigger: str
    entry_quality: str
    stop_loss: float
    target1: float
    target2: float
    avoid_reason: str
    invalidation: str
    explanation: str
    activation_rules: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class FactorSignal:
    name: str
    rating: int
    label: str
    reason: str
    weight: float = 1.0
    hard_block: bool = False


@dataclass(frozen=True)
class FactorGroupScore:
    group: str
    score: float
    weighted_points: float
    weight: float
    positive: int
    negative: int
    neutral: int
    passes: list[str]
    failures: list[str]
    neutrals: list[str]
    summary: str


@dataclass(frozen=True)
class WeightedScorecard:
    final_score: float
    grade_label: str
    conviction_label: str
    positive_count: int
    negative_count: int
    neutral_count: int
    pass_count: int
    fail_count: int
    conflict_score: int
    hard_blocks: list[str]
    boosters: list[str]
    major_passes: list[str]
    major_failures: list[str]
    group_scores: dict[str, FactorGroupScore]
    factor_heatmap: dict[str, float]
    score_drift: float = 0.0
    signal_stability: str = "fresh"
    live_conviction_change: str = "new"


@dataclass(frozen=True)
class FinalAssessment:
    symbol: str
    side: Side
    final_score: float
    grade: Grade
    decision: Decision
    setup_type: str
    entry_type: EntryType
    entry_reason: str
    passed: list[str]
    missing: list[str]
    failed: list[str]
    warnings: list[str]
    reasons: list[str]
    detected_patterns: list[str]
    confidence_note: str
    entry_low: float
    entry_high: float
    stop_loss: float
    target1: float
    target2: float
    rr: float
    invalidation_note: str
    vwap_distance_pct: float = 0.0
    vwap_distance_atr: float = 0.0
    prediction_bias: str = "NEUTRAL"
    prediction_strength: float = 0.0
    pre_breakout_status: str = "NO_SETUP"
    prediction_grade: str = "D"
    breakout_probability: str = "LOW"
    trap_risk: str = "HIGH"
    structure_state: str = "RANGE"
    compression_state: str = "NONE"
    pressure_state: str = "NEUTRAL"
    vwap_state: str = "CHOPPY"
    volume_state: str = "LOW"
    exhaustion_state: str = "ACCEPTABLE"
    level_tests: int = 0
    level_test_quality: str = "LOOSE"
    time_quality: str = "AVERAGE"
    prediction_explanation: str = ""
    key_level: float = 0.0
    pressure_side: str = ""
    ideal_scenario: str = ""
    invalid_scenario: str = ""
    preparation_signals: list[str] = field(default_factory=list)
    prediction_warnings: list[str] = field(default_factory=list)
    snapshot_mode: bool = False
    execution_state: str = "WAIT"
    execution_grade: str = "WAIT"
    execution_direction: str = "NONE"
    execution_entry_quality: str = "RISKY"
    avoid_reason: str = ""
    execution_explanation: str = ""
    validation_factors: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    market_bias: str = "neutral"
    market_strength: float = 50.0
    risk_state: str = "neutral"
    market_explanation: str = ""
    sector: str = "Unknown"
    final_selector_score: float = 0.0
    selection_bucket: str = "RISKY"
    why_selected: list[str] = field(default_factory=list)
    what_must_happen: str = ""
    why_not_higher: str = ""
    why_ranked_here: str = ""
    scorecard: WeightedScorecard | None = None
    conviction_label: str = "Reject"
    positive_count: int = 0
    negative_count: int = 0
    neutral_count: int = 0
    pass_count: int = 0
    fail_count: int = 0
    conflict_score: int = 0
    hard_blocks: list[str] = field(default_factory=list)
    boosters: list[str] = field(default_factory=list)
    major_passes: list[str] = field(default_factory=list)
    major_failures: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ScanStats:
    scanned: int
    shortlisted: int
    validated: int
    selected: int
    elapsed_ms: float


@dataclass(frozen=True)
class ScanResult:
    setups: list[FinalAssessment]
    rejected: list[dict[str, str]]
    stats: ScanStats
    market: MarketRegime
    sectors: dict[str, SectorAssessment]
    market_context: MarketContext | None = None
