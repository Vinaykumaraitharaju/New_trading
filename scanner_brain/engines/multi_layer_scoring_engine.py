from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from scanner_brain.config.scoring_profiles import ScoringProfile, reaction_profile_for_stock, sensitivity_for_group
from scanner_brain.core.enums import Bias, Grade, Side
from scanner_brain.core.models import (
    ExecutionAssessment,
    FactorGroupScore,
    FactorSignal,
    FinalAssessment,
    MarketContext,
    NewsAssessment,
    PatternAssessment,
    PredictionAssessment,
    SectorAssessment,
    StockSnapshot,
    TechnicalAssessment,
    WeightedScorecard,
)


class MultiLayerScoringEngine:
    """Weighted 15m-first decision scorecard.

    Every factor is rated from -2 to +2, then grouped through configurable
    weights. Counts are retained for transparency, but ranking uses the final
    weighted score and hard-block caps.
    """

    def __init__(self, profile: ScoringProfile) -> None:
        self.profile = profile

    def apply(
        self,
        *,
        stock: StockSnapshot,
        final: FinalAssessment,
        market: MarketContext,
        sector: SectorAssessment | None,
        technical: TechnicalAssessment,
        pattern: PatternAssessment,
        news: NewsAssessment,
        prediction: PredictionAssessment,
        execution: ExecutionAssessment,
    ) -> FinalAssessment:
        groups = self._groups(stock, final, market, sector, technical, pattern, news, prediction, execution)
        scorecard = self._scorecard(groups, stock, final, prediction, execution)
        grade = self._grade(scorecard.final_score, scorecard.hard_blocks)
        return replace(
            final,
            final_score=scorecard.final_score,
            grade=grade,
            scorecard=scorecard,
            conviction_label=scorecard.conviction_label,
            positive_count=scorecard.positive_count,
            negative_count=scorecard.negative_count,
            neutral_count=scorecard.neutral_count,
            pass_count=scorecard.pass_count,
            fail_count=scorecard.fail_count,
            conflict_score=scorecard.conflict_score,
            hard_blocks=scorecard.hard_blocks,
            boosters=scorecard.boosters,
            major_passes=scorecard.major_passes,
            major_failures=scorecard.major_failures,
            confidence_note=(
                f"{scorecard.conviction_label}. Weighted scorecard: {scorecard.final_score:.1f}/100. "
                f"Adaptive profile: {scorecard.reaction_profile}."
            ),
        )

    def _groups(
        self,
        stock: StockSnapshot,
        final: FinalAssessment,
        market: MarketContext,
        sector: SectorAssessment | None,
        technical: TechnicalAssessment,
        pattern: PatternAssessment,
        news: NewsAssessment,
        prediction: PredictionAssessment,
        execution: ExecutionAssessment,
    ) -> dict[str, list[FactorSignal]]:
        side = technical.side
        vwap = stock.vwap_proxy
        gap_abs = abs(stock.gap_pct)
        market_aligned = (side == Side.LONG and market.market_bias == "bullish") or (side == Side.SHORT and market.market_bias == "bearish")
        sector_aligned = sector is not None and ((side == Side.LONG and sector.bias == Bias.BULLISH) or (side == Side.SHORT and sector.bias == Bias.BEARISH))
        close_position = stock.price_position if side == Side.LONG else 1.0 - stock.price_position
        direction_change = stock.change_pct if side == Side.LONG else -stock.change_pct
        direction_move = stock.intraday_move_pct if side == Side.LONG else -stock.intraday_move_pct
        volume_known = stock.raw.get("liquidity_mode") != "snapshot_fallback" and stock.volume > 0

        return {
            "market_context": [
                self._signal("Index alignment", 2 if market_aligned else 0 if market.market_bias == "neutral" else -2, market.explanation),
                self._signal("Market strength", self._band(market.market_strength, 65, 56, 44, 35), f"Market score {market.market_strength:.0f}/100"),
                self._signal("Sector alignment", 2 if sector_aligned else 0 if sector is None or sector.bias == Bias.NEUTRAL else -1, sector.reasons[0] if sector and sector.reasons else "Sector read neutral"),
                self._signal("Breadth and risk mood", 1 if market.risk_state == "risk-on" and side == Side.LONG else 1 if market.risk_state == "risk-off" and side == Side.SHORT else 0 if market.risk_state == "neutral" else -1, market.risk_state),
            ],
            "price_action_structure": [
                self._signal("15m structure", self._structure_rating(prediction.structure_state, side), prediction.structure_state, hard_block=prediction.structure_state in {"CHOPPY", "CHOPPY_RANGE"}),
                self._signal("Candle close quality", 2 if close_position >= 0.78 else 1 if close_position >= 0.62 else -1 if close_position <= 0.38 else 0, f"Close position {close_position:.2f}"),
                self._signal("Expansion or compression", 2 if prediction.structure_state in {"EXPANSION_UP", "EXPANSION_DOWN"} else 1 if prediction.compression_state in {"TIGHT", "MODERATE"} else 0, f"{prediction.structure_state} / {prediction.compression_state}"),
                self._signal("Trap rejection", -2 if prediction.trap_risk == "HIGH" else -1 if prediction.trap_risk == "MEDIUM" else 1, f"Trap risk {prediction.trap_risk}", hard_block=prediction.trap_risk == "HIGH"),
            ],
            "trend": [
                self._signal("15m trend", self._structure_rating(prediction.structure_state, side), prediction.structure_state),
                self._signal("1h proxy trend", 2 if direction_change >= 1.2 else 1 if direction_change >= 0.35 else -1 if direction_change <= -0.35 else 0, f"Change {stock.change_pct:+.2f}%"),
                self._signal("Daily/open bias proxy", 1 if direction_move > 0 and ((side == Side.LONG and stock.open >= stock.prev_close) or (side == Side.SHORT and stock.open <= stock.prev_close)) else 0 if abs(stock.gap_pct) < 0.2 else -1, f"Gap {stock.gap_pct:+.2f}%"),
                self._signal("Trend maturity", -2 if prediction.exhaustion_state in {"CHASE_RISK_HIGH", "OVEREXTENDED"} else -1 if prediction.exhaustion_state == "EXTENDED" else 1, prediction.exhaustion_state),
            ],
            "volume": [
                self._signal("Relative volume", self._volume_rating(prediction.volume_state), prediction.volume_state, hard_block=prediction.volume_state in {"WEAK", "WEAK_VOLUME"} and execution.state != "TRADE"),
                self._signal("Volume consistency", 1 if volume_known else -1, "Live volume confirmed" if volume_known else "Live volume unavailable"),
                self._signal("Breakout volume", 2 if prediction.volume_state in {"CONFIRMED", "VOLUME_CONFIRMED"} else 1 if prediction.volume_state in {"EXPANDING", "BUILDING"} else -1, prediction.volume_state),
            ],
            "vwap": [
                self._signal("VWAP side", self._vwap_rating(prediction.vwap_state, side), prediction.vwap_state),
                self._signal("VWAP distance", 2 if final.vwap_distance_pct <= 0.55 else 1 if final.vwap_distance_pct <= 1.0 else -1 if final.vwap_distance_pct <= 1.55 else -2, f"{final.vwap_distance_pct:.2f}% from VWAP", hard_block=final.vwap_distance_pct > self.profile.extended_from_vwap_pct),
                self._signal("VWAP institutional behavior", 1 if prediction.vwap_state in {"ABOVE_HOLD", "BELOW_REJECT", "VWAP_RECLAIMED"} else -1, prediction.vwap_state),
            ],
            "opening_behavior": [
                self._signal("Gap quality", 1 if gap_abs >= self.profile.meaningful_gap_pct and direction_move >= 0 else 0 if gap_abs < self.profile.meaningful_gap_pct else -1, f"Gap {stock.gap_pct:+.2f}%"),
                self._signal("Opening drive", 2 if direction_move >= 1.0 else 1 if direction_move >= 0.35 else -1 if direction_move < -0.25 else 0, f"Intraday move {stock.intraday_move_pct:+.2f}%"),
                self._signal("Opening range location", 1 if close_position >= 0.66 else -1 if close_position <= 0.34 else 0, f"Range position {close_position:.2f}"),
            ],
            "support_resistance": [
                self._signal("Level tests", 2 if prediction.level_tests >= 3 and prediction.level_test_quality == "TIGHT" else 1 if prediction.level_tests >= 2 else -1 if prediction.level_tests == 1 else -2, f"{prediction.level_tests} {prediction.level_test_quality} tests"),
                self._signal("Clean trigger", 1 if prediction.key_level > 0 and final.invalidation_note else -2, f"Key level {prediction.key_level:.2f}", hard_block=prediction.key_level <= 0),
                self._signal("Barrier proximity", 1 if self._trigger_proximity_pct(final, prediction) <= 0.6 else -1, f"{self._trigger_proximity_pct(final, prediction):.2f}% from key level"),
            ],
            "volatility": [
                self._signal("Range expansion", 1 if 0.35 <= abs(stock.intraday_move_pct) <= 2.4 else -1 if abs(stock.intraday_move_pct) > 3.0 else 0, f"Move {stock.intraday_move_pct:+.2f}%"),
                self._signal("ATR proxy", 1 if technical.atr_proxy > stock.ltp * 0.004 else -1, f"ATR proxy {technical.atr_proxy:.2f}"),
                self._signal("Overextension risk", -2 if prediction.exhaustion_state in {"CHASE_RISK_HIGH", "OVEREXTENDED"} else -1 if prediction.exhaustion_state == "EXTENDED" else 1, prediction.exhaustion_state),
            ],
            "pattern": [
                self._signal("Pattern confluence", 1 if pattern.detected else 0, ", ".join(pattern.detected) or "No dominant pattern"),
                self._signal("Liquidity sweep/trap", -2 if prediction.trap_risk == "HIGH" else 1 if "failed" in " ".join(pattern.detected).lower() else 0, prediction.trap_risk),
            ],
            "indicator_confirmation": [
                self._signal("Momentum slope proxy", 1 if direction_change > 0.35 else -1 if direction_change < -0.35 else 0, f"Change {stock.change_pct:+.2f}%"),
                self._signal("EMA proxy", 1 if (side == Side.LONG and stock.ltp >= max(stock.open, vwap)) or (side == Side.SHORT and stock.ltp <= min(stock.open, vwap)) else -1, "Price vs open/VWAP proxy"),
                self._signal("RSI/MACD support proxy", 0 if abs(direction_change) < 2.8 else -1, "Indicators support only, never primary"),
            ],
            "liquidity_orderflow_proxy": [
                self._signal("Tradability", 2 if volume_known and stock.volume >= self.profile.fast_filter.min_volume * 1.5 else 1 if volume_known else -1, f"Volume {stock.volume:,.0f}"),
                self._signal("Acceptance above/below level", 1 if prediction.pressure_state in {"BUYER_PRESSURE", "SELLER_PRESSURE", "ABSORPTION", "MOMENTUM"} else -1, prediction.pressure_state),
                self._signal("Demand/supply defense", 1 if prediction.vwap_state in {"ABOVE_HOLD", "BELOW_REJECT", "VWAP_RECLAIMED"} else -1, prediction.vwap_state),
            ],
            "news_events": [
                self._signal("News sentiment", 1 if news.bias == Bias.BULLISH and side == Side.LONG else 1 if news.bias == Bias.BEARISH and side == Side.SHORT else -1 if news.bias not in {Bias.NEUTRAL} else 0, "; ".join(news.reasons[:1]) or "No fresh event boost"),
                self._signal("Event freshness", 1 if news.confidence >= 0.7 else 0, f"News confidence {news.confidence:.0%}"),
            ],
            "macro_overlay": [
                self._signal("Risk overlay", 1 if market.risk_state != "neutral" and not market_aligned else 0 if market.risk_state == "neutral" else -1, market.risk_state),
            ],
            "execution_quality": [
                self._signal("Entry clarity", 2 if execution.entry_quality == "IDEAL" else 1 if execution.entry_quality == "ACCEPTABLE" else -1 if execution.entry_quality == "RISKY" else -2, execution.entry_quality, hard_block=execution.entry_quality == "LATE"),
                self._signal("Stop clarity", 1 if final.stop_loss > 0 and final.invalidation_note else -2, final.invalidation_note or "No clean stop", hard_block=final.stop_loss <= 0),
                self._signal("Reward risk", 2 if final.rr >= 2.0 else 1 if final.rr >= self.profile.min_rr_for_selection else -2, f"RR 1:{final.rr:.2f}", hard_block=final.rr < self.profile.min_rr_for_selection),
                self._signal("Chase risk", -2 if final.entry_type.value == "CHASING" else -1 if final.entry_type.value == "RISKY" else 1, final.entry_reason, hard_block=final.entry_type.value == "CHASING"),
            ],
            "risk_filter": [
                self._signal("Hard risk blocks", -2 if execution.state == "AVOID" else 0, execution.avoid_reason or execution.state, hard_block=execution.state == "AVOID"),
                self._signal("Conflict level", -2 if len(prediction.contradictions) >= 4 else -1 if prediction.contradictions else 0, f"{len(prediction.contradictions)} contradictions"),
                self._signal("Market disagreement", -2 if not market_aligned and market.market_bias != "neutral" else 0, market.market_bias),
            ],
        }

    def _scorecard(
        self,
        groups: dict[str, list[FactorSignal]],
        stock: StockSnapshot,
        final: FinalAssessment,
        prediction: PredictionAssessment,
        execution: ExecutionAssessment,
    ) -> WeightedScorecard:
        reaction_profile = reaction_profile_for_stock(stock.symbol, stock.sector, stock.raw)
        weights = self._adaptive_group_weights(reaction_profile.group_multipliers)
        group_scores: dict[str, FactorGroupScore] = {}
        weighted_total = 0.0
        total_weight = sum(float(weight) for weight in weights.values()) or 1.0
        positive = negative = neutral = 0
        hard_blocks: list[str] = []
        boosters: list[str] = []
        major_passes: list[str] = []
        major_failures: list[str] = []

        for group, signals in groups.items():
            weight = float(weights.get(group, 0.0))
            raw = self._group_raw_score(signals)
            raw = self._apply_group_sensitivity(raw, sensitivity_for_group(reaction_profile, group))
            positive += sum(1 for signal in signals if signal.rating > 0)
            negative += sum(1 for signal in signals if signal.rating < 0)
            neutral += sum(1 for signal in signals if signal.rating == 0)
            passes = [signal.name for signal in signals if signal.rating > 0]
            failures = [signal.name for signal in signals if signal.rating < 0]
            neutrals = [signal.name for signal in signals if signal.rating == 0]
            hard_blocks.extend([signal.reason or signal.name for signal in signals if signal.hard_block and signal.rating < 0])
            if weight >= 0.06:
                major_passes.extend([f"{group}: {name}" for name in passes[:2]])
                major_failures.extend([f"{group}: {name}" for name in failures[:2]])
            if weight >= 0.06 and raw >= 72:
                boosters.append(group.replace("_", " ").title())
            weighted_points = raw * weight
            weighted_total += weighted_points
            group_scores[group] = FactorGroupScore(
                group=group,
                score=round(raw, 1),
                weighted_points=round(weighted_points, 2),
                weight=weight,
                positive=len(passes),
                negative=len(failures),
                neutral=len(neutrals),
                passes=passes,
                failures=failures,
                neutrals=neutrals,
                summary=self._group_summary(group, raw, passes, failures),
            )

        score = max(0.0, min(100.0, weighted_total / total_weight))
        if group_scores["market_context"].score < 42 and final.side == Side.LONG:
            score = min(score, 58.0)
        if group_scores["price_action_structure"].score < self.profile.thresholds.min_clean_structure_score:
            score = min(score, 55.0)
        if group_scores["execution_quality"].score < self.profile.thresholds.min_execution_score:
            score = min(score, 52.0)
        if group_scores["risk_filter"].score < 35 or hard_blocks:
            score = min(score, self.profile.thresholds.hard_block_score_cap)
        if prediction.trap_risk == "HIGH" or execution.state == "AVOID":
            score = min(score, 44.0)

        conflict_score = negative + len(hard_blocks) * 2 + len(prediction.contradictions)
        grade_label = self._grade_label(score, hard_blocks)
        if reaction_profile.name != "Balanced":
            boosters.insert(0, f"Adaptive Profile: {reaction_profile.name}")
        return WeightedScorecard(
            final_score=round(score, 1),
            grade_label=grade_label,
            conviction_label=grade_label,
            positive_count=positive,
            negative_count=negative,
            neutral_count=neutral,
            pass_count=positive,
            fail_count=negative + len(hard_blocks),
            conflict_score=conflict_score,
            hard_blocks=list(dict.fromkeys(hard_blocks))[:6],
            boosters=list(dict.fromkeys(boosters))[:6],
            major_passes=list(dict.fromkeys(major_passes))[:10],
            major_failures=list(dict.fromkeys(major_failures))[:10],
            group_scores=group_scores,
            factor_heatmap={group: item.score for group, item in group_scores.items()},
            reaction_profile=reaction_profile.name,
            reaction_profile_note=reaction_profile.description,
            adaptive_weights={group: round(float(weight), 4) for group, weight in weights.items()},
            stock_sensitivities={group: round(float(value), 3) for group, value in reaction_profile.sensitivities.items()},
        )

    def _adaptive_group_weights(self, multipliers: dict[str, float]) -> dict[str, float]:
        base_weights = self.profile.group_weights.__dict__
        return {
            group: max(0.0, float(weight) * float(multipliers.get(group, 1.0)))
            for group, weight in base_weights.items()
        }

    @staticmethod
    def _apply_group_sensitivity(raw_score: float, sensitivity: float) -> float:
        """Amplify or mute distance from neutral based on stock behavior."""

        distance_from_neutral = raw_score - 50.0
        adjusted = 50.0 + distance_from_neutral * sensitivity
        return max(0.0, min(100.0, adjusted))

    @staticmethod
    def _signal(name: str, rating: int, reason: str, *, hard_block: bool = False) -> FactorSignal:
        clipped = max(-2, min(2, int(rating)))
        labels = {-2: "Strong Bearish", -1: "Bearish", 0: "Neutral", 1: "Bullish", 2: "Strong Bullish"}
        return FactorSignal(name=name, rating=clipped, label=labels[clipped], reason=reason, hard_block=hard_block)

    @staticmethod
    def _group_raw_score(signals: Iterable[FactorSignal]) -> float:
        values = list(signals)
        if not values:
            return 50.0
        weighted_sum = sum(signal.rating * signal.weight for signal in values)
        max_abs = sum(2.0 * signal.weight for signal in values)
        return max(0.0, min(100.0, 50.0 + (weighted_sum / max(max_abs, 0.01)) * 50.0))

    @staticmethod
    def _band(value: float, strong_pos: float, pos: float, neg: float, strong_neg: float) -> int:
        if value >= strong_pos:
            return 2
        if value >= pos:
            return 1
        if value <= strong_neg:
            return -2
        if value <= neg:
            return -1
        return 0

    @staticmethod
    def _structure_rating(state: str, side: Side) -> int:
        if state == "HH_HL_BUILDING":
            return 2 if side == Side.LONG else -1
        if state == "LH_LL_BUILDING":
            return 2 if side == Side.SHORT else -1
        if state in {"EXPANSION_UP", "EXPANSION_DOWN"}:
            return 2 if (state.endswith("UP") and side == Side.LONG) or (state.endswith("DOWN") and side == Side.SHORT) else -1
        if state == "RANGE_COMPRESSION":
            return 1
        if state in {"CHOPPY", "CHOPPY_RANGE"}:
            return -2
        return 0

    @staticmethod
    def _volume_rating(state: str) -> int:
        return {
            "VOLUME_CONFIRMED": 2,
            "CONFIRMED": 2,
            "EXPANDING_ON_PUSH": 2,
            "EXPANDING": 1,
            "HEALTHY_BUILDUP": 1,
            "BUILDING": 1,
            "DRY_COMPRESSION": 1,
            "WEAK": -2,
            "WEAK_VOLUME": -2,
        }.get(state, 0)

    @staticmethod
    def _vwap_rating(state: str, side: Side) -> int:
        if state == "ABOVE_HOLD":
            return 2 if side == Side.LONG else -1
        if state == "BELOW_REJECT":
            return 2 if side == Side.SHORT else -1
        if state == "VWAP_RECLAIMED":
            return 1
        if state == "EXTENDED":
            return -2
        if state == "VWAP_CHOPPY":
            return -1
        return 0

    @staticmethod
    def _trigger_proximity_pct(final: FinalAssessment, prediction: PredictionAssessment) -> float:
        if prediction.key_level <= 0:
            return 99.0
        trigger = final.entry_high if final.side == Side.LONG else final.entry_low
        return abs(trigger - prediction.key_level) / max(abs(prediction.key_level), 0.01) * 100.0

    @staticmethod
    def _group_summary(group: str, score: float, passes: list[str], failures: list[str]) -> str:
        if failures and score < 45:
            return f"{group.replace('_', ' ').title()} is failing: {', '.join(failures[:2])}."
        if passes and score >= 60:
            return f"{group.replace('_', ' ').title()} supports the setup: {', '.join(passes[:2])}."
        return f"{group.replace('_', ' ').title()} is neutral."

    def _grade_label(self, score: float, hard_blocks: list[str]) -> str:
        t = self.profile.thresholds
        if hard_blocks or score < t.bronze:
            return "Reject"
        if score >= t.diamond:
            return "Diamond"
        if score >= t.platinum:
            return "Platinum"
        if score >= t.gold:
            return "Gold"
        if score >= t.silver:
            return "Silver"
        return "Bronze"

    @staticmethod
    def _grade(score: float, hard_blocks: list[str]) -> Grade:
        if hard_blocks or score < 42:
            return Grade.REJECT
        if score >= 86:
            return Grade.A_PLUS
        if score >= 76:
            return Grade.A
        if score >= 64:
            return Grade.B
        if score >= 52:
            return Grade.C
        return Grade.REJECT
