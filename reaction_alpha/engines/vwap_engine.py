from __future__ import annotations

from ..models import ComponentScore
from ..state import SymbolState


class VwapEngine:
    def evaluate(self, state: SymbolState) -> ComponentScore:
        price = state.latest_price()
        tick = state.ticks[-1] if state.ticks else None
        if not tick or price <= 0 or tick.vwap <= 0:
            return ComponentScore(name="vwap", score=0, reasons=["VWAP unavailable"])
        score = 0
        reasons: list[str] = []
        alignment = "neutral"
        if price > tick.vwap * 1.001:
            score += 3
            alignment = "bullish"
            reasons.append("Price trading above VWAP")
        elif price < tick.vwap * 0.999:
            score += 3
            alignment = "bearish"
            reasons.append("Price trading below VWAP")
        else:
            reasons.append("Price hugging VWAP")
        return ComponentScore(
            name="vwap",
            score=score,
            reasons=reasons,
            metadata={"price": round(price, 2), "vwap": round(tick.vwap, 2), "alignment": alignment},
        )
