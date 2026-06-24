from __future__ import annotations

from ..metrics import mean
from ..models import ComponentScore
from ..state import SymbolState


class VolatilityEngine:
    def evaluate(self, state: SymbolState) -> ComponentScore:
        candles = list(state.candles_1m)
        if len(candles) < 10:
            return ComponentScore(name="volatility", score=0, reasons=["ATR history still building"])
        atr = state.atr(window=14)
        recent_ranges = [c.high - c.low for c in candles[-4:]]
        prior_ranges = [c.high - c.low for c in candles[-10:-4]]
        squeeze = mean(prior_ranges) > 0 and mean(recent_ranges[:-1]) <= mean(prior_ranges) * 0.75
        expansion = recent_ranges[-1] >= atr * 1.15
        score = 0
        reasons: list[str] = []
        if squeeze and expansion:
            score += 4
            reasons.append("Volatility squeeze expanded into range expansion")
        elif expansion:
            reasons.append("Range expanded beyond recent ATR")
        else:
            reasons.append("No volatility expansion yet")
        return ComponentScore(
            name="volatility",
            score=score,
            reasons=reasons,
            metadata={"atr": round(atr, 3), "latest_range": round(recent_ranges[-1], 3), "squeeze": squeeze},
        )
