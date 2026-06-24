from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .metrics import clamp
from .models import TradeSignal
from .state import SymbolState


@dataclass(slots=True)
class _TrackedSignal:
    symbol: str
    direction: str
    setup_type: str
    regime: str
    created_at: datetime
    entry: float
    sl: float
    t1: float
    t2: float
    t1_hit: bool = False
    t2_hit: bool = False


class OutcomeTracker:
    _SETUP_PRIORS: dict[str, tuple[float, float, int]] = {
        "BREAKOUT_CONTINUATION": (0.68, 0.38, 34),
        "PULLBACK_CONTINUATION": (0.64, 0.33, 28),
        "FAILED_BREAKOUT_REVERSAL": (0.62, 0.30, 26),
        "ABSORPTION_BUILDUP": (0.58, 0.27, 22),
        "STRUCTURE_COMPRESSION": (0.57, 0.25, 20),
        "EVENT_REACTION": (0.55, 0.24, 18),
    }

    _REGIME_ADJUSTMENTS: dict[str, tuple[float, float]] = {
        "EXPANSION": (0.05, 0.04),
        "TRENDING": (0.04, 0.03),
        "BALANCED": (0.0, 0.0),
        "COMPRESSION": (-0.02, -0.01),
        "CHOPPY": (-0.06, -0.05),
        "DISCOVERY": (-0.03, -0.02),
    }

    def __init__(self) -> None:
        self._open: dict[str, _TrackedSignal] = {}
        self._stats: dict[str, dict[str, float]] = {}

    def register_signal(self, signal: TradeSignal, *, direction: str) -> None:
        if direction not in {"BULLISH", "BEARISH"}:
            return
        symbol = signal.stock.upper()
        current = self._open.get(symbol)
        if current and current.setup_type == signal.setup_type and current.regime == signal.regime and abs(current.entry - signal.entry) < 0.05:
            current.entry = signal.entry
            current.sl = signal.sl
            current.t1 = signal.t1
            current.t2 = signal.t2
            return
        self._open[symbol] = _TrackedSignal(
            symbol=symbol,
            direction=direction,
            setup_type=signal.setup_type,
            regime=signal.regime,
            created_at=datetime.now(),
            entry=signal.entry,
            sl=signal.sl,
            t1=signal.t1,
            t2=signal.t2,
        )

    def update_from_state(self, state: SymbolState) -> None:
        tracked = self._open.get(state.symbol.upper())
        if tracked is None:
            return
        price = state.latest_price()
        now = datetime.now()

        if tracked.direction == "BULLISH":
            if not tracked.t1_hit and price >= tracked.t1:
                tracked.t1_hit = True
            if price >= tracked.t2:
                tracked.t1_hit = True
                tracked.t2_hit = True
                self._finalize(tracked, "t2")
                return
            if price <= tracked.sl:
                outcome = "sl_after_t1" if tracked.t1_hit else "sl"
                self._finalize(tracked, outcome)
                return
        else:
            if not tracked.t1_hit and price <= tracked.t1:
                tracked.t1_hit = True
            if price <= tracked.t2:
                tracked.t1_hit = True
                tracked.t2_hit = True
                self._finalize(tracked, "t2")
                return
            if price >= tracked.sl:
                outcome = "sl_after_t1" if tracked.t1_hit else "sl"
                self._finalize(tracked, outcome)
                return

        if now - tracked.created_at >= timedelta(minutes=45):
            outcome = "timeout_t1" if tracked.t1_hit else "timeout"
            self._finalize(tracked, outcome)

    def snapshot(
        self,
        *,
        setup_type: str,
        regime: str,
        score: int,
        direction: str,
        components: dict[str, int],
        regime_confidence: int = 50,
        market_context: dict[str, object] | None = None,
    ) -> dict[str, object]:
        base_t1, base_t2, prior_weight = self._SETUP_PRIORS.get(setup_type, self._SETUP_PRIORS["EVENT_REACTION"])
        regime_t1, regime_t2 = self._REGIME_ADJUSTMENTS.get(regime, (0.0, 0.0))
        regime_t1 = clamp(base_t1 + regime_t1, 0.35, 0.88)
        regime_t2 = clamp(base_t2 + regime_t2, 0.14, 0.74)

        key = self._key(setup_type, regime, direction)
        stats = self._stats.get(key, {"closed": 0.0, "t1_hits": 0.0, "t2_hits": 0.0})
        closed = int(stats["closed"])
        observed_t1 = int(stats["t1_hits"])
        observed_t2 = int(stats["t2_hits"])

        score_boost = clamp((score - 12.0) * 0.008, -0.04, 0.08)
        structure_boost = clamp((components.get("structure", 0) + components.get("reaction", 0) - 6) * 0.006, -0.03, 0.05)
        volume_boost = clamp((components.get("volume", 0) + components.get("orderflow", 0) - 3) * 0.004, -0.02, 0.03)
        context_boost = clamp(((components.get("market", 0) - 1.0) * 0.01) + ((regime_confidence - 50.0) * 0.0008), -0.03, 0.05)
        market_context = market_context or {}
        breadth_bonus = clamp(float(market_context.get("market_breadth", 0.0)) * 0.004, -0.02, 0.02)
        sector_bonus = clamp(float(market_context.get("sector_strength", 0.0)) * 0.004, -0.02, 0.02)
        live_boost = score_boost + structure_boost + volume_boost + context_boost + breadth_bonus + sector_bonus

        t1_rate = ((regime_t1 * prior_weight) + observed_t1) / (prior_weight + closed) if (prior_weight + closed) > 0 else regime_t1
        t2_rate = ((regime_t2 * prior_weight) + observed_t2) / (prior_weight + closed) if (prior_weight + closed) > 0 else regime_t2
        t1_live = clamp(t1_rate + live_boost, 0.35, 0.92)
        t2_live = clamp(t2_rate + (live_boost * 0.75), 0.12, 0.78)

        return {
            "t1_hit_rate": int(round(t1_live * 100)),
            "t2_hit_rate": int(round(t2_live * 100)),
            "sample_size": int(prior_weight + closed),
            "live_trades": closed,
            "basis": "runtime setup model",
            "regime_adjusted": True,
        }

    def _finalize(self, tracked: _TrackedSignal, outcome: str) -> None:
        key = self._key(tracked.setup_type, tracked.regime, tracked.direction)
        stats = self._stats.setdefault(key, {"closed": 0.0, "t1_hits": 0.0, "t2_hits": 0.0})
        stats["closed"] += 1.0
        if tracked.t1_hit or outcome in {"t2", "timeout_t1", "sl_after_t1"}:
            stats["t1_hits"] += 1.0
        if tracked.t2_hit or outcome == "t2":
            stats["t2_hits"] += 1.0
        self._open.pop(tracked.symbol, None)

    @staticmethod
    def _key(setup_type: str, regime: str, direction: str) -> str:
        return f"{setup_type}|{regime}|{direction}"
