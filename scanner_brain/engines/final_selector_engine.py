from __future__ import annotations

from dataclasses import replace

from scanner_brain.config.scoring_profiles import ScoringProfile
from scanner_brain.core.enums import Bias, Decision, Grade, Side
from scanner_brain.core.models import FinalAssessment, MarketContext, SectorAssessment


class FinalSelectorEngine:
    """Institutional-quality top-5 selector run only after prediction and execution."""

    MIN_INSTITUTIONAL_SCORE = 58.0
    LOW_OPPORTUNITY_SCORE = 52.0

    def __init__(self, profile: ScoringProfile) -> None:
        self.profile = profile

    def select(
        self,
        assessments: list[FinalAssessment],
        *,
        market_context: MarketContext,
        sectors: dict[str, SectorAssessment],
        min_score: float,
    ) -> tuple[list[FinalAssessment], list[dict[str, str]]]:
        scored = [
            self._score_assessment(item, market_context=market_context, sector=sectors.get(item.sector))
            for item in assessments
        ]
        rejected: list[dict[str, str]] = []
        candidates: list[FinalAssessment] = []
        for item in scored:
            hard_reasons = self._hard_filter_reasons(item)
            if hard_reasons:
                rejected.append({"symbol": item.symbol, "reason": "; ".join(hard_reasons[:3])})
                continue
            if item.final_selector_score < max(min_score, self.LOW_OPPORTUNITY_SCORE):
                rejected.append({"symbol": item.symbol, "reason": f"Institutional selector score {item.final_selector_score:.1f} below threshold"})
                continue
            candidates.append(item)

        candidates = sorted(candidates, key=self._ranking_key, reverse=True)
        selected_pool = self._opportunity_pool(candidates)
        if not selected_pool and scored:
            rejected.append({"symbol": "MARKET", "reason": "Low Opportunity Market: no clean institutional-quality setup after full analysis"})
        selected = self._differentiate_ranked_list(selected_pool[: self.profile.top_n])
        if selected and all(item.execution_state == "WAIT" for item in selected):
            rejected.append({"symbol": "MARKET", "reason": f"Only {len(selected)} watchlist-quality setups; no trade-ready confirmation yet"})
        return selected, rejected

    def _score_assessment(
        self,
        item: FinalAssessment,
        *,
        market_context: MarketContext,
        sector: SectorAssessment | None,
    ) -> FinalAssessment:
        components = {
            "weighted_scorecard": self._weighted_scorecard_quality(item),
            "prediction": self._prediction_quality(item),
            "execution": self._execution_readiness(item),
            "structure": self._structure_quality(item),
            "level": self._level_quality(item),
            "proximity": self._breakout_proximity_quality(item),
            "vwap": self._vwap_quality(item),
            "volume": self._volume_quality(item),
            "market": self._market_alignment(item, market_context),
            "sector": self._sector_alignment(item, sector),
            "rr": self._risk_reward_score(item),
        }
        # Weighted blend mirrors the scanner purpose: early preparation first, then executable risk.
        score = (
            components["weighted_scorecard"] * 0.38
            + components["prediction"] * 0.16
            + components["execution"] * 0.14
            + components["structure"] * 0.11
            + components["level"] * 0.07
            + components["proximity"] * 0.05
            + components["volume"] * 0.04
            + components["vwap"] * 0.03
            + components["market"] * 0.01
            + components["sector"] * 0.005
            + components["rr"] * 0.005
        )
        penalties = self._penalties(item)
        score += self._relative_edge_points(item)
        score = max(0.0, min(100.0, score - sum(penalties.values())))
        score = self._score_caps(item, score)
        bucket = self._bucket(item, score)
        why_selected = self._why_selected(item)
        why_not_higher = self._why_not_higher(item, penalties, components)
        return replace(
            item,
            final_selector_score=round(score, 1),
            final_score=round(score, 1),
            grade=self._grade(score, item),
            decision=self._decision(score, item),
            selection_bucket=bucket,
            why_selected=why_selected,
            what_must_happen=self._what_must_happen(item),
            why_not_higher=why_not_higher,
            why_ranked_here="Awaiting final relative ranking.",
            confidence_note=self._confidence_note(bucket, why_not_higher),
        )

    def _opportunity_pool(self, candidates: list[FinalAssessment]) -> list[FinalAssessment]:
        high_quality = [
            item for item in candidates
            if item.final_selector_score >= self.MIN_INSTITUTIONAL_SCORE
            and item.selection_bucket in {"TRADE_READY", "NEAR_TRIGGER", "EARLY_WATCH"}
        ]
        if high_quality:
            risky = [
                item for item in candidates
                if item.selection_bucket == "RISKY"
                and item.final_selector_score >= self.MIN_INSTITUTIONAL_SCORE + 4.0
            ][:1]
            return high_quality + risky
        return []

    def _differentiate_ranked_list(self, items: list[FinalAssessment]) -> list[FinalAssessment]:
        items = self._normalize_score_spread(items)
        differentiated: list[FinalAssessment] = []
        last_score: float | None = None
        last_signature: tuple | None = None
        for rank, item in enumerate(items, start=1):
            signature = self._setup_signature(item)
            score = float(item.final_selector_score)
            # Keep exact ties only for truly identical setup signatures; otherwise enforce the best relative edge.
            if last_score is not None and round(score, 1) >= last_score and signature != last_signature:
                score = max(0.0, last_score - 0.1)
            bucket = self._bucket_for_rank(item, score, rank, len(items))
            why_ranked_here = self._why_ranked_here(item, rank, score, items)
            differentiated.append(
                replace(
                    item,
                    final_selector_score=round(score, 1),
                    final_score=round(score, 1),
                    grade=self._grade(score, item),
                    decision=self._decision(score, item),
                    selection_bucket=bucket,
                    why_ranked_here=why_ranked_here,
                    confidence_note=self._confidence_note(bucket, item.why_not_higher, why_ranked_here),
                )
            )
            last_score = round(score, 1)
            last_signature = signature
        return differentiated

    @staticmethod
    def _normalize_score_spread(items: list[FinalAssessment]) -> list[FinalAssessment]:
        if len(items) <= 1:
            return items
        ordered = sorted(items, key=FinalSelectorEngine._ranking_key, reverse=True)
        signatures = {FinalSelectorEngine._setup_signature(item) for item in ordered}
        if len(signatures) == 1:
            return ordered
        top_score = float(ordered[0].final_selector_score)
        bottom_score = float(ordered[-1].final_selector_score)
        target_spread = min(18.0, max(8.0, len(ordered) * 2.2))
        if top_score - bottom_score >= target_spread:
            return ordered

        normalized: list[FinalAssessment] = []
        step = target_spread / max(len(ordered) - 1, 1)
        anchor = min(96.0, max(top_score, 72.0 if ordered[0].selection_bucket in {"TRADE_READY", "NEAR_TRIGGER"} else top_score))
        for idx, item in enumerate(ordered):
            score = max(0.0, min(100.0, anchor - step * idx))
            capped = FinalSelectorEngine._score_caps(item, score)
            if idx and capped >= normalized[-1].final_selector_score:
                capped = max(0.0, normalized[-1].final_selector_score - 0.2)
            normalized.append(replace(item, final_selector_score=round(capped, 1), final_score=round(capped, 1)))
        return normalized

    @staticmethod
    def _ranking_key(item: FinalAssessment) -> tuple:
        return (
            item.final_selector_score,
            item.trap_risk == "LOW",
            FinalSelectorEngine._structure_rank(item),
            item.level_tests,
            item.level_test_quality == "TIGHT",
            FinalSelectorEngine._volume_rank(item),
            FinalSelectorEngine._vwap_rank(item),
            FinalSelectorEngine._execution_rank(item),
            item.rr,
            -FinalSelectorEngine._trigger_proximity_pct(item),
            FinalSelectorEngine._relative_edge_points(item),
            item.selection_bucket == "TRADE_READY",
            item.selection_bucket == "NEAR_TRIGGER",
            item.symbol,
        )

    @staticmethod
    def _setup_signature(item: FinalAssessment) -> tuple:
        return (
            item.side,
            item.pre_breakout_status,
            item.execution_state,
            item.structure_state,
            item.compression_state,
            item.level_tests,
            item.level_test_quality,
            item.vwap_state,
            item.volume_state,
            item.trap_risk,
            item.exhaustion_state,
            item.execution_entry_quality,
            round(item.rr, 2),
            round(item.vwap_distance_pct, 2),
            round(item.key_level, 2),
        )

    @staticmethod
    def _relative_edge_points(item: FinalAssessment) -> float:
        edge = 0.0
        edge += {
            "HH_HL_BUILDING": 1.8 if item.side == Side.LONG else 0.4,
            "LH_LL_BUILDING": 1.8 if item.side == Side.SHORT else 0.4,
            "RANGE_COMPRESSION": 1.2,
            "EXPANSION_UP": 1.4 if item.side == Side.LONG else -0.6,
            "EXPANSION_DOWN": 1.4 if item.side == Side.SHORT else -0.6,
            "CHOPPY": -1.8,
            "CHOPPY_RANGE": -1.8,
        }.get(item.structure_state, 0.0)
        edge += min(max(item.level_tests, 0), 4) * 0.45
        if item.level_test_quality == "TIGHT":
            edge += 0.75
        edge += {
            "CONFIRMED": 1.4,
            "VOLUME_CONFIRMED": 1.4,
            "EXPANDING_ON_PUSH": 1.25,
            "EXPANDING": 1.1,
            "HEALTHY_BUILDUP": 0.9,
            "BUILDING": 0.75,
            "DRY_COMPRESSION": 0.45,
            "WEAK": -1.2,
            "WEAK_VOLUME": -1.2,
        }.get(item.volume_state, 0.0)
        edge += {"LOW": 1.1, "MEDIUM": -0.6, "HIGH": -2.0}.get(item.trap_risk, -0.2)
        edge += {"FRESH": 0.8, "ACCEPTABLE": 0.35, "EXTENDED": -1.1, "OVEREXTENDED": -1.4, "CHASE_RISK_HIGH": -2.0}.get(item.exhaustion_state, 0.0)
        edge += max(0.0, 1.2 - min(item.vwap_distance_pct, 2.4) * 0.5)
        trigger = item.entry_high if item.side == Side.LONG else item.entry_low
        proximity_pct = abs(trigger - item.key_level) / max(abs(item.key_level), 0.01) * 100.0 if item.key_level else 99.0
        edge += max(-0.8, 1.0 - proximity_pct)
        return round(edge, 4)

    @staticmethod
    def _structure_rank(item: FinalAssessment) -> int:
        directional = {
            "HH_HL_BUILDING": 6 if item.side == Side.LONG else 2,
            "LH_LL_BUILDING": 6 if item.side == Side.SHORT else 2,
            "RANGE_COMPRESSION": 5,
            "EXPANSION_UP": 4 if item.side == Side.LONG else 1,
            "EXPANSION_DOWN": 4 if item.side == Side.SHORT else 1,
            "CHOPPY": 0,
            "CHOPPY_RANGE": 0,
        }
        return directional.get(item.structure_state, 1)

    @staticmethod
    def _volume_rank(item: FinalAssessment) -> int:
        return {
            "VOLUME_CONFIRMED": 7,
            "CONFIRMED": 7,
            "EXPANDING_ON_PUSH": 6,
            "EXPANDING": 5,
            "HEALTHY_BUILDUP": 4,
            "BUILDING": 3,
            "DRY_COMPRESSION": 2,
            "WEAK": 0,
            "WEAK_VOLUME": 0,
        }.get(item.volume_state, 1)

    @staticmethod
    def _vwap_rank(item: FinalAssessment) -> int:
        if item.side == Side.LONG and item.vwap_state == "ABOVE_HOLD":
            return 5
        if item.side == Side.SHORT and item.vwap_state == "BELOW_REJECT":
            return 5
        return {"VWAP_RECLAIMED": 4, "VWAP_CHOPPY": 1, "EXTENDED": 0}.get(item.vwap_state, 2)

    @staticmethod
    def _execution_rank(item: FinalAssessment) -> int:
        return {"TRADE": 4, "WAIT": 2, "AVOID": 0}.get(item.execution_state, 1)

    @staticmethod
    def _context_edge_points(item: FinalAssessment, market_context: MarketContext) -> float:
        if item.side == Side.LONG and market_context.market_bias == "bullish":
            return 2.0
        if item.side == Side.SHORT and market_context.market_bias == "bearish":
            return 2.0
        if market_context.market_bias == "neutral":
            return 0.0
        return -2.0

    @staticmethod
    def _prediction_quality(item: FinalAssessment) -> float:
        score = min(max(float(item.prediction_strength), 0.0), 100.0)
        if item.pre_breakout_status == "NEAR_BREAKOUT":
            score += 8.0
        elif item.pre_breakout_status == "BUILDING":
            score += 3.0
        elif item.pre_breakout_status == "NO_SETUP":
            score -= 30.0
        if item.breakout_probability == "HIGH":
            score += 10.0
        elif item.breakout_probability == "MEDIUM":
            score += 4.0
        else:
            score -= 12.0
        if item.pressure_state in {"BUYER_PRESSURE", "SELLER_PRESSURE", "MOMENTUM", "ABSORPTION"}:
            score += 5.0
        if item.prediction_explanation:
            score += 2.0
        return max(0.0, min(100.0, score))

    @staticmethod
    def _weighted_scorecard_quality(item: FinalAssessment) -> float:
        if item.scorecard is not None:
            return item.scorecard.final_score
        return item.final_score

    @staticmethod
    def _execution_readiness(item: FinalAssessment) -> float:
        state_score = {"TRADE": 100.0, "WAIT": 76.0, "AVOID": 12.0}.get(item.execution_state, 45.0)
        quality_bonus = {"IDEAL": 10.0, "ACCEPTABLE": 4.0, "RISKY": -12.0, "LATE": -25.0}.get(item.execution_entry_quality, -8.0)
        invalidation_bonus = 5.0 if item.invalidation_note or item.execution_explanation else -8.0
        near_trigger_bonus = 5.0 if item.pre_breakout_status == "NEAR_BREAKOUT" and item.execution_state == "WAIT" else 0.0
        return max(0.0, min(100.0, state_score + quality_bonus + invalidation_bonus + near_trigger_bonus))

    @staticmethod
    def _structure_quality(item: FinalAssessment) -> float:
        mapping = {
            "HH_HL_BUILDING": 92.0 if item.side == Side.LONG else 58.0,
            "LH_LL_BUILDING": 92.0 if item.side == Side.SHORT else 58.0,
            "RANGE_COMPRESSION": 78.0,
            "EXPANSION_UP": 88.0 if item.side == Side.LONG else 50.0,
            "EXPANSION_DOWN": 88.0 if item.side == Side.SHORT else 50.0,
            "CHOPPY": 20.0,
            "CHOPPY_RANGE": 20.0,
        }
        score = mapping.get(item.structure_state, 45.0)
        if item.compression_state == "TIGHT":
            score += 8.0
        elif item.compression_state == "MODERATE":
            score += 4.0
        return max(0.0, min(100.0, score))

    @staticmethod
    def _level_quality(item: FinalAssessment) -> float:
        if item.level_tests >= 3 and item.level_test_quality == "TIGHT":
            return 96.0
        if item.level_tests == 2 and item.level_test_quality == "TIGHT":
            return 86.0
        if item.level_tests >= 2:
            return 70.0
        if item.level_tests == 1:
            return 42.0
        return 24.0

    @staticmethod
    def _breakout_proximity_quality(item: FinalAssessment) -> float:
        proximity = FinalSelectorEngine._trigger_proximity_pct(item)
        if item.exhaustion_state in {"EXTENDED", "OVEREXTENDED", "CHASE_RISK_HIGH"} or item.vwap_state == "EXTENDED":
            return 18.0
        if proximity <= 0.12:
            return 96.0
        if proximity <= 0.30:
            return 86.0
        if proximity <= 0.60:
            return 70.0
        if proximity <= 1.00:
            return 52.0
        return 30.0

    @staticmethod
    def _trigger_proximity_pct(item: FinalAssessment) -> float:
        if item.key_level <= 0:
            return 99.0
        trigger = item.entry_high if item.side == Side.LONG else item.entry_low
        return abs(trigger - item.key_level) / max(abs(item.key_level), 0.01) * 100.0

    @staticmethod
    def _vwap_quality(item: FinalAssessment) -> float:
        mapping = {
            "ABOVE_HOLD": 92.0 if item.side == Side.LONG else 48.0,
            "BELOW_REJECT": 92.0 if item.side == Side.SHORT else 48.0,
            "VWAP_RECLAIMED": 86.0,
            "VWAP_CHOPPY": 30.0,
            "EXTENDED": 18.0,
        }
        return mapping.get(item.vwap_state, 45.0)

    @staticmethod
    def _volume_quality(item: FinalAssessment) -> float:
        mapping = {
            "DRY_COMPRESSION": 72.0,
            "BUILDING": 82.0,
            "HEALTHY_BUILDUP": 84.0,
            "EXPANDING": 90.0,
            "EXPANDING_ON_PUSH": 92.0,
            "CONFIRMED": 96.0,
            "VOLUME_CONFIRMED": 96.0,
            "WEAK": 22.0,
            "WEAK_VOLUME": 22.0,
        }
        return mapping.get(item.volume_state, 45.0)

    @staticmethod
    def _market_alignment(item: FinalAssessment, market_context: MarketContext) -> float:
        if item.side == Side.LONG and market_context.market_bias == "bullish":
            return 92.0
        if item.side == Side.SHORT and market_context.market_bias == "bearish":
            return 92.0
        if market_context.market_bias == "neutral":
            return 58.0
        return 28.0

    @staticmethod
    def _sector_alignment(item: FinalAssessment, sector: SectorAssessment | None) -> float:
        if sector is None:
            return 45.0
        if sector.bias == Bias.NEUTRAL:
            return 55.0
        if item.side == Side.LONG and sector.bias == Bias.BULLISH:
            return 88.0
        if item.side == Side.SHORT and sector.bias == Bias.BEARISH:
            return 88.0
        return 28.0

    def _risk_reward_score(self, item: FinalAssessment) -> float:
        if item.rr < self.profile.min_rr_for_selection:
            return 10.0
        if item.rr >= 2.0:
            return 96.0
        if item.rr >= 1.6:
            return 84.0
        return 68.0

    @staticmethod
    def _penalties(item: FinalAssessment) -> dict[str, float]:
        penalties: dict[str, float] = {}
        if item.trap_risk == "HIGH":
            penalties["high trap risk"] = 20.0
        elif item.trap_risk == "MEDIUM":
            penalties["medium trap risk"] = 8.0
        if item.exhaustion_state == "CHASE_RISK_HIGH" or item.execution_entry_quality == "LATE":
            penalties["chase risk high"] = 15.0
        if item.exhaustion_state in {"EXTENDED", "OVEREXTENDED"} or item.vwap_state == "EXTENDED":
            penalties["overextended from VWAP"] = 12.0
        if item.structure_state in {"CHOPPY", "CHOPPY_RANGE"}:
            penalties["structure not confirmed"] = 10.0
        if item.volume_state in {"WEAK", "WEAK_VOLUME"}:
            penalties["weak volume"] = 10.0
            if item.execution_state != "TRADE":
                penalties["weak volume at trigger"] = 8.0
        if item.level_tests == 1:
            penalties["only one level test"] = 6.0
        if item.snapshot_mode:
            penalties["snapshot mode used"] = 12.0
        if item.time_quality == "MIDDAY" and item.volume_state in {"WEAK", "WEAK_VOLUME"}:
            penalties["midday low-quality move"] = 5.0
        if FinalSelectorEngine._has_degraded_data(item):
            penalties["degraded data source"] = 15.0
        if item.conflict_score >= 7:
            penalties["too many conflicting factors"] = 10.0
        if item.hard_blocks:
            penalties["hard risk block"] = 18.0
        return penalties

    @staticmethod
    def _score_caps(item: FinalAssessment, score: float) -> float:
        if item.snapshot_mode:
            score = min(score, 72.0)
        if item.trap_risk == "MEDIUM":
            score = min(score, 82.0)
        if item.volume_state in {"WEAK", "WEAK_VOLUME"} or item.level_tests <= 1:
            score = min(score, 68.0)
        if item.exhaustion_state in {"EXTENDED", "OVEREXTENDED"} or item.vwap_state == "EXTENDED":
            score = min(score, 58.0)
        if item.trap_risk == "HIGH" or item.exhaustion_state == "CHASE_RISK_HIGH" or item.execution_state == "AVOID":
            score = min(score, 45.0)
        if FinalSelectorEngine._has_degraded_data(item):
            score = min(score, 52.0)
        if item.hard_blocks:
            score = min(score, 44.0)
        return score

    def _hard_filter_reasons(self, item: FinalAssessment) -> list[str]:
        reasons: list[str] = []
        if item.pre_breakout_status == "NO_SETUP":
            reasons.append("prediction status is NO_SETUP")
        if item.pre_breakout_status == "EXHAUSTED":
            reasons.append("prediction status is EXHAUSTED")
        if item.structure_state in {"CHOPPY", "CHOPPY_RANGE"} and not item.snapshot_mode:
            reasons.append("structure is choppy")
        if item.trap_risk == "HIGH":
            reasons.append("trap risk is HIGH")
        if item.breakout_probability == "LOW":
            reasons.append("breakout probability is LOW")
        if item.volume_state in {"WEAK", "WEAK_VOLUME"} and item.execution_state != "TRADE" and not item.snapshot_mode:
            reasons.append("weak volume at trigger")
        if item.exhaustion_state in {"OVEREXTENDED", "CHASE_RISK_HIGH"}:
            reasons.append("move is chase risk high")
        if item.execution_state == "AVOID":
            reasons.append("execution state is AVOID")
        if item.hard_blocks:
            reasons.append("hard block: " + item.hard_blocks[0])
        if item.conflict_score >= self.profile.thresholds.max_conflict_for_top5:
            reasons.append("conflict score too high")
        if item.rr < self.profile.min_rr_for_selection:
            reasons.append("risk reward below minimum")
        if item.key_level <= 0 or not item.invalidation_note:
            reasons.append("breakout level unclear")
        if self._has_degraded_data(item) and item.snapshot_mode:
            reasons.append("snapshot fallback with degraded data source")
        return reasons

    @staticmethod
    def _has_degraded_data(item: FinalAssessment) -> bool:
        text = " | ".join(
            str(value).lower()
            for value in [
                *item.missing,
                *item.warnings,
                *item.prediction_warnings,
                *item.contradictions,
                item.confidence_note,
                item.market_explanation,
            ]
            if str(value).strip()
        )
        degraded_terms = (
            "degraded",
            "stale",
            "fallback",
            "snapshot fallback",
            "authentication blocked",
            "not connected",
            "live volume unavailable",
            "volume unavailable",
        )
        return any(term in text for term in degraded_terms)

    @staticmethod
    def _bucket(item: FinalAssessment, score: float) -> str:
        if item.execution_state == "TRADE" and score >= 78 and item.trap_risk == "LOW" and item.rr >= 1.2:
            return "TRADE_READY"
        if item.pre_breakout_status == "NEAR_BREAKOUT" and score >= 70:
            return "NEAR_TRIGGER"
        if score >= 58 and item.pre_breakout_status == "BUILDING":
            return "EARLY_WATCH"
        return "RISKY"

    @staticmethod
    def _bucket_for_rank(item: FinalAssessment, score: float, rank: int, total: int) -> str:
        base = FinalSelectorEngine._bucket(item, score)
        if base == "TRADE_READY" or total <= 2:
            return base
        if item.execution_state == "WAIT" and item.pre_breakout_status == "NEAR_BREAKOUT" and item.trap_risk == "LOW":
            return "NEAR_TRIGGER" if rank <= 2 or score >= 72 else "EARLY_WATCH"
        if item.pre_breakout_status == "BUILDING" and score >= 58:
            return "EARLY_WATCH" if rank <= max(4, total - 1) else "RISKY"
        if rank == total and total >= 4:
            return "RISKY"
        return base

    @staticmethod
    def _grade(score: float, item: FinalAssessment) -> Grade:
        if score >= 85 and item.trap_risk == "LOW":
            return Grade.A_PLUS
        if score >= 72:
            return Grade.A
        if score >= 58:
            return Grade.B
        if score >= 45:
            return Grade.C
        return Grade.REJECT

    @staticmethod
    def _decision(score: float, item: FinalAssessment) -> Decision:
        if score < 58 or item.execution_state == "AVOID":
            return Decision.REJECTED
        if item.execution_state == "TRADE":
            return Decision.SELECTED
        return Decision.WATCHLIST

    @staticmethod
    def _why_selected(item: FinalAssessment) -> list[str]:
        reasons: list[str] = []
        if item.structure_state == "HH_HL_BUILDING":
            reasons.append("Higher highs and higher lows building")
        elif item.structure_state == "LH_LL_BUILDING":
            reasons.append("Lower highs and lower lows building")
        elif item.structure_state == "RANGE_COMPRESSION":
            reasons.append("Range compression near key level")
        if item.vwap_state == "ABOVE_HOLD":
            reasons.append("VWAP holding as support")
        elif item.vwap_state == "BELOW_REJECT":
            reasons.append("VWAP rejecting price from above")
        elif item.vwap_state == "VWAP_RECLAIMED":
            reasons.append("Clean VWAP reclaim")
        if item.level_tests >= 2:
            reasons.append(f"{item.level_tests} {item.level_test_quality.lower()} tests near trigger")
        if item.volume_state in {"BUILDING", "HEALTHY_BUILDUP"}:
            reasons.append("Healthy volume buildup")
        elif item.volume_state in {"EXPANDING", "EXPANDING_ON_PUSH", "CONFIRMED", "VOLUME_CONFIRMED"}:
            reasons.append("Volume expanding near trigger")
        if item.trap_risk == "LOW":
            reasons.append("Trap risk low")
        if item.execution_state == "TRADE":
            reasons.append("Execution trigger is active")
        return reasons[:5] or ["Best available setup after full validation"]

    @staticmethod
    def _what_must_happen(item: FinalAssessment) -> str:
        trigger = item.entry_high if item.side == Side.LONG else item.entry_low
        action = "through" if item.side == Side.LONG else "below"
        volume = "volume expansion" if item.volume_state not in {"CONFIRMED", "VOLUME_CONFIRMED"} else "continued volume confirmation"
        return f"{volume.title()} {action} {trigger:.2f}"

    @staticmethod
    def _why_not_higher(item: FinalAssessment, penalties: dict[str, float], components: dict[str, float]) -> str:
        if penalties:
            return max(penalties, key=penalties.get).capitalize()
        weakest = min(components, key=components.get)
        labels = {
            "prediction": "Prediction still needs cleaner confirmation",
            "execution": "Execution trigger is not fully ready",
            "structure": "Structure quality is not best-in-class",
            "level": "Level test memory is limited",
            "proximity": "Breakout proximity is weaker than better-ranked peers",
            "vwap": "VWAP behavior is not perfect",
            "volume": "Volume not yet confirmed",
            "market": "Market context is not fully aligned",
            "sector": "Sector support is limited",
            "rr": "Risk-reward is acceptable but not exceptional",
        }
        return labels.get(weakest, "Another candidate has cleaner institutional quality")

    @staticmethod
    def _why_ranked_here(item: FinalAssessment, rank: int, score: float, items: list[FinalAssessment]) -> str:
        leader = items[0] if items else item
        lag_bits: list[str] = []
        if rank == 1:
            return (
                "Ranked #1 because it has the strongest relative edge after structure, level tests, "
                "VWAP, volume, trap risk, and execution readiness were compared."
            )
        if item.level_tests < leader.level_tests:
            lag_bits.append(f"fewer level tests than #{1}")
        if item.volume_state != leader.volume_state:
            lag_bits.append(f"volume quality {item.volume_state} trails {leader.volume_state}")
        if item.structure_state != leader.structure_state:
            lag_bits.append(f"structure {item.structure_state} is less clean than {leader.structure_state}")
        if item.trap_risk != "LOW":
            lag_bits.append(f"trap risk is {item.trap_risk.lower()}")
        if item.execution_state != "TRADE" and leader.execution_state == "TRADE":
            lag_bits.append("execution is not trade-ready yet")
        if not lag_bits:
            lag_bits.append("slightly weaker relative edge on proximity, RR, or VWAP distance")
        return f"Ranked #{rank} with {score:.1f}/100 because " + "; ".join(lag_bits[:3]) + "."

    @staticmethod
    def _confidence_note(bucket: str, why_not_higher: str, why_ranked_here: str = "") -> str:
        note = f"Institutional selector bucket: {bucket}. Limiter: {why_not_higher}."
        if why_ranked_here:
            note = f"{note} {why_ranked_here}"
        return note
