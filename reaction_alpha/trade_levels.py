from __future__ import annotations

from dataclasses import dataclass

from .config import ReactionAlphaConfig
from .state import SymbolState
from .engines.reaction_engine import ReactionResult
from .engines.structure_engine import StructureResult


@dataclass(slots=True)
class TradeLevels:
    direction: str
    entry: float
    sl: float
    t1: float
    t2: float
    expected_move: str
    risk_points: float
    target1_points: float


def build_trade_levels(
    *,
    config: ReactionAlphaConfig,
    state: SymbolState,
    reaction: ReactionResult,
    structure: StructureResult,
    direction: str,
    setup_type: str | None = None,
    regime: str | None = None,
    setup_profile: str = "neutral",
) -> TradeLevels:
    price = state.latest_price()
    atr = max(state.atr(window=14), price * 0.0045, 0.6)
    structure_range = max(abs(structure.swing_high - structure.swing_low), atr * 1.4, price * 0.006)
    risk_unit = max(atr * 1.25, structure_range * 0.42, price * 0.0055)
    confirmation_buffer = max(atr * 0.18, price * 0.0012, 0.12)
    minimum_reward = max(config.minimum_profit_points, atr * 1.4, price * 0.0035)
    max_entry_distance = max(atr * config.intraday_max_entry_distance_atr, price * config.intraday_max_entry_distance_pct, 0.2)
    max_sl_width = max(atr * config.intraday_max_sl_width_atr, price * config.intraday_max_sl_width_pct, 0.35)
    reward_mult_1, reward_mult_2 = _reward_profile(config, reaction.classification, setup_type)
    confirmation_factor, entry_distance_factor, sl_width_factor, reward_factor = _profile_adjustments(setup_profile)
    regime_reward_factor = _regime_reward_factor(regime)
    confirmation_buffer *= confirmation_factor
    max_entry_distance *= entry_distance_factor
    max_sl_width *= sl_width_factor
    reward_mult_1 *= reward_factor * regime_reward_factor
    reward_mult_2 *= reward_factor * regime_reward_factor

    if direction == "BULLISH":
        breakout_level = max(
            [
                level
                for level in [
                    reaction.breakout_level,
                    reaction.confirmation_level,
                    structure.swing_high,
                    state.day_high,
                    price,
                ]
                if level and level > 0
            ],
            default=price,
        )
        entry_anchor = breakout_level
        raw_entry = entry_anchor + confirmation_buffer
        entry = min(raw_entry, price + max_entry_distance)
        swing_stop = min(
            [level for level in [structure.swing_low, reaction.failure_level, state.previous_day_low] if level and level > 0],
            default=price - risk_unit,
        )
        raw_sl = min(entry - (risk_unit * 0.95), swing_stop - (atr * 0.22))
        sl = max(raw_sl, entry - max_sl_width)
        risk = max(entry - sl, min(risk_unit, max_sl_width))
        reward_1 = max(risk * reward_mult_1, minimum_reward)
        reward_2 = max(risk * reward_mult_2, minimum_reward * 1.35)
        t1 = entry + reward_1
        t2 = entry + reward_2
        expected_move = f"{entry:.2f} -> {entry + max(risk * 1.6, minimum_reward * 1.2):.2f}-{t2:.2f}"
    elif direction == "BEARISH":
        breakdown_level = min(
            [
                level
                for level in [
                    reaction.breakout_level,
                    reaction.confirmation_level,
                    structure.swing_low,
                    state.day_low if state.day_low > 0 else None,
                    price,
                ]
                if level and level > 0
            ],
            default=price,
        )
        entry_anchor = breakdown_level
        raw_entry = entry_anchor - confirmation_buffer
        entry = max(raw_entry, price - max_entry_distance)
        swing_stop = max(
            [level for level in [structure.swing_high, reaction.failure_level, state.previous_day_high] if level and level > 0],
            default=price + risk_unit,
        )
        raw_sl = max(entry + (risk_unit * 0.95), swing_stop + (atr * 0.22))
        sl = min(raw_sl, entry + max_sl_width)
        risk = max(sl - entry, min(risk_unit, max_sl_width))
        reward_1 = max(risk * reward_mult_1, minimum_reward)
        reward_2 = max(risk * reward_mult_2, minimum_reward * 1.35)
        t1 = entry - reward_1
        t2 = entry - reward_2
        expected_move = f"{entry:.2f} -> {entry - max(risk * 1.6, minimum_reward * 1.2):.2f}-{t2:.2f}"
    else:
        entry = price
        sl = price - min(risk_unit, max_sl_width)
        reward_1 = max(min(risk_unit, max_sl_width) * reward_mult_1, minimum_reward)
        reward_2 = max(min(risk_unit, max_sl_width) * reward_mult_2, minimum_reward * 1.35)
        t1 = price + reward_1
        t2 = price + reward_2
        expected_move = f"{price:.2f} -> {price - risk_unit:.2f}-{price + reward_2:.2f}"

    return TradeLevels(
        direction=direction,
        entry=round(entry, 2),
        sl=round(max(0.01, sl), 2),
        t1=round(t1, 2),
        t2=round(t2, 2),
        expected_move=expected_move,
        risk_points=round(abs(entry - sl), 2),
        target1_points=round(abs(t1 - entry), 2),
    )


