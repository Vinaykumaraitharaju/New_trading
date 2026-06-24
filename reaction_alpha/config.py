from __future__ import annotations

from dataclasses import dataclass, field
import os


def _csv_env(name: str, default: str) -> list[str]:
    raw = (os.getenv(name, default) or "").strip()
    return [item.strip().upper() for item in raw.split(",") if item.strip()]


@dataclass(slots=True)
class ReactionAlphaConfig:
    symbols: list[str] = field(default_factory=lambda: _csv_env("REACTION_ALPHA_SYMBOLS", "RELIANCE,HDFCBANK,ICICIBANK,INFY,TCS"))
    exchange_segment: str = os.getenv("REACTION_ALPHA_EXCHANGE", "nse_cm").strip().lower()
    top_n: int = int(os.getenv("REACTION_ALPHA_TOP_N", "5"))
    dynamic_universe_enabled: bool = (os.getenv("REACTION_ALPHA_DYNAMIC_UNIVERSE", "true").strip().lower() == "true")
    dynamic_universe_size: int = int(os.getenv("REACTION_ALPHA_DYNAMIC_UNIVERSE_SIZE", "5"))
    dynamic_scan_universe: int = int(os.getenv("REACTION_ALPHA_DYNAMIC_SCAN_UNIVERSE", "120"))
    dynamic_refresh_sec: float = float(os.getenv("REACTION_ALPHA_DYNAMIC_REFRESH_SEC", "180"))
    dynamic_max_per_sector: int = int(os.getenv("REACTION_ALPHA_DYNAMIC_MAX_PER_SECTOR", "2"))
    dynamic_speed_weight: float = float(os.getenv("REACTION_ALPHA_DYNAMIC_SPEED_WEIGHT", "18"))
    minimum_profit_points: float = float(os.getenv("REACTION_ALPHA_MIN_PROFIT_POINTS", "10"))
    paper_trading_enabled: bool = (os.getenv("REACTION_ALPHA_PAPER_TRADING", "true").strip().lower() == "true")
    paper_trade_pending_expiry_min: int = int(os.getenv("REACTION_ALPHA_PAPER_PENDING_EXPIRY_MIN", "20"))
    paper_trade_max_hold_min: int = int(os.getenv("REACTION_ALPHA_PAPER_MAX_HOLD_MIN", "45"))
    paper_trade_db_path: str = os.getenv("REACTION_ALPHA_PAPER_DB", "storage/reaction_alpha_paper_trades.db").strip()
    paper_trade_slippage_bps: float = float(os.getenv("REACTION_ALPHA_PAPER_SLIPPAGE_BPS", "3.0"))
    paper_trade_spread_capture_ratio: float = float(os.getenv("REACTION_ALPHA_PAPER_SPREAD_RATIO", "0.35"))
    paper_trade_fixed_cost_points: float = float(os.getenv("REACTION_ALPHA_PAPER_FIXED_COST_POINTS", "0.05"))
    paper_trade_entry_confirm_ratio: float = float(os.getenv("REACTION_ALPHA_PAPER_ENTRY_CONFIRM_RATIO", "0.08"))
    paper_trade_max_chase_ratio: float = float(os.getenv("REACTION_ALPHA_PAPER_MAX_CHASE_RATIO", "0.22"))
    paper_trade_candidate_freeze_sec: int = int(os.getenv("REACTION_ALPHA_PAPER_CANDIDATE_FREEZE_SEC", "90"))
    paper_trade_pending_min_age_sec: int = int(os.getenv("REACTION_ALPHA_PAPER_PENDING_MIN_AGE_SEC", "15"))
    paper_trade_pending_max_distance_pct: float = float(os.getenv("REACTION_ALPHA_PAPER_PENDING_MAX_DISTANCE_PCT", "0.45"))
    paper_trade_pending_max_choppy_distance_pct: float = float(os.getenv("REACTION_ALPHA_PAPER_PENDING_MAX_CHOPPY_DISTANCE_PCT", "0.20"))
    paper_trade_choppy_confirm_multiplier: float = float(os.getenv("REACTION_ALPHA_PAPER_CHOPPY_CONFIRM_MULT", "1.45"))
    paper_trade_choppy_chase_multiplier: float = float(os.getenv("REACTION_ALPHA_PAPER_CHOPPY_CHASE_MULT", "0.72"))
    paper_trade_early_exit_enabled: bool = (os.getenv("REACTION_ALPHA_PAPER_EARLY_EXIT", "true").strip().lower() == "true")
    paper_trade_early_exit_min_hold_sec: int = int(os.getenv("REACTION_ALPHA_PAPER_EARLY_EXIT_MIN_HOLD_SEC", "60"))
    paper_trade_early_exit_adverse_r: float = float(os.getenv("REACTION_ALPHA_PAPER_EARLY_EXIT_ADVERSE_R", "0.45"))
    paper_trade_early_exit_mfe_r: float = float(os.getenv("REACTION_ALPHA_PAPER_EARLY_EXIT_MFE_R", "0.25"))
    adaptive_setup_guard_enabled: bool = (os.getenv("REACTION_ALPHA_ADAPTIVE_SETUP_GUARD", "true").strip().lower() == "true")
    adaptive_setup_guard_min_entries: int = int(os.getenv("REACTION_ALPHA_ADAPTIVE_SETUP_GUARD_MIN_ENTRIES", "1"))
    adaptive_setup_guard_sl_rate: float = float(os.getenv("REACTION_ALPHA_ADAPTIVE_SETUP_GUARD_SL_RATE", "0.75"))
    adaptive_setup_guard_clean_rate: float = float(os.getenv("REACTION_ALPHA_ADAPTIVE_SETUP_GUARD_CLEAN_RATE", "0.50"))
    adaptive_setup_guard_min_expectancy_entries: int = int(os.getenv("REACTION_ALPHA_ADAPTIVE_SETUP_GUARD_MIN_EXPECTANCY_ENTRIES", "3"))
    adaptive_setup_guard_negative_expectancy_points: float = float(os.getenv("REACTION_ALPHA_ADAPTIVE_SETUP_GUARD_NEG_EXPECTANCY_POINTS", "-0.10"))
    hard_block_max_spread_bps: float = float(os.getenv("REACTION_ALPHA_HARD_BLOCK_MAX_SPREAD_BPS", "12"))
    hard_block_max_vwap_distance_pct: float = float(os.getenv("REACTION_ALPHA_HARD_BLOCK_MAX_VWAP_DISTANCE_PCT", "1.20"))
    hard_block_choppy_max_vwap_distance_pct: float = float(os.getenv("REACTION_ALPHA_HARD_BLOCK_CHOPPY_MAX_VWAP_DISTANCE_PCT", "0.55"))
    hard_block_choppy_min_volume_score: int = int(os.getenv("REACTION_ALPHA_HARD_BLOCK_CHOPPY_MIN_VOLUME_SCORE", "4"))
    hard_block_choppy_min_orderflow_score: int = int(os.getenv("REACTION_ALPHA_HARD_BLOCK_CHOPPY_MIN_ORDERFLOW_SCORE", "2"))
    hard_block_against_context_pct: float = float(os.getenv("REACTION_ALPHA_HARD_BLOCK_AGAINST_CONTEXT_PCT", "0.15"))
    reaction_window_ticks: int = int(os.getenv("REACTION_ALPHA_REACTION_WINDOW_TICKS", "14"))
    swing_lookback_candles: int = int(os.getenv("REACTION_ALPHA_SWING_LOOKBACK", "40"))
    volume_spike_multiplier: float = float(os.getenv("REACTION_ALPHA_VOLUME_SPIKE_MULTIPLIER", "2.5"))
    price_expansion_threshold: float = float(os.getenv("REACTION_ALPHA_PRICE_EXPANSION_THRESHOLD", "0.0035"))
    orderflow_shift_threshold: float = float(os.getenv("REACTION_ALPHA_ORDERFLOW_SHIFT_THRESHOLD", "0.18"))
    speed_velocity_threshold_bps_15s: float = float(os.getenv("REACTION_ALPHA_SPEED_BPS_15S", "22"))
    speed_velocity_threshold_bps_30s: float = float(os.getenv("REACTION_ALPHA_SPEED_BPS_30S", "38"))
    speed_ignore_threshold: int = int(os.getenv("REACTION_ALPHA_SPEED_IGNORE_THRESHOLD", "-2"))
    elite_threshold: int = int(os.getenv("REACTION_ALPHA_ELITE_THRESHOLD", "18"))
    strong_threshold: int = int(os.getenv("REACTION_ALPHA_STRONG_THRESHOLD", "12"))
    signal_stale_sec: int = int(os.getenv("REACTION_ALPHA_SIGNAL_STALE_SEC", "90"))
    intraday_max_entry_distance_atr: float = float(os.getenv("REACTION_ALPHA_MAX_ENTRY_DISTANCE_ATR", "0.75"))
    intraday_max_entry_distance_pct: float = float(os.getenv("REACTION_ALPHA_MAX_ENTRY_DISTANCE_PCT", "0.0028"))
    intraday_max_sl_width_atr: float = float(os.getenv("REACTION_ALPHA_MAX_SL_WIDTH_ATR", "1.15"))
    intraday_max_sl_width_pct: float = float(os.getenv("REACTION_ALPHA_MAX_SL_WIDTH_PCT", "0.0048"))
    continuation_t1_r_mult: float = float(os.getenv("REACTION_ALPHA_CONT_T1_R", "1.10"))
    continuation_t2_r_mult: float = float(os.getenv("REACTION_ALPHA_CONT_T2_R", "1.85"))
    breakout_t1_r_mult: float = float(os.getenv("REACTION_ALPHA_BREAKOUT_T1_R", "1.20"))
    breakout_t2_r_mult: float = float(os.getenv("REACTION_ALPHA_BREAKOUT_T2_R", "2.00"))
    reversal_t1_r_mult: float = float(os.getenv("REACTION_ALPHA_REVERSAL_T1_R", "0.95"))
    reversal_t2_r_mult: float = float(os.getenv("REACTION_ALPHA_REVERSAL_T2_R", "1.50"))
    absorption_t1_r_mult: float = float(os.getenv("REACTION_ALPHA_ABSORPTION_T1_R", "0.90"))
    absorption_t2_r_mult: float = float(os.getenv("REACTION_ALPHA_ABSORPTION_T2_R", "1.40"))
    setup_preferred_score_boost: int = int(os.getenv("REACTION_ALPHA_SETUP_PREFERRED_SCORE_BOOST", "2"))
    setup_experimental_score_penalty: int = int(os.getenv("REACTION_ALPHA_SETUP_EXPERIMENTAL_SCORE_PENALTY", "3"))
    setup_experimental_min_extra_score: int = int(os.getenv("REACTION_ALPHA_SETUP_EXPERIMENTAL_MIN_EXTRA_SCORE", "3"))
    tick_buffer_size: int = int(os.getenv("REACTION_ALPHA_TICK_BUFFER", "600"))
    candle_buffer_size: int = int(os.getenv("REACTION_ALPHA_CANDLE_BUFFER", "240"))
    heartbeat_sec: float = float(os.getenv("REACTION_ALPHA_HEARTBEAT_SEC", "0.2"))
    telegram_bot_token: str = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    telegram_chat_id: str = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    webhook_secret: str = (os.getenv("REACTION_ALPHA_WEBHOOK_SECRET") or "").strip()
    simulated: bool = (os.getenv("REACTION_ALPHA_SIMULATED", "false").strip().lower() == "true")
    simulated_market_always_open: bool = (os.getenv("REACTION_ALPHA_SIM_ALWAYS_OPEN", "false").strip().lower() == "true")
    pretrade_scan_universe: int = int(os.getenv("REACTION_ALPHA_PRETRADE_SCAN_UNIVERSE", "120"))
    pretrade_cache_sec: float = float(os.getenv("REACTION_ALPHA_PRETRADE_CACHE_SEC", "20"))
    pretrade_min_score: float = float(os.getenv("REACTION_ALPHA_PRETRADE_MIN_SCORE", "42"))


