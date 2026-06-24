from __future__ import annotations

from ..models import ComponentScore
from ..state import SymbolState


class SupportResistanceEngine:
    def evaluate(self, state: SymbolState) -> ComponentScore:
        price = state.latest_price()
        if price <= 0:
            return ComponentScore(name="sr", score=0, reasons=["Price unavailable"])
        intraday_high = state.day_high or price
        intraday_low = state.day_low or price
        cluster = state.volume_cluster_price()
        score = 0
        reasons: list[str] = []
        zone = "neutral"
        if price >= intraday_high * 0.999 and price >= cluster:
            score += 4
            zone = "breakout"
            reasons.append("Breakout holding near intraday high")
        elif price <= intraday_low * 1.001 and price <= cluster:
            score += 4
            zone = "breakdown"
            reasons.append("Breakdown holding near intraday low")
        elif abs(price - cluster) / max(price, 0.01) <= 0.003:
            score += 3
            zone = "retest"
            reasons.append("Retest at high-volume cluster")
        if state.previous_day_high and price > state.previous_day_high:
            reasons.append("Trading above previous day high")
        if state.previous_day_low and price < state.previous_day_low:
            reasons.append("Trading below previous day low")
        return ComponentScore(
            name="sr",
            score=score,
            reasons=reasons or ["No critical S/R interaction"],
            metadata={"zone": zone, "intraday_high": round(intraday_high, 2), "intraday_low": round(intraday_low, 2), "cluster": round(cluster, 2)},
        )
