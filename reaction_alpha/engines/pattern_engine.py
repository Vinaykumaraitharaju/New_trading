from __future__ import annotations

from ..metrics import mean
from ..models import Candle, ComponentScore
from ..state import SymbolState


class PatternEngine:
    def evaluate(self, state: SymbolState) -> ComponentScore:
        candles = list(state.candles_1m)
        if len(candles) < 10:
            return ComponentScore(
                name="pattern",
                score=0,
                reasons=["Pattern still forming"],
                metadata={"pattern": "forming", "patterns": [], "label": "Pattern Still Forming", "bias": "neutral"},
            )

        recent = candles[-12:]
        last = recent[-1]
        prev = recent[-2]
        prev2 = recent[-3]
        ranges = [max(c.high - c.low, 0.01) for c in recent]
        avg_range = max(mean(ranges[:-1]), 0.01)
        avg_volume = max(mean([c.volume for c in recent[:-1]]), 1.0)
        recent_high = max(c.high for c in recent[:-2])
        recent_low = min(c.low for c in recent[:-2])
        score = 0
        reasons: list[str] = []
        patterns: list[str] = []
        bias = "neutral"

        shock = self._shock_breakdown_continuation(last, prev, recent, avg_range, avg_volume)
        if shock:
            score = max(score, 6)
            patterns.append("shock_breakdown_continuation")
            reasons.append(shock[0])
            bias = shock[1]

        panic = self._panic_bounce_failure(last, recent, avg_range, avg_volume)
        if panic:
            score = max(score, 6)
            patterns.append("panic_bounce_failure")
            reasons.append(panic[0])
            bias = panic[1]

        flush = self._flush_exhaustion_reversal(last, recent, avg_range, avg_volume)
        if flush:
            score = max(score, 6)
            patterns.append("flush_exhaustion_reversal")
            reasons.append(flush[0])
            bias = flush[1]

        breakout = self._breakout_confirmation(last, recent_high, recent_low, avg_range, avg_volume)
        if breakout:
            score += 5
            patterns.append("breakout_confirmation")
            reasons.append(breakout[0])
            bias = breakout[1]

        rejection = self._failed_breakout_rejection(last, prev, recent_high, recent_low, avg_range, avg_volume)
        if rejection:
            score = max(score, 5)
            patterns.append("failed_breakout_rejection")
            reasons.append(rejection[0])
            bias = rejection[1]

        continuation = self._pullback_continuation(last, recent, avg_range, avg_volume)
        if continuation:
            score = max(score, 4)
            patterns.append("pullback_continuation")
            reasons.append(continuation[0])
            bias = continuation[1]

        expansion = self._inside_bar_expansion(last, prev, prev2, avg_range, avg_volume)
        if expansion:
            score = max(score, 4)
            patterns.append("inside_bar_expansion")
            reasons.append(expansion[0])
            bias = expansion[1]

        exhaustion = self._exhaustion_reversal(last, recent, state, avg_range, avg_volume)
        if exhaustion:
            score = max(score, 5)
            patterns.append("exhaustion_reversal")
            reasons.append(exhaustion[0])
            bias = exhaustion[1]

        if not reasons:
            compression = self._compression_context(recent, avg_range)
            if compression:
                score = max(score, 3)
                patterns.append("compression")
                reasons.append("Inside compression still building before directional release")

        primary_pattern = patterns[0] if patterns else "none"
        return ComponentScore(
            name="pattern",
            score=score,
            reasons=reasons or ["No confirmed pattern"],
            metadata={
                "pattern": primary_pattern,
                "patterns": patterns,
                "label": self._pattern_label(primary_pattern),
                "bias": bias,
            },
        )

    @staticmethod
    def _body_ratio(candle: Candle) -> float:
        candle_range = max(candle.high - candle.low, 0.01)
        return abs(candle.close - candle.open) / candle_range

    def _shock_breakdown_continuation(
        self,
        last: Candle,
        prev: Candle,
        recent: list[Candle],
        avg_range: float,
        avg_volume: float,
    ) -> tuple[str, str] | None:
        last_range = max(last.high - last.low, 0.01)
        prev_range = max(prev.high - prev.low, 0.01)
        last_body = self._body_ratio(last)
        prev_body = self._body_ratio(prev)

        last_shock_bearish = (
            last.close < last.open
            and last_range >= avg_range * 2.2
            and last.volume >= avg_volume * 1.75
            and last_body >= 0.68
            and (last.close - last.low) <= last_range * 0.22
        )
        if last_shock_bearish:
            return ("Shock breakdown candle expanded lower with panic participation", "bearish")

        last_shock_bullish = (
            last.close > last.open
            and last_range >= avg_range * 2.2
            and last.volume >= avg_volume * 1.75
            and last_body >= 0.68
            and (last.high - last.close) <= last_range * 0.22
        )
        if last_shock_bullish:
            return ("Shock breakout candle expanded higher with aggressive participation", "bullish")

        prev_shock_bearish = (
            prev.close < prev.open
            and prev_range >= avg_range * 2.0
            and prev.volume >= avg_volume * 1.6
            and prev_body >= 0.64
        )
        if (
            prev_shock_bearish
            and last.close < last.open
            and last.close <= prev.close + (prev_range * 0.2)
            and last.high <= prev.open - (prev_range * 0.12)
            and last.volume >= avg_volume * 1.05
        ):
            return ("Shock breakdown held and follow-through selling stayed in control", "bearish")

        prev_shock_bullish = (
            prev.close > prev.open
            and prev_range >= avg_range * 2.0
            and prev.volume >= avg_volume * 1.6
            and prev_body >= 0.64
        )
        if (
            prev_shock_bullish
            and last.close > last.open
            and last.close >= prev.close - (prev_range * 0.2)
            and last.low >= prev.open + (prev_range * 0.12)
            and last.volume >= avg_volume * 1.05
        ):
            return ("Shock breakout held and follow-through buying stayed in control", "bullish")

        return None

    def _breakout_confirmation(
        self,
        last: Candle,
        recent_high: float,
        recent_low: float,
        avg_range: float,
        avg_volume: float,
    ) -> tuple[str, str] | None:
        body_ratio = self._body_ratio(last)
        bullish_break = last.close > recent_high and last.close > last.open
        bearish_break = last.close < recent_low and last.close < last.open
        expansion = (last.high - last.low) >= avg_range * 1.15
        participation = last.volume >= avg_volume * 1.2
        if not ((bullish_break or bearish_break) and expansion and participation and body_ratio >= 0.58):
            return None
        if bullish_break:
            return ("Breakout confirmation candle closed above resistance with range and participation", "bullish")
        return ("Breakout confirmation candle closed below support with range and participation", "bearish")

    def _failed_breakout_rejection(
        self,
        last: Candle,
        prev: Candle,
        recent_high: float,
        recent_low: float,
        avg_range: float,
        avg_volume: float,
    ) -> tuple[str, str] | None:
        upper_wick = last.high - max(last.open, last.close)
        lower_wick = min(last.open, last.close) - last.low
        body_ratio = self._body_ratio(last)
        if (
            prev.high > recent_high
            and last.close < recent_high
            and upper_wick >= avg_range * 0.45
            and last.volume >= avg_volume * 1.1
            and body_ratio <= 0.45
        ):
            return ("Failed breakout rejection near resistance", "bearish")
        if (
            prev.low < recent_low
            and last.close > recent_low
            and lower_wick >= avg_range * 0.45
            and last.volume >= avg_volume * 1.1
            and body_ratio <= 0.45
        ):
            return ("Failed breakdown rejection near support", "bullish")
        return None

    def _panic_bounce_failure(
        self,
        last: Candle,
        recent: list[Candle],
        avg_range: float,
        avg_volume: float,
    ) -> tuple[str, str] | None:
        shock_bearish = self._recent_shock_reference(recent, avg_range, avg_volume, "bearish")
        if shock_bearish is not None:
            shock = recent[shock_bearish]
            after = recent[shock_bearish + 1 :]
            if len(after) >= 2:
                shock_range = max(shock.high - shock.low, 0.01)
                bounce_high = max(c.high for c in after[:-1]) if len(after) > 1 else after[0].high
                bounce_floor = min(c.close for c in after[:-1]) if len(after) > 1 else after[0].close
                reclaim_cap = shock.close + ((shock.open - shock.close) * 0.45)
                if (
                    any(c.close > c.open for c in after[:-1])
                    and bounce_high <= reclaim_cap
                    and last.close < last.open
                    and last.close <= bounce_floor
                    and last.volume >= avg_volume * 1.05
                ):
                    return ("Panic bounce failed below the shock breakdown zone", "bearish")

        shock_bullish = self._recent_shock_reference(recent, avg_range, avg_volume, "bullish")
        if shock_bullish is not None:
            shock = recent[shock_bullish]
            after = recent[shock_bullish + 1 :]
            if len(after) >= 2:
                shock_range = max(shock.high - shock.low, 0.01)
                bounce_low = min(c.low for c in after[:-1]) if len(after) > 1 else after[0].low
                bounce_cap = max(c.close for c in after[:-1]) if len(after) > 1 else after[0].close
                reclaim_floor = shock.close - ((shock.close - shock.open) * 0.45)
                if (
                    any(c.close < c.open for c in after[:-1])
                    and bounce_low >= reclaim_floor
                    and last.close > last.open
                    and last.close >= bounce_cap
                    and last.volume >= avg_volume * 1.05
                ):
                    return ("Panic pullback failed below the shock breakout zone", "bullish")

        return None

    def _pullback_continuation(
        self,
        last: Candle,
        recent: list[Candle],
        avg_range: float,
        avg_volume: float,
    ) -> tuple[str, str] | None:
        closes = [c.close for c in recent]
        bullish_context = closes[-6] < closes[-5] < closes[-3]
        bearish_context = closes[-6] > closes[-5] > closes[-3]
        mid_pullback = recent[-4:-1]
        pullback_low = min(c.low for c in mid_pullback)
        pullback_high = max(c.high for c in mid_pullback)
        if (
            bullish_context
            and pullback_low >= min(c.low for c in recent[-8:-4])
            and last.close > last.open
            and last.close > max(c.high for c in recent[-3:-1])
            and last.low <= (last.vwap or last.close) * 1.002
            and last.volume >= avg_volume * 1.05
            and (last.high - last.low) >= avg_range * 0.9
        ):
            return ("Pullback continuation candle reclaimed the short-term trend", "bullish")
        if (
            bearish_context
            and pullback_high <= max(c.high for c in recent[-8:-4])
            and last.close < last.open
            and last.close < min(c.low for c in recent[-3:-1])
            and last.high >= (last.vwap or last.close) * 0.998
            and last.volume >= avg_volume * 1.05
            and (last.high - last.low) >= avg_range * 0.9
        ):
            return ("Pullback continuation candle resumed downside pressure", "bearish")
        return None

    def _inside_bar_expansion(
        self,
        last: Candle,
        prev: Candle,
        prev2: Candle,
        avg_range: float,
        avg_volume: float,
    ) -> tuple[str, str] | None:
        inside_bar = prev.high <= prev2.high and prev.low >= prev2.low
        if not inside_bar:
            return None
        if (
            last.close > prev.high
            and last.close > last.open
            and (last.high - last.low) >= avg_range * 1.05
            and last.volume >= avg_volume * 1.15
        ):
            return ("Inside-bar expansion released to the upside", "bullish")
        if (
            last.close < prev.low
            and last.close < last.open
            and (last.high - last.low) >= avg_range * 1.05
            and last.volume >= avg_volume * 1.15
        ):
            return ("Inside-bar expansion released to the downside", "bearish")
        return None

    def _exhaustion_reversal(
        self,
        last: Candle,
        recent: list[Candle],
        state: SymbolState,
        avg_range: float,
        avg_volume: float,
    ) -> tuple[str, str] | None:
        upper_wick = last.high - max(last.open, last.close)
        lower_wick = min(last.open, last.close) - last.low
        near_day_high = state.day_high > 0 and (state.day_high - last.high) <= avg_range * 0.25
        near_day_low = state.day_low > 0 and (last.low - state.day_low) <= avg_range * 0.25
        near_prev_high = state.previous_day_high > 0 and abs(last.high - state.previous_day_high) <= avg_range * 0.35
        near_prev_low = state.previous_day_low > 0 and abs(last.low - state.previous_day_low) <= avg_range * 0.35
        participation = last.volume >= avg_volume * 1.25
        if (
            (near_day_high or near_prev_high)
            and last.close < last.open
            and upper_wick >= avg_range * 0.55
            and participation
        ):
            return ("Exhaustion reversal formed near a key high", "bearish")
        if (
            (near_day_low or near_prev_low)
            and last.close > last.open
            and lower_wick >= avg_range * 0.55
            and participation
        ):
            return ("Exhaustion reversal formed near a key low", "bullish")
        return None

    def _flush_exhaustion_reversal(
        self,
        last: Candle,
        recent: list[Candle],
        avg_range: float,
        avg_volume: float,
    ) -> tuple[str, str] | None:
        lower_wick = min(last.open, last.close) - last.low
        upper_wick = last.high - max(last.open, last.close)

        shock_bearish = self._recent_shock_reference(recent, avg_range, avg_volume, "bearish")
        if shock_bearish is not None:
            shock = recent[shock_bearish]
            shock_range = max(shock.high - shock.low, 0.01)
            shock_mid = shock.low + (shock_range * 0.5)
            if (
                last.close > last.open
                and lower_wick >= avg_range * 0.6
                and last.close >= shock_mid
                and last.volume >= avg_volume * 1.15
            ):
                return ("Flush exhaustion reversed after a panic sell-off", "bullish")

        shock_bullish = self._recent_shock_reference(recent, avg_range, avg_volume, "bullish")
        if shock_bullish is not None:
            shock = recent[shock_bullish]
            shock_range = max(shock.high - shock.low, 0.01)
            shock_mid = shock.high - (shock_range * 0.5)
            if (
                last.close < last.open
                and upper_wick >= avg_range * 0.6
                and last.close <= shock_mid
                and last.volume >= avg_volume * 1.15
            ):
                return ("Flush exhaustion reversed after a panic squeeze higher", "bearish")

        return None

    def _recent_shock_reference(
        self,
        recent: list[Candle],
        avg_range: float,
        avg_volume: float,
        side: str,
    ) -> int | None:
        start = max(len(recent) - 5, 0)
        end = max(len(recent) - 1, 0)
        for index in range(start, end):
            candle = recent[index]
            candle_range = max(candle.high - candle.low, 0.01)
            body_ratio = self._body_ratio(candle)
            if side == "bearish":
                if (
                    candle.close < candle.open
                    and candle_range >= avg_range * 1.95
                    and candle.volume >= avg_volume * 1.55
                    and body_ratio >= 0.62
                ):
                    return index
            else:
                if (
                    candle.close > candle.open
                    and candle_range >= avg_range * 1.95
                    and candle.volume >= avg_volume * 1.55
                    and body_ratio >= 0.62
                ):
                    return index
        return None

    @staticmethod
    def _compression_context(recent: list[Candle], avg_range: float) -> bool:
        tail = recent[-4:]
        tail_range = max(c.high for c in tail) - min(c.low for c in tail)
        prior_range = max(c.high for c in recent[:-4]) - min(c.low for c in recent[:-4])
        return tail_range > 0 and prior_range > 0 and tail_range <= max(prior_range * 0.45, avg_range * 1.8)

    @staticmethod
    def _pattern_label(pattern_name: str) -> str:
        labels = {
            "shock_breakdown_continuation": "Shock Breakdown Continuation",
            "panic_bounce_failure": "Panic Bounce Failure",
            "flush_exhaustion_reversal": "Flush Exhaustion Reversal",
            "breakout_confirmation": "Breakout Confirmation",
            "failed_breakout_rejection": "Failed Breakout Rejection",
            "pullback_continuation": "Pullback Continuation",
            "inside_bar_expansion": "Inside-Bar Expansion",
            "exhaustion_reversal": "Exhaustion Reversal",
            "compression": "Compression Build",
            "forming": "Pattern Still Forming",
            "none": "No Confirmed Pattern",
        }
        return labels.get(pattern_name, "No Confirmed Pattern")
