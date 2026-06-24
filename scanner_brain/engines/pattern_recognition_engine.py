from __future__ import annotations

from scanner_brain.config.pattern_profiles import PatternProfile
from scanner_brain.core.enums import Bias, Side
from scanner_brain.core.models import MarketRegime, PatternAssessment, SectorAssessment, StockSnapshot, TechnicalAssessment


class PatternRecognitionEngine:
    def __init__(self, profile: PatternProfile) -> None:
        self.profile = profile

    def evaluate(
        self,
        stock: StockSnapshot,
        technical: TechnicalAssessment,
        market: MarketRegime,
        sector: SectorAssessment | None,
    ) -> PatternAssessment:
        body = abs(stock.ltp - stock.open)
        rng = stock.day_range
        upper_wick = max(stock.high - max(stock.open, stock.ltp), 0.0)
        lower_wick = max(min(stock.open, stock.ltp) - stock.low, 0.0)
        body_ratio = body / rng
        detected: list[str] = []
        reasons: list[str] = []
        contradictions: list[str] = []
        adjustment = 0.0
        bias = Bias.NEUTRAL

        if body_ratio <= self.profile.doji_body_ratio:
            detected.append("doji")
            adjustment -= 3.0 if "key level context favorable" in technical.passed else 1.0
            reasons.append("Doji shows hesitation near current setup")
            contradictions.append("hesitation candle")

        if body_ratio >= self.profile.marubozu_body_ratio:
            name = "bullish marubozu" if stock.ltp >= stock.open else "bearish marubozu"
            detected.append(name)
            candle_bias = Bias.BULLISH if stock.ltp >= stock.open else Bias.BEARISH
            bias = candle_bias
            adjustment += self._contextual_points(candle_bias, technical, market, sector)
            reasons.append(f"{name.title()} confirms directional pressure")

        if lower_wick / rng >= self.profile.hammer_wick_ratio and body_ratio <= 0.45:
            detected.append("hammer")
            bias = Bias.BULLISH
            points = self._contextual_points(Bias.BULLISH, technical, market, sector)
            adjustment += points
            reasons.append("Hammer-style rejection from lower levels")

        if upper_wick / rng >= self.profile.shooting_star_wick_ratio and body_ratio <= 0.45:
            detected.append("shooting star")
            bias = Bias.BEARISH
            points = self._contextual_points(Bias.BEARISH, technical, market, sector)
            adjustment += points
            reasons.append("Shooting-star rejection near upper levels")

        if stock.high > max(stock.open, stock.prev_close, stock.ltp) and stock.low < min(stock.open, stock.prev_close, stock.ltp):
            detected.append("outside bar context")
            adjustment += self.profile.weak_pattern_weight if abs(stock.change_pct) >= 0.4 else 0.0

        if not detected:
            return PatternAssessment([], Bias.NEUTRAL, 0.0, ["No strong pattern context in quote-only scan"])

        if technical.side == Side.LONG and bias == Bias.BEARISH:
            adjustment += self.profile.conflict_weight
            contradictions.append("bearish pattern conflicts with long setup")
        elif technical.side == Side.SHORT and bias == Bias.BULLISH:
            adjustment += self.profile.conflict_weight
            contradictions.append("bullish pattern conflicts with short setup")

        return PatternAssessment(detected, bias, max(-10.0, min(10.0, adjustment)), reasons, contradictions)

    def _contextual_points(
        self,
        pattern_bias: Bias,
        technical: TechnicalAssessment,
        market: MarketRegime,
        sector: SectorAssessment | None,
    ) -> float:
        side_bias = Bias.BULLISH if technical.side == Side.LONG else Bias.BEARISH
        if pattern_bias != side_bias:
            return self.profile.conflict_weight
        points = self.profile.base_weight
        if market.bias in {pattern_bias, Bias.NEUTRAL}:
            points += 1.5
        if sector is None or sector.bias in {pattern_bias, Bias.NEUTRAL}:
            points += 1.5
        if "VWAP/open proxy supportive" in technical.passed or "key level context favorable" in technical.passed:
            points += 2.0
        return min(self.profile.contextual_weight, points)
