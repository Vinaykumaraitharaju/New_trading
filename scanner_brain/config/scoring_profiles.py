from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
class StockReactionProfile:
    """Per-stock sensitivity layer used to avoid one-size-fits-all scoring."""

    name: str = "Balanced"
    description: str = "Balanced stock: structure, volume, context, and execution are treated evenly."
    group_multipliers: dict[str, float] = field(default_factory=dict)
    sensitivities: dict[str, float] = field(default_factory=dict)


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


DEFAULT_REACTION_PROFILE = StockReactionProfile(
    sensitivities={
        "market_context": 1.0,
        "price_action_structure": 1.0,
        "trend": 1.0,
        "volume": 1.0,
        "liquidity_orderflow_proxy": 1.0,
        "news_events": 1.0,
        "macro_overlay": 1.0,
    }
)


SECTOR_REACTION_PROFILES: dict[str, StockReactionProfile] = {
    "BANK": StockReactionProfile(
        name="Banking / Rates Sensitive",
        description="Banks react more to index alignment, rates, sector flow, options-like positioning, and execution clarity.",
        group_multipliers={
            "market_context": 1.18,
            "liquidity_orderflow_proxy": 1.18,
            "volume": 1.08,
            "macro_overlay": 1.35,
            "news_events": 0.85,
            "support_resistance": 0.92,
        },
        sensitivities={"market_context": 0.9, "liquidity_orderflow_proxy": 0.85, "macro_overlay": 0.85, "news_events": 0.55},
    ),
    "FINANCIAL": StockReactionProfile(
        name="Financial / Flow Sensitive",
        description="Financial stocks need stronger market, sector, and order-flow confirmation than isolated news.",
        group_multipliers={"market_context": 1.15, "liquidity_orderflow_proxy": 1.14, "volume": 1.08, "macro_overlay": 1.25, "news_events": 0.9},
        sensitivities={"market_context": 0.85, "liquidity_orderflow_proxy": 0.85, "macro_overlay": 0.8, "news_events": 0.6},
    ),
    "IT": StockReactionProfile(
        name="IT / Global-Macro Sensitive",
        description="IT names receive extra weight for global macro and news/deal context, with market flow still required for confirmation.",
        group_multipliers={
            "market_context": 1.08,
            "macro_overlay": 1.45,
            "news_events": 1.25,
            "volume": 0.95,
            "liquidity_orderflow_proxy": 0.96,
        },
        sensitivities={"market_context": 0.75, "macro_overlay": 0.9, "news_events": 0.82, "volume": 0.65},
    ),
    "PHARMA": StockReactionProfile(
        name="Pharma / Event Sensitive",
        description="Pharma names can move sharply on approvals, inspections, litigation, and management commentary.",
        group_multipliers={"news_events": 1.55, "macro_overlay": 1.18, "volume": 1.08, "liquidity_orderflow_proxy": 1.05, "trend": 0.92},
        sensitivities={"news_events": 0.92, "macro_overlay": 0.75, "volume": 0.7, "liquidity_orderflow_proxy": 0.68},
    ),
    "ENERGY": StockReactionProfile(
        name="Energy / Commodity Sensitive",
        description="Energy stocks need more global commodity, sector, and demand-supply confirmation.",
        group_multipliers={"market_context": 1.08, "macro_overlay": 1.5, "sector": 1.15, "volume": 1.1, "news_events": 1.1},
        sensitivities={"market_context": 0.75, "macro_overlay": 0.92, "volume": 0.78, "news_events": 0.72},
    ),
    "METAL": StockReactionProfile(
        name="Metals / Commodity Cycle Sensitive",
        description="Metals are weighted toward global commodity cues, sector strength, and volume confirmation.",
        group_multipliers={"market_context": 1.08, "macro_overlay": 1.55, "volume": 1.12, "trend": 1.05, "news_events": 0.95},
        sensitivities={"market_context": 0.75, "macro_overlay": 0.95, "volume": 0.8, "news_events": 0.62},
    ),
    "AUTO": StockReactionProfile(
        name="Auto / Demand Data Sensitive",
        description="Auto names respond to monthly demand data, commodity input costs, sector rotation, and clean trend confirmation.",
        group_multipliers={"news_events": 1.18, "macro_overlay": 1.18, "market_context": 1.08, "trend": 1.06, "volume": 1.04},
        sensitivities={"news_events": 0.75, "macro_overlay": 0.75, "market_context": 0.72, "trend": 0.72},
    ),
    "FMCG": StockReactionProfile(
        name="FMCG / Defensive Demand Sensitive",
        description="FMCG usually needs slower confirmation from sector rotation, margins, and news instead of pure momentum.",
        group_multipliers={"news_events": 1.22, "macro_overlay": 1.18, "market_context": 0.9, "volume": 0.92, "execution_quality": 1.08},
        sensitivities={"news_events": 0.78, "macro_overlay": 0.7, "volume": 0.55, "liquidity_orderflow_proxy": 0.55},
    ),
}


