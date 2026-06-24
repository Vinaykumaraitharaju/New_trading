from __future__ import annotations

from ..config import ReactionAlphaConfig
from ..metrics import mean
from ..models import MarketEvent, ReactionResult
from ..state import SymbolState


class ReactionEngine:
    def __init__(self, config: ReactionAlphaConfig) -> None:
        self.config = config

    def evaluate(self, state: SymbolState, event: MarketEvent | None) -> ReactionResult:
        ticks = list(state.ticks)
        if not ticks:
            return ReactionResult("NONE", 0, ["Awaiting ticks"], 0.0, 0.0, 0.0)
        latest = ticks[-1]
        if event is None:
            return ReactionResult("NONE", 0, ["No active market event"], latest.price, latest.price, latest.price)
        window = ticks[-self.config.reaction_window_ticks :]
        prices = [tick.price for tick in window]
        imbalances = [tick.imbalance for tick in window]
        event_price = event.price
        atr = state.atr(window=14)
        drift = latest.price - event_price
        pullback = max(prices) - latest.price if drift >= 0 else latest.price - min(prices)
        compression = (max(prices) - min(prices)) <= max(atr * 0.45, event_price * 0.002)
        avg_imbalance = mean(imbalances)
        reasons: list[str] = []
        classification = "ABSORPTION"
        score = 2
        breakout = event_price
        confirmation = max(prices) if drift >= 0 else min(prices)
        failure = event_price - atr if drift >= 0 else event_price + atr
        if drift >= atr * 0.35 and avg_imbalance >= 0.08 and pullback <= atr * 0.45:
            classification = "CONTINUATION"
            score = 6
            reasons.extend(["Price held above breakout", "Buyers maintained control", "Pullback stayed shallow"])
        elif drift <= -atr * 0.35 and avg_imbalance <= -0.08 and pullback <= atr * 0.45:
            classification = "REVERSAL"
            score = 6
            reasons.extend(["Move failed to hold", "Opposite-side order flow took over", "Sharp rejection after event"])
        elif compression:
            classification = "ABSORPTION"
            score = 4
            reasons.extend(["High participation with limited displacement", "Absorption / accumulation profile"])
        else:
            reasons.append("Reaction still maturing")
        return ReactionResult(
            classification=classification,
            score=score,
            reasons=reasons,
            breakout_level=round(breakout, 2),
            confirmation_level=round(confirmation, 2),
            failure_level=round(failure, 2),
        )
