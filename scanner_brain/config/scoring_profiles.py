from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FastFilterProfile:
    min_price: float = 80.0
    max_price: float = 5000.0
    min_volume: int = 250000
    max_candidates: int = 45
    early_vwap_reject_pct: float = 2.2
    early_vwap_reject_atr: float = 1.85
    early_chasing_intraday_move_pct: float = 1.4
    min_intraday_range_pct: float = 0.25
    max_spread_pct: float = 0.22
    max_chaos_range_pct: float = 7.5
    max_open_wick_pct: float = 4.0
    min_tradable_ltp: float = 0.01


@dataclass(frozen=True)
class ValidationWeights:
    market: float = 12.0
    sector: float = 10.0
    technical: float = 35.0
    vwap: float = 10.0
    volume: float = 10.0
    structure: float = 8.0
    support_resistance: float = 8.0
    pattern: float = 7.0
    news: float = 3.0


@dataclass(frozen=True)
class HierarchicalGroupWeights:
    market_context: float = 0.20
    price_action_structure: float = 0.16
    trend: float = 0.14
    volume: float = 0.10
    vwap: float = 0.08
    opening_behavior: float = 0.07
    support_resistance: float = 0.06
    volatility: float = 0.05
    pattern: float = 0.04
    indicator_confirmation: float = 0.03
    liquidity_orderflow_proxy: float = 0.03
    news_events: float = 0.02
    macro_overlay: float = 0.01
    execution_quality: float = 0.06
    risk_filter: float = 0.05


@dataclass(frozen=True)
class DecisionThresholds:
    diamond: float = 86.0
    platinum: float = 76.0
    gold: float = 64.0
    silver: float = 52.0
    bronze: float = 42.0
    max_conflict_for_top5: int = 4
    min_clean_structure_score: float = 48.0
    min_execution_score: float = 45.0
    hard_block_score_cap: float = 44.0


@dataclass(frozen=True)
class GradeThresholds:
    a_plus: float = 82.0
    a: float = 72.0
    b: float = 58.0
    c: float = 45.0
    max_failed_for_a: int = 1
    max_missing_for_a_plus: int = 2
    max_contradiction_for_select: float = 18.0


@dataclass(frozen=True)
class ScoringProfile:
    fast_filter: FastFilterProfile = field(default_factory=FastFilterProfile)
    weights: ValidationWeights = field(default_factory=ValidationWeights)
    group_weights: HierarchicalGroupWeights = field(default_factory=HierarchicalGroupWeights)
    thresholds: DecisionThresholds = field(default_factory=DecisionThresholds)
    grades: GradeThresholds = field(default_factory=GradeThresholds)
    min_select_score: float = 58.0
    top_n: int = 5
    volume_spike_ratio: float = 1.25
    meaningful_gap_pct: float = 0.35
    strong_gap_pct: float = 1.0
    breakout_buffer_pct: float = 0.08
    ideal_vwap_distance_pct: float = 0.55
    acceptable_vwap_distance_pct: float = 1.0
    risky_vwap_distance_pct: float = 1.55
    extended_from_vwap_pct: float = 2.2
    ideal_vwap_distance_atr: float = 0.45
    acceptable_vwap_distance_atr: float = 0.85
    risky_vwap_distance_atr: float = 1.45
    breakout_near_vwap_pct: float = 0.9
    chasing_move_pct: float = 2.0
    min_rr_for_selection: float = 1.2
