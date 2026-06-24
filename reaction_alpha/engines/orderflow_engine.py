from __future__ import annotations

from ..metrics import mean
from ..models import ComponentScore
from ..state import SymbolState


class OrderFlowEngine:
    def evaluate(self, state: SymbolState) -> ComponentScore:
        ticks = list(state.ticks)[-36:]
        if len(ticks) < 8:
            return ComponentScore(name="orderflow", score=0, reasons=["Order flow still warming up"])
        imbalances = [tick.imbalance for tick in ticks]
        recent = mean(imbalances[-8:])
        mid = mean(imbalances[-16:-8] or imbalances)
        baseline = mean(imbalances[:-16] or imbalances)
        aggressive_buying = sum(1 for tick in ticks[-10:] if tick.price >= tick.ask and tick.ask > 0)
        aggressive_selling = sum(1 for tick in ticks[-10:] if tick.price <= tick.bid and tick.bid > 0)
        spread_now = mean([tick.spread for tick in ticks[-8:]])
        spread_base = mean([tick.spread for tick in ticks[:-8] or ticks])
        persistent_bid = recent > 0.18 and mid > 0.1
        persistent_ask = recent < -0.18 and mid < -0.1
        score = 0
        reasons: list[str] = []
        bias = "neutral"
        if persistent_bid or recent - baseline >= 0.18 or recent >= 0.25:
            score += 3 if persistent_bid else 2
            bias = "bullish"
            reasons.append("Bid-side pressure is persisting across multiple tick windows" if persistent_bid else "Bid-side imbalance shifted higher")
        elif persistent_ask or baseline - recent >= 0.18 or recent <= -0.25:
            score += 3 if persistent_ask else 2
            bias = "bearish"
            reasons.append("Ask-side pressure is persisting across multiple tick windows" if persistent_ask else "Ask-side imbalance shifted higher")
        if aggressive_buying >= 6:
            score += 1
            reasons.append("Aggressive buyers are lifting offers")
        elif aggressive_selling >= 6:
            score += 1
            reasons.append("Aggressive sellers are hitting bids")
        if spread_now <= max(spread_base * 0.92, 0.02) and bias != "neutral":
            reasons.append("Spread is staying controlled while pressure persists")
        return ComponentScore(
            name="orderflow",
            score=score,
            reasons=reasons or ["Order flow balanced"],
            metadata={
                "imbalance": round(recent, 3),
                "mid_window": round(mid, 3),
                "baseline": round(baseline, 3),
                "bias": bias,
                "persistent": persistent_bid or persistent_ask,
            },
        )
