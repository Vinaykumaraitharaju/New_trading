from __future__ import annotations

from scanner_brain.config.scoring_profiles import ScoringProfile
from scanner_brain.core.enums import Bias, Decision, EntryType, Grade, Side
from scanner_brain.core.models import FinalAssessment, MarketRegime, NewsAssessment, PatternAssessment, SectorAssessment, StockSnapshot, TechnicalAssessment


class AlignmentScoringEngine:
    def __init__(self, profile: ScoringProfile) -> None:
        self.profile = profile

    def grade(
        self,
        stock: StockSnapshot,
        market: MarketRegime,
        sector: SectorAssessment | None,
        technical: TechnicalAssessment,
        pattern: PatternAssessment,
        news: NewsAssessment,
    ) -> FinalAssessment:
        side_bias = Bias.BULLISH if technical.side == Side.LONG else Bias.BEARISH
        passed = list(technical.passed)
        missing = list(technical.missing)
        failed = list(technical.failed)
        warnings = list(technical.contradictions) + list(pattern.contradictions)
        reasons = list(technical.reasons)
        reasons.append(f"Entry type: {technical.entry_type.value} - {technical.entry_reason}")

        market_points = self.profile.weights.market if market.bias in {side_bias, Bias.NEUTRAL} else -self.profile.weights.market
        if market.bias == side_bias:
            passed.append("market aligned")
            reasons.extend(market.reasons[:2])
        elif market.bias == Bias.NEUTRAL:
            missing.append("market mixed")
        else:
            failed.append("market against setup")
            warnings.append("broader market contradicts setup")

        sector_points = 0.0
        if sector is None:
            missing.append("sector data limited")
        elif sector.bias == side_bias:
            sector_points = self.profile.weights.sector
            passed.append("sector aligned")
            reasons.extend(sector.reasons[:2])
        elif sector.bias == Bias.NEUTRAL:
            sector_points = 2.0
            missing.append("sector mixed")
        else:
            sector_points = -self.profile.weights.sector * 0.75
            failed.append("sector against setup")
            warnings.append("sector is not aligned")

        technical_points = (technical.score / 100.0) * self.profile.weights.technical
        pattern_points = pattern.score_adjustment
        news_points = news.score_adjustment
        score = 35.0 + market_points + sector_points + technical_points + pattern_points + news_points
        if technical.entry_type == EntryType.IDEAL:
            score += 8.0
            passed.append("entry quality ideal")
        elif technical.entry_type == EntryType.ACCEPTABLE:
            score += 3.0
            passed.append("entry quality acceptable")
        elif technical.entry_type == EntryType.RISKY:
            score -= 10.0
            missing.append("entry quality risky")
        else:
            score -= 24.0
            failed.append("entry quality is chasing")
            warnings.append("breakout is too extended from VWAP")
        score -= len(failed) * 4.0 + max(0, len(missing) - 3) * 1.5 + len(warnings) * 2.0
        score = max(0.0, min(100.0, score))

        entry_low, entry_high, stop, target1, target2, rr = self._trade_plan(stock, technical)
        if rr < self.profile.min_rr_for_selection:
            failed.append("poor risk reward for intraday execution")
            warnings.append("risk reward is too weak for a top-quality setup")
            score = max(0.0, score - 8.0)

        grade = self._grade(score, technical.entry_type, missing, failed, warnings)
        decision = Decision.SELECTED if grade in {Grade.A_PLUS, Grade.A, Grade.B} and score >= self.profile.min_select_score else Decision.WATCHLIST
        if grade == Grade.REJECT or technical.entry_type == EntryType.CHASING or len(failed) >= 4 or len(warnings) >= 4:
            decision = Decision.REJECTED

        if pattern.detected:
            reasons.append("Pattern context: " + ", ".join(pattern.detected))
        confidence_note = self._confidence_note(grade, technical.entry_type, missing, failed, warnings)
        invalidation = self._invalidation(technical.side, stop, stock.vwap_proxy)
        return FinalAssessment(
            symbol=stock.symbol,
            side=technical.side,
            final_score=round(score, 1),
            grade=grade,
            decision=decision,
            setup_type=technical.setup_type,
            entry_type=technical.entry_type,
            entry_reason=technical.entry_reason,
            passed=passed,
            missing=missing,
            failed=failed,
            warnings=warnings,
            reasons=reasons[:10],
            detected_patterns=pattern.detected,
            confidence_note=confidence_note,
            entry_low=entry_low,
            entry_high=entry_high,
            stop_loss=stop,
            target1=target1,
            target2=target2,
            rr=rr,
            invalidation_note=invalidation,
            vwap_distance_pct=technical.vwap_distance_pct,
            vwap_distance_atr=technical.vwap_distance_atr,
        )

    def _grade(self, score: float, entry_type: EntryType, missing: list[str], failed: list[str], warnings: list[str]) -> Grade:
        g = self.profile.grades
        if entry_type == EntryType.CHASING or any("poor risk reward" in item.lower() for item in failed):
            return Grade.REJECT
        if entry_type == EntryType.IDEAL and score >= g.a_plus and len(missing) <= g.max_missing_for_a_plus and not failed:
            return Grade.A_PLUS
        if entry_type in {EntryType.IDEAL, EntryType.ACCEPTABLE} and score >= g.a and len(failed) <= g.max_failed_for_a:
            return Grade.A
        if entry_type != EntryType.CHASING and score >= g.b and len(warnings) <= 3:
            return Grade.B
        if score >= g.c:
            return Grade.C
        return Grade.REJECT

    @staticmethod
    def _trade_plan(stock: StockSnapshot, technical: TechnicalAssessment) -> tuple[float, float, float, float, float, float]:
        plan_unit = AlignmentScoringEngine._intraday_plan_unit(stock, technical)
        entry_span = max(plan_unit * 0.25, stock.ltp * 0.001, 0.05)
        if technical.side == Side.LONG:
            trigger = min(max(technical.trigger, stock.ltp), stock.ltp + plan_unit * 0.45)
            entry_high = max(stock.ltp, trigger)
            entry_low = min(stock.ltp, entry_high - entry_span)
            stop_floor = entry_low - plan_unit * 0.85
            stop = technical.support if stop_floor < technical.support < entry_low else stop_floor
            risk = max(entry_high - stop, plan_unit * 0.55)
            target1 = entry_high + min(max(risk * 1.10, plan_unit * 0.75), plan_unit * 1.15)
            target2 = entry_high + min(max(risk * 1.80, plan_unit * 1.35), plan_unit * 2.00)
        else:
            trigger = max(min(technical.trigger, stock.ltp), stock.ltp - plan_unit * 0.45)
            entry_low = min(stock.ltp, trigger)
            entry_high = max(stock.ltp, entry_low + entry_span)
            stop_ceiling = entry_high + plan_unit * 0.85
            stop = technical.resistance if entry_high < technical.resistance < stop_ceiling else stop_ceiling
            risk = max(stop - entry_low, plan_unit * 0.55)
            target1 = max(entry_low - min(max(risk * 1.10, plan_unit * 0.75), plan_unit * 1.15), 0.01)
            target2 = max(entry_low - min(max(risk * 1.80, plan_unit * 1.35), plan_unit * 2.00), 0.01)
        rr = abs(target2 - ((entry_low + entry_high) / 2.0)) / max(risk, 0.01)
        return tuple(round(v, 2) for v in [entry_low, entry_high, stop, target1, target2, rr])  # type: ignore[return-value]

    @staticmethod
    def _intraday_plan_unit(stock: StockSnapshot, technical: TechnicalAssessment) -> float:
        """Use a capped range unit so intraday plans do not project multi-day targets."""
        ltp = max(stock.ltp, 0.01)
        floor = ltp * 0.006
        cap = ltp * 0.018
        observed = max(min(stock.day_range * 0.45, cap), floor)
        atr = max(min(technical.atr_proxy, cap), floor)
        return max(min(observed, atr, cap), floor, 0.05)

    @staticmethod
    def _confidence_note(grade: Grade, entry_type: EntryType, missing: list[str], failed: list[str], warnings: list[str]) -> str:
        if grade == Grade.A_PLUS:
            return "Almost all key validations align; only normal intraday execution risk remains."
        if grade == Grade.A:
            return "Strong setup with one or two validations not perfect."
        if grade == Grade.B and entry_type == EntryType.RISKY:
            return "Directional setup exists, but entry is stretched from VWAP. Wait for pullback."
        if grade == Grade.B:
            return "Tradeable but needs disciplined confirmation; some validations are missing."
        if entry_type == EntryType.CHASING:
            return "Late move away from VWAP; skip unless price resets near support."
        if failed or warnings:
            return "Weak or conflicted setup; keep it on watchlist only."
        return "Low conviction setup."

    @staticmethod
    def _invalidation(side: Side, stop: float, vwap: float) -> str:
        if side == Side.LONG:
            return f"If price loses VWAP near {vwap:.2f} or sustains below {stop:.2f}, avoid the long."
        return f"If price reclaims VWAP near {vwap:.2f} or sustains above {stop:.2f}, avoid the short."