def resolve_trade_state(
    *,
    price: float,
    entry: float,
    t1: float,
    score: int,
    strong_threshold: int,
    direction: str,
    setup_profile: str = "neutral",
) -> str:
    if abs(t1 - entry) < 0.01:
        return "WATCH"
    profile = str(setup_profile or "neutral").lower()
    min_score = strong_threshold
    execute_width_factor = 1.0
    if profile == "preferred":
        min_score = max(strong_threshold - 1, 1)
        execute_width_factor = 1.1
    elif profile == "experimental":
        min_score = strong_threshold + 3
        execute_width_factor = 0.7
    if score < min_score:
        return "WATCH"

    if direction == "BULLISH":
        if entry <= price <= entry + max(abs(t1 - entry) * 0.35 * execute_width_factor, 1.0):
            return "EXECUTE"
        if price < entry:
            return "READY"
        return "READY"

    if direction == "BEARISH":
        if entry >= price >= entry - max(abs(t1 - entry) * 0.35 * execute_width_factor, 1.0):
            return "EXECUTE"
        if price > entry:
            return "READY"
        return "READY"

    return "WATCH"


def _reward_profile(config: ReactionAlphaConfig, reaction: str, setup_type: str | None) -> tuple[float, float]:
    setup = str(setup_type or "").upper()
    if setup == "BREAKOUT_CONTINUATION":
        return (config.breakout_t1_r_mult, config.breakout_t2_r_mult)
    if setup == "PULLBACK_CONTINUATION":
        return (config.continuation_t1_r_mult, config.continuation_t2_r_mult)
    if setup == "FAILED_BREAKOUT_REVERSAL":
        return (config.reversal_t1_r_mult, config.reversal_t2_r_mult)
    if setup == "ABSORPTION_BUILDUP":
        return (config.absorption_t1_r_mult, config.absorption_t2_r_mult)
    if setup == "SHOCK_BREAKDOWN_CONTINUATION":
        return (max(config.breakout_t1_r_mult, 1.1), max(config.breakout_t2_r_mult, 1.9))
    if setup == "PANIC_BOUNCE_FAILURE":
        return (max(config.continuation_t1_r_mult, 1.0), max(config.continuation_t2_r_mult, 1.75))
    if setup == "FLUSH_EXHAUSTION_REVERSAL":
        return (max(config.reversal_t1_r_mult, 0.95), max(config.reversal_t2_r_mult, 1.45))
    if reaction == "REVERSAL":
        return (config.reversal_t1_r_mult, config.reversal_t2_r_mult)
    if reaction == "CONTINUATION":
        return (config.continuation_t1_r_mult, config.continuation_t2_r_mult)
    return (1.0, 1.6)


def _profile_adjustments(setup_profile: str) -> tuple[float, float, float, float]:
    profile = str(setup_profile or "neutral").lower()
    if profile == "preferred":
        return (0.92, 1.0, 1.03, 1.08)
    if profile == "experimental":
        return (1.18, 0.74, 0.84, 0.88)
    return (1.0, 1.0, 1.0, 1.0)


def _regime_reward_factor(regime: str | None) -> float:
    regime_label = str(regime or "").upper()
    if regime_label == "TRENDING":
        return 1.06
    if regime_label == "CHOPPY":
        return 0.9
    if regime_label == "COMPRESSION":
        return 0.95
    return 1.0