SYMBOL_REACTION_PROFILES: dict[str, StockReactionProfile] = {
    "RELIANCE": StockReactionProfile(
        name="Reliance / Multi-Factor Bellwether",
        description="Reliance is treated as a mixed energy, index, news, and flow-sensitive bellwether.",
        group_multipliers={"market_context": 1.12, "macro_overlay": 1.35, "news_events": 1.22, "volume": 1.08, "liquidity_orderflow_proxy": 1.08},
        sensitivities={"market_context": 0.82, "macro_overlay": 0.86, "news_events": 0.82, "volume": 0.75, "liquidity_orderflow_proxy": 0.76},
    ),
    "INFY": StockReactionProfile(
        name="Infosys / IT Global Cue Sensitive",
        description="Infosys gets higher sensitivity to global tech, currency, guidance, and deal-related news.",
        group_multipliers={"macro_overlay": 1.55, "news_events": 1.35, "market_context": 1.08, "volume": 0.95},
        sensitivities={"macro_overlay": 0.92, "news_events": 0.88, "market_context": 0.78, "volume": 0.62},
    ),
    "TCS": StockReactionProfile(
        name="TCS / IT Global Cue Sensitive",
        description="TCS is weighted toward global tech, currency, results, guidance, and institutional flow.",
        group_multipliers={"macro_overlay": 1.5, "news_events": 1.3, "market_context": 1.08, "liquidity_orderflow_proxy": 1.05},
        sensitivities={"macro_overlay": 0.9, "news_events": 0.84, "market_context": 0.78, "liquidity_orderflow_proxy": 0.68},
    ),
    "HDFCBANK": StockReactionProfile(
        name="HDFC Bank / Index-Flow Sensitive",
        description="HDFC Bank needs strong bank index, macro, and order-flow confirmation; isolated news is discounted.",
        group_multipliers={"market_context": 1.25, "liquidity_orderflow_proxy": 1.24, "volume": 1.1, "macro_overlay": 1.35, "news_events": 0.82},
        sensitivities={"market_context": 0.9, "liquidity_orderflow_proxy": 0.88, "macro_overlay": 0.84, "news_events": 0.5},
    ),
    "ICICIBANK": StockReactionProfile(
        name="ICICI Bank / Index-Flow Sensitive",
        description="ICICI Bank is treated as market, bank-index, and order-flow led.",
        group_multipliers={"market_context": 1.22, "liquidity_orderflow_proxy": 1.24, "volume": 1.1, "macro_overlay": 1.3, "news_events": 0.85},
        sensitivities={"market_context": 0.9, "liquidity_orderflow_proxy": 0.88, "macro_overlay": 0.82, "news_events": 0.55},
    ),
}


REACTION_COMPONENT_MAP: dict[str, str] = {
    "reaction": "news_events",
    "structure": "price_action_structure",
    "sr": "support_resistance",
    "pattern": "pattern",
    "volume": "volume",
    "orderflow": "liquidity_orderflow_proxy",
    "vwap": "vwap",
    "volatility": "volatility",
    "speed": "trend",
    "market": "market_context",
    "buildup": "volume",
    "fake_move": "risk_filter",
}


def reaction_profile_for_stock(symbol: str, sector: str = "", raw: dict[str, Any] | None = None) -> StockReactionProfile:
    """Return the best available sensitivity profile for a symbol.

    Raw quote data can override this with:
    raw["reaction_profile"] = {
        "name": "...",
        "description": "...",
        "group_multipliers": {"news_events": 1.4},
        "sensitivities": {"news_events": 0.9},
    }
    """

    profile = DEFAULT_REACTION_PROFILE
    sector_profile = _sector_profile(sector)
    if sector_profile is not None:
        profile = _merge_reaction_profiles(profile, sector_profile)
    symbol_profile = SYMBOL_REACTION_PROFILES.get(str(symbol or "").upper().strip())
    if symbol_profile is not None:
        profile = _merge_reaction_profiles(profile, symbol_profile)

    raw_profile = (raw or {}).get("reaction_profile") or (raw or {}).get("stock_profile")
    if isinstance(raw_profile, dict):
        profile = _merge_reaction_profiles(
            profile,
            StockReactionProfile(
                name=str(raw_profile.get("name") or profile.name),
                description=str(raw_profile.get("description") or profile.description),
                group_multipliers=_clean_float_map(raw_profile.get("group_multipliers")),
                sensitivities=_clean_float_map(raw_profile.get("sensitivities") or raw_profile.get("metric_sensitivity")),
            ),
        )
    return profile


def multiplier_for_group(profile: StockReactionProfile, group: str) -> float:
    return max(0.2, min(2.5, float(profile.group_multipliers.get(group, 1.0))))


def sensitivity_for_group(profile: StockReactionProfile, group: str) -> float:
    return max(0.2, min(1.25, float(profile.sensitivities.get(group, 1.0))))


def adaptive_component_score(score: float, profile: StockReactionProfile, group: str) -> float:
    """Scale a signal by stock personality without flipping its direction."""

    if score == 0:
        return 0.0
    multiplier = multiplier_for_group(profile, group)
    sensitivity = sensitivity_for_group(profile, group)
    return float(score) * multiplier * sensitivity


def adaptive_signal_components(
    components: dict[str, int | float],
    profile: StockReactionProfile,
    *,
    component_map: dict[str, str] | None = None,
) -> dict[str, float]:
    mapping = component_map or REACTION_COMPONENT_MAP
    return {
        name: round(adaptive_component_score(float(score), profile, mapping.get(name, name)), 2)
        for name, score in components.items()
    }


def _sector_profile(sector: str) -> StockReactionProfile | None:
    label = str(sector or "").upper()
    for key, profile in SECTOR_REACTION_PROFILES.items():
        if key in label:
            return profile
    return None


def _merge_reaction_profiles(base: StockReactionProfile, override: StockReactionProfile) -> StockReactionProfile:
    return StockReactionProfile(
        name=override.name or base.name,
        description=override.description or base.description,
        group_multipliers={**base.group_multipliers, **override.group_multipliers},
        sensitivities={**base.sensitivities, **override.sensitivities},
    )


def _clean_float_map(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    cleaned: dict[str, float] = {}
    for key, raw_value in value.items():
        try:
            cleaned[str(key)] = max(0.2, min(2.5, float(raw_value)))
        except (TypeError, ValueError):
            continue
    return cleaned