def classify_setup_profile(setup_type: str, regime: str, direction: str = "") -> str:
    setup = str(setup_type or "").upper()
    regime_label = str(regime or "").upper()

    preferred_map = {
        "BREAKOUT_CONTINUATION": {"TRENDING", "EXPANSION"},
        "PULLBACK_CONTINUATION": {"TRENDING", "BALANCED"},
        "FAILED_BREAKOUT_REVERSAL": {"CHOPPY", "BALANCED"},
        "ABSORPTION_BUILDUP": {"COMPRESSION", "BALANCED"},
        "STRUCTURE_COMPRESSION": {"COMPRESSION", "BALANCED"},
        "SHOCK_BREAKDOWN_CONTINUATION": {"TRENDING", "EXPANSION", "DISCOVERY"},
        "PANIC_BOUNCE_FAILURE": {"EXPANSION", "DISCOVERY", "CHOPPY"},
        "FLUSH_EXHAUSTION_REVERSAL": {"BALANCED", "CHOPPY", "DISCOVERY"},
    }
    experimental_map = {
        "BREAKOUT_CONTINUATION": {"CHOPPY", "COMPRESSION"},
        "PULLBACK_CONTINUATION": {"CHOPPY", "COMPRESSION"},
        "FAILED_BREAKOUT_REVERSAL": {"TRENDING", "EXPANSION"},
        "ABSORPTION_BUILDUP": {"TRENDING", "EXPANSION"},
        "STRUCTURE_COMPRESSION": {"TRENDING", "EXPANSION"},
        "SHOCK_BREAKDOWN_CONTINUATION": {"BALANCED", "COMPRESSION"},
        "PANIC_BOUNCE_FAILURE": {"COMPRESSION"},
        "FLUSH_EXHAUSTION_REVERSAL": {"TRENDING", "EXPANSION"},
        "EVENT_REACTION": {"TRENDING", "BALANCED", "CHOPPY", "EXPANSION", "DISCOVERY", "COMPRESSION"},
    }

    if regime_label in preferred_map.get(setup, set()):
        return "preferred"
    if regime_label in experimental_map.get(setup, set()):
        return "experimental"
    return "neutral"


def setup_profile_score_adjustment(config: ReactionAlphaConfig, profile: str) -> int:
    label = str(profile or "neutral").lower()
    if label == "preferred":
        return int(config.setup_preferred_score_boost)
    if label == "experimental":
        return -int(config.setup_experimental_score_penalty)
    return 0


def setup_profile_min_score(config: ReactionAlphaConfig, profile: str) -> int:
    label = str(profile or "neutral").lower()
    if label == "preferred":
        return max(config.strong_threshold - 1, 1)
    if label == "experimental":
        return config.strong_threshold + int(config.setup_experimental_min_extra_score)
    return config.strong_threshold
