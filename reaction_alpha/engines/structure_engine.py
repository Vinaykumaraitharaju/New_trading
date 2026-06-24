from __future__ import annotations

from ..models import StructureResult
from ..state import SymbolState


class MarketStructureEngine:
    def evaluate(self, state: SymbolState) -> StructureResult:
        candles = list(state.candles_1m)
        if len(candles) < 4:
            ticks = list(state.ticks)
            if len(ticks) >= 10:
                prices = [tick.price for tick in ticks[-10:]]
                bullish = prices[-1] > prices[-4] > prices[-7]
                bearish = prices[-1] < prices[-4] < prices[-7]
                if bullish:
                    return StructureResult(
                        trend="Bullish",
                        structure_label="HH-HL",
                        score=4,
                        bos=False,
                        choch=False,
                        swing_high=max(prices),
                        swing_low=min(prices),
                        reasons=["Tick structure shows higher highs and higher lows"],
                    )
                if bearish:
                    return StructureResult(
                        trend="Bearish",
                        structure_label="LH-LL",
                        score=4,
                        bos=False,
                        choch=False,
                        swing_high=max(prices),
                        swing_low=min(prices),
                        reasons=["Tick structure shows lower highs and lower lows"],
                    )
        if len(candles) < 8:
            return StructureResult(
                trend="RANGE",
                structure_label="UNDEFINED",
                score=0,
                bos=False,
                choch=False,
                swing_high=state.day_high or state.latest_price(),
                swing_low=state.day_low or state.latest_price(),
                reasons=["Market structure still building"],
            )
        recent = candles[-8:]
        highs = [c.high for c in recent]
        lows = [c.low for c in recent]
        closes = [c.close for c in recent]
        swing_high = max(highs[:-1])
        swing_low = min(lows[:-1])
        score = 0
        reasons: list[str] = []
        bos = False
        choch = False
        structure = "RANGE"
        trend = "Range"
        if closes[-1] > closes[-3] > closes[-5] and lows[-1] > lows[-3] > lows[-5]:
            trend = "Bullish"
            structure = "HH-HL"
            score += 4
            reasons.append("Higher highs and higher lows")
            if closes[-1] > swing_high:
                bos = True
                score += 5
                reasons.append("Bullish break of structure")
        elif closes[-1] < closes[-3] < closes[-5] and highs[-1] < highs[-3] < highs[-5]:
            trend = "Bearish"
            structure = "LH-LL"
            score += 4
            reasons.append("Lower highs and lower lows")
            if closes[-1] < swing_low:
                bos = True
                score += 5
                reasons.append("Bearish break of structure")
        elif closes[-1] > closes[-2] and closes[-2] < closes[-4]:
            choch = True
            reasons.append("Potential bullish CHOCH")
        elif closes[-1] < closes[-2] and closes[-2] > closes[-4]:
            choch = True
            reasons.append("Potential bearish CHOCH")
        return StructureResult(
            trend=trend,
            structure_label=structure,
            score=score,
            bos=bos,
            choch=choch,
            swing_high=swing_high,
            swing_low=swing_low,
            reasons=reasons or ["Range structure"],
        )
