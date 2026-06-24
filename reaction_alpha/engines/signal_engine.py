from __future__ import annotations

from datetime import datetime

from ..metrics import confidence_from_score
from ..models import TradeSignal
from ..state import SymbolState
from ..trade_levels import build_trade_levels, resolve_trade_state
from .scoring_engine import UnifiedScore
from .reaction_engine import ReactionResult
from .structure_engine import StructureResult


class SignalEngine:
    def build(
        self,
        *,
        config,
        state: SymbolState,
        event_name: str,
        reaction: ReactionResult,
        structure: StructureResult,
        score: UnifiedScore,
        setup_type: str,
        regime: str,
        probability: dict[str, object],
        direction: str,
        setup_profile: str = "neutral",
    ) -> TradeSignal | None:
        if score.label == "IGNORE":
            return None
        price = state.latest_price()
        atr = state.atr(window=14)
        levels = build_trade_levels(
            config=config,
            state=state,
            reaction=reaction,
            structure=structure,
            direction=direction,
            setup_type=setup_type,
            regime=regime,
            setup_profile=setup_profile,
        )
        if levels.target1_points < config.minimum_profit_points:
            return None
        if direction == "BULLISH":
            signal = f"{score.label} BULLISH" if reaction.classification == "CONTINUATION" else "REVERSAL ALERT"
        elif direction == "BEARISH":
            signal = f"{score.label} BEARISH" if reaction.classification != "ABSORPTION" else "ABSORPTION ZONE"
        else:
            signal = "ABSORPTION ZONE"
        trade_state = resolve_trade_state(
            price=price,
            entry=levels.entry,
            t1=levels.t1,
            score=score.total,
            strong_threshold=config.strong_threshold,
            direction=direction,
            setup_profile=setup_profile,
        )
        probability_t1 = float(probability.get("t1_hit_rate", 0) or 0)
        confidence = (confidence_from_score(score.total) * 0.45) + (probability_t1 * 0.55)
        return TradeSignal(
            stock=state.symbol,
            event=event_name,
            reaction=reaction.classification,
            signal=signal,
            direction=direction,
            setup_type=setup_type,
            regime=regime,
            trend=structure.structure_label,
            score=score.total,
            entry=levels.entry,
            sl=levels.sl,
            t1=levels.t1,
            t2=levels.t2,
            expected_move=levels.expected_move,
            confidence=f"{round(confidence):.0f}%",
            reason=list(dict.fromkeys(reason for reason in score.reasons if reason))[:6],
            timestamp=datetime.now().isoformat(timespec="seconds"),
            components=score.components,
            probability=probability,
            raw_confidence=confidence,
            state=trade_state,
        )
