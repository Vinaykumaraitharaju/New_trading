from __future__ import annotations

from collections import deque

from ..metrics import clamp, mean
from ..models import Candle
from ..state import SymbolState
from .structure_engine import StructureResult


class RegimeEngine:
    def evaluate(self, state: SymbolState, structure: StructureResult) -> dict[str, object]:
        candles = list(state.candles_1m)
        price = state.latest_price()
        atr = max(state.atr(window=14), price * 0.0025, 0.2)
        if len(candles) < 6:
            bias = "BULLISH" if structure.trend == "Bullish" else "BEARISH" if structure.trend == "Bearish" else "NEUTRAL"
            return {
                "label": "DISCOVERY",
                "bias": bias,
                "confidence": 52,
                "description": "Context still building. Let the first structure and volume cycles settle.",
            }

        recent = candles[-12:]
        ranges = [max(candle.high - candle.low, 0.01) for candle in recent]
        closes = [candle.close for candle in recent]
        avg_range = mean(ranges)
        latest_range = ranges[-1]
        net_move = closes[-1] - closes[0]
        travel = sum(ranges)
        directional_efficiency = abs(net_move) / travel if travel > 0 else 0.0
        compression = avg_range <= atr * 0.82
        expansion = latest_range >= avg_range * 1.35
        trend = structure.trend
        tf_bias = self._timeframe_biases(state)
        alignment_count = sum(1 for value in tf_bias.values() if value == trend)
        conflict_count = sum(1 for value in tf_bias.values() if value not in {"Neutral", trend})

        if expansion and directional_efficiency >= 0.34 and trend in {"Bullish", "Bearish"} and alignment_count >= 2:
            label = "EXPANSION"
            description = "Range is expanding with directional intent. Continuation setups deserve extra respect."
        elif trend in {"Bullish", "Bearish"} and directional_efficiency >= 0.27 and alignment_count >= 2:
            label = "TRENDING"
            description = "Structure is directional and pullbacks are likely to be bought or sold."
        elif compression and directional_efficiency <= 0.18:
            label = "COMPRESSION"
            description = "Price is coiling tightly. Wait for clean release rather than predicting early."
        elif directional_efficiency <= 0.16 or conflict_count >= 2:
            label = "CHOPPY"
            description = "Rotation is dominating. Breakouts need stronger confirmation than usual."
        else:
            label = "BALANCED"
            description = "Mixed participation. Favor selective setups with strong structure and order flow."

        if trend == "Bullish":
            bias = "BULLISH"
        elif trend == "Bearish":
            bias = "BEARISH"
        else:
            bias = "NEUTRAL"

        confidence = int(
            round(
                clamp(
                    50.0
                    + (directional_efficiency * 80.0)
                    + (8.0 if expansion else 0.0)
                    + (alignment_count * 3.0)
                    - (5.0 if label == "CHOPPY" else 0.0)
                    - (conflict_count * 2.0),
                    45.0,
                    88.0,
                )
            )
        )
        return {
            "label": label,
            "bias": bias,
            "confidence": confidence,
            "description": description,
            "timeframes": tf_bias,
            "alignment_count": alignment_count,
        }

    def _timeframe_biases(self, state: SymbolState) -> dict[str, str]:
        one_minute = list(state.candles_1m)
        five_minute = list(state.candles_5m)
        fifteen_minute = self._aggregate(one_minute, minutes=15)
        return {
            "1m": self._bias_from_candles(one_minute[-20:]),
            "5m": self._bias_from_candles(five_minute[-16:]),
            "15m": self._bias_from_candles(fifteen_minute[-12:]),
        }

    @staticmethod
    def _bias_from_candles(candles: list[Candle]) -> str:
        if len(candles) < 4:
            return "Neutral"
        closes = [c.close for c in candles]
        net = closes[-1] - closes[0]
        swing = max(max(closes) - min(closes), max(closes[-1] * 0.0025, 0.1))
        if net >= swing * 0.28:
            return "Bullish"
        if net <= -(swing * 0.28):
            return "Bearish"
        return "Neutral"

    @staticmethod
    def _aggregate(rows: list[Candle], *, minutes: int) -> list[Candle]:
        if not rows:
            return []
        aggregated: deque[Candle] = deque()
        for candle in rows:
            bucket_minute = (candle.timestamp.minute // minutes) * minutes
            bucket = candle.timestamp.replace(second=0, microsecond=0, minute=bucket_minute)
            if not aggregated or aggregated[-1].timestamp != bucket:
                aggregated.append(
                    Candle(
                        timestamp=bucket,
                        open=candle.open,
                        high=candle.high,
                        low=candle.low,
                        close=candle.close,
                        volume=candle.volume,
                        vwap=candle.vwap,
                    )
                )
                continue
            current = aggregated[-1]
            current.high = max(current.high, candle.high)
            current.low = min(current.low, candle.low)
            current.close = candle.close
            current.volume += candle.volume
            current.vwap = candle.vwap
        return list(aggregated)
