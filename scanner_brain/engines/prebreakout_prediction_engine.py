from __future__ import annotations

from scanner_brain.core.enums import Bias, Side
from scanner_brain.core.models import (
    MarketContext,
    PatternAssessment,
    PredictionAssessment,
    SectorAssessment,
    StockSnapshot,
    TechnicalAssessment,
)
from scanner_brain.engines.candle_sequence_engine import CandleSequenceAssessment, CandleSequenceEngine


class PreBreakoutPredictionEngine:
    """Prediction answers one question only: is a professional setup forming?"""

    def __init__(self) -> None:
        self.sequence_engine = CandleSequenceEngine()

    def evaluate(
        self,
        stock: StockSnapshot,
        market: MarketContext,
        sector: SectorAssessment | None,
        technical: TechnicalAssessment,
        pattern: PatternAssessment,
    ) -> PredictionAssessment:
        sequence = self.sequence_engine.analyze(
            stock,
            side=technical.side,
            reference_level=technical.resistance if technical.side == Side.LONG else technical.support,
            atr_proxy=technical.atr_proxy,
        )
        bias = self._bias(technical.side, sequence)
        score = self._base_score(sequence, technical.side)
        signals, warnings, contradictions = self._reason_trail(
            sequence=sequence,
            side=technical.side,
            sector=sector,
            pattern=pattern,
        )

        score += self._market_points(technical.side, market)
        score += self._sector_points(technical.side, sector, warnings)
        score += min(pattern.score_adjustment, 5.0)
        score -= self._mandatory_penalties(sequence, sector, technical, warnings)

        if bias == "NEUTRAL":
            score = min(score, 54.0)
        score = max(0.0, min(100.0, score))

        trap_risk = sequence.trap_risk
        if score < 55 and trap_risk == "LOW" and sequence.trap_flags:
            trap_risk = "MEDIUM"
        breakout_probability = self._probability(score, sequence)
        status = self._status(score, breakout_probability, trap_risk, sequence.exhaustion_state)
        if status == "NO_SETUP":
            bias = "NEUTRAL"
        grade = self._grade(score, status, trap_risk, sequence)
        explanation = self._explanation(bias, sequence, technical.side)
        ideal_scenario = self._ideal_scenario(bias, sequence)
        invalid_scenario = self._invalid_scenario(bias, sequence)

        validation_factors = [
            f"Structure {sequence.structure_state}",
            f"Compression {sequence.compression_state}",
            f"Pressure {sequence.pressure_state}",
            f"VWAP {sequence.vwap_state}",
            f"Volume {sequence.volume_state}",
            f"Level tests {sequence.level_test_count} {sequence.level_test_quality}",
            f"Exhaustion {sequence.exhaustion_state}",
            f"Time {sequence.time_context}",
        ]
        if sequence.snapshot_mode:
            validation_factors.append("Snapshot mode penalty applied")

        return PredictionAssessment(
            bias=bias,
            strength=round(score, 1),
            status=status,
            grade=grade,
            breakout_probability=breakout_probability,
            trap_risk=trap_risk,
            structure_state=sequence.structure_state,
            compression_state=sequence.compression_state,
            pressure_state=sequence.pressure_state,
            vwap_state=sequence.vwap_state,
            volume_state=sequence.volume_state,
            exhaustion_state=sequence.exhaustion_state,
            level_tests=sequence.level_test_count,
            level_test_quality=sequence.level_test_quality,
            time_quality=sequence.time_context,
            explanation=explanation,
            key_level=sequence.key_level,
            pressure_side="UNDER_RESISTANCE" if technical.side == Side.LONG else "ABOVE_SUPPORT",
            ideal_scenario=ideal_scenario,
            invalid_scenario=invalid_scenario,
            preparation_signals=signals[:8],
            contradictions=(contradictions + technical.contradictions + pattern.contradictions)[:8],
            validation_factors=validation_factors,
            warnings=(warnings + sequence.trap_flags)[:8],
            snapshot_mode=sequence.snapshot_mode,
        )

    @staticmethod
    def _bias(side: Side, sequence: CandleSequenceAssessment) -> str:
        if sequence.exhaustion_state == "CHASE_RISK_HIGH" or sequence.trap_risk == "HIGH":
            return "NEUTRAL"
        if sequence.snapshot_mode:
            if side == Side.LONG and sequence.vwap_state == "ABOVE_HOLD":
                return "BULLISH"
            if side == Side.SHORT and sequence.vwap_state == "BELOW_REJECT":
                return "BEARISH"
        bullish_states = {"HH_HL_BUILDING", "EXPANSION_UP", "RANGE_COMPRESSION"}
        bearish_states = {"LH_LL_BUILDING", "EXPANSION_DOWN", "RANGE_COMPRESSION"}
        bullish_pressure = sequence.pressure_state in {"BUYER_PRESSURE", "MOMENTUM", "ABSORPTION"}
        bearish_pressure = sequence.pressure_state in {"SELLER_PRESSURE", "MOMENTUM", "ABSORPTION"}
        if side == Side.LONG and sequence.structure_state in bullish_states and bullish_pressure:
            return "BULLISH"
        if side == Side.SHORT and sequence.structure_state in bearish_states and bearish_pressure:
            return "BEARISH"
        return "NEUTRAL"

    @staticmethod
    def _base_score(sequence: CandleSequenceAssessment, side: Side) -> float:
        if sequence.snapshot_mode:
            score = 86.0
            if sequence.vwap_state in {"ABOVE_HOLD", "BELOW_REJECT"}:
                score += 4.0
            if sequence.pressure_state in {"BUYER_PRESSURE", "SELLER_PRESSURE"}:
                score += 3.0
            return score
        score = 34.0
        directional_structure = (
            side == Side.LONG and sequence.structure_state in {"HH_HL_BUILDING", "EXPANSION_UP"}
        ) or (
            side == Side.SHORT and sequence.structure_state in {"LH_LL_BUILDING", "EXPANSION_DOWN"}
        )
        if directional_structure:
            score += 18.0
        elif sequence.structure_state == "RANGE_COMPRESSION":
            score += 10.0
        elif sequence.structure_state == "CHOPPY":
            score -= 8.0

        if sequence.compression_state == "TIGHT":
            score += 13.0
        elif sequence.compression_state == "MODERATE":
            score += 7.0

        if sequence.level_test_count >= 3 and sequence.level_test_quality == "TIGHT":
            score += 16.0
        elif sequence.level_test_count >= 2:
            score += 10.0
        elif sequence.level_test_count == 1:
            score += 3.0

        if sequence.vwap_state in {"ABOVE_HOLD", "BELOW_REJECT", "VWAP_RECLAIMED"}:
            score += 10.0
        elif sequence.vwap_state == "VWAP_CHOPPY":
            score -= 8.0
        elif sequence.vwap_state == "EXTENDED":
            score -= 6.0

        if sequence.pressure_state == "MOMENTUM":
            score += 11.0
        elif sequence.pressure_state in {"BUYER_PRESSURE", "SELLER_PRESSURE", "ABSORPTION"}:
            score += 8.0
        elif sequence.pressure_state == "REJECTION_HEAVY":
            score -= 12.0

        if sequence.volume_state == "CONFIRMED":
            score += 12.0
        elif sequence.volume_state in {"EXPANDING", "BUILDING"}:
            score += 8.0
        elif sequence.volume_state == "DRY_COMPRESSION":
            score += 6.0
        elif sequence.volume_state == "WEAK":
            score -= 8.0

        if sequence.exhaustion_state == "FRESH":
            score += 6.0
        elif sequence.exhaustion_state == "EXTENDED":
            score -= 10.0
        elif sequence.exhaustion_state == "CHASE_RISK_HIGH":
            score -= 22.0

        if sequence.time_context == "OPENING":
            score += 3.0
        elif sequence.time_context == "LATE":
            score -= 5.0
        return score

    @staticmethod
    def _market_points(side: Side, market: MarketContext) -> float:
        if side == Side.LONG and market.market_bias == "bullish":
            return 5.0
        if side == Side.SHORT and market.market_bias == "bearish":
            return 5.0
        if market.market_bias == "neutral":
            return 0.0
        return -7.0

    @staticmethod
    def _sector_points(side: Side, sector: SectorAssessment | None, warnings: list[str]) -> float:
        if sector is None:
            warnings.append("Sector read is limited.")
            return -5.0
        if sector.bias == Bias.NEUTRAL:
            warnings.append("Sector is neutral, so confidence is capped lower.")
            return -5.0
        if side == Side.LONG and sector.bias == Bias.BULLISH:
            return 5.0
        if side == Side.SHORT and sector.bias == Bias.BEARISH:
            return 5.0
        warnings.append("Sector is fighting the setup.")
        return -8.0

    @staticmethod
    def _mandatory_penalties(
        sequence: CandleSequenceAssessment,
        sector: SectorAssessment | None,
        technical: TechnicalAssessment,
        warnings: list[str],
    ) -> float:
        penalty = 0.0
        if sequence.snapshot_mode:
            penalty += 15.0
            warnings.append("Snapshot mode: candle memory is missing.")
        if sequence.volume_state == "WEAK" or sequence.relative_volume <= 0:
            penalty += 10.0
            warnings.append("Volume confirmation is missing.")
        if sequence.structure_state in {"CHOPPY", "RANGE_COMPRESSION"} and sequence.compression_state == "NONE":
            penalty += 10.0
            warnings.append("Structure is weak, not a clean sequence.")
        if sector is None or sector.bias == Bias.NEUTRAL:
            penalty += 5.0
        if sequence.vwap_state == "EXTENDED" or sequence.exhaustion_state in {"EXTENDED", "CHASE_RISK_HIGH"}:
            penalty += 10.0
            warnings.append("Price is extended from VWAP.")
        if sequence.level_test_count == 1:
            penalty += 5.0
            warnings.append("Only one level test, so breakout memory is thin.")
        if sequence.trap_risk == "HIGH":
            penalty += 15.0
            warnings.append("High trap risk detected.")
        if any("live volume unavailable" in item.lower() for item in technical.missing):
            penalty += 10.0
        return penalty

    @staticmethod
    def _reason_trail(
        *,
        sequence: CandleSequenceAssessment,
        side: Side,
        sector: SectorAssessment | None,
        pattern: PatternAssessment,
    ) -> tuple[list[str], list[str], list[str]]:
        side_word = "resistance" if side == Side.LONG else "support"
        signals: list[str] = []
        warnings: list[str] = []
        contradictions: list[str] = []
        if sequence.compression_state in {"TIGHT", "MODERATE"}:
            signals.append(f"{sequence.compression_state.title()} compression is forming near {side_word}.")
        if sequence.level_test_count >= 3 and sequence.level_test_quality == "TIGHT":
            signals.append(f"Three tight tests at {sequence.key_level:.2f} show level memory is building.")
        elif sequence.level_test_count:
            signals.append(f"{sequence.level_test_count} tests recorded near {sequence.key_level:.2f}.")
        if sequence.pressure_state in {"BUYER_PRESSURE", "SELLER_PRESSURE", "ABSORPTION", "MOMENTUM"}:
            signals.append(f"Pressure tape reads {sequence.pressure_state}.")
        if sequence.vwap_state in {"ABOVE_HOLD", "BELOW_REJECT", "VWAP_RECLAIMED"}:
            signals.append(f"VWAP state is supportive: {sequence.vwap_state}.")
        if sequence.volume_state in {"DRY_COMPRESSION", "BUILDING", "EXPANDING", "CONFIRMED"}:
            signals.append(f"Volume state is {sequence.volume_state}.")
        if pattern.detected:
            signals.append("Pattern confluence: " + ", ".join(pattern.detected[:2]) + ".")
        if sector is not None and sector.reasons:
            signals.append(sector.reasons[0])
        if sequence.pressure_state == "REJECTION_HEAVY":
            contradictions.append("Repeated wick rejection is blocking the setup.")
        if sequence.trap_flags:
            warnings.extend(sequence.trap_flags)
        return signals, warnings, contradictions

    @staticmethod
    def _probability(score: float, sequence: CandleSequenceAssessment) -> str:
        if (
            score >= 74
            and sequence.level_test_count >= 3
            and sequence.level_test_quality == "TIGHT"
            and sequence.trap_risk != "HIGH"
        ):
            return "HIGH"
        if score >= 55 and sequence.trap_risk != "HIGH":
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _status(score: float, probability: str, trap_risk: str, exhaustion: str) -> str:
        if exhaustion in {"EXTENDED", "CHASE_RISK_HIGH"} or trap_risk == "HIGH":
            return "EXHAUSTED"
        if probability == "HIGH" and score >= 70:
            return "NEAR_BREAKOUT"
        if score >= 55:
            return "BUILDING"
        return "NO_SETUP"

    @staticmethod
    def _grade(score: float, status: str, trap_risk: str, sequence: CandleSequenceAssessment) -> str:
        clean = (
            not sequence.snapshot_mode
            and trap_risk == "LOW"
            and sequence.exhaustion_state in {"FRESH", "ACCEPTABLE"}
            and sequence.volume_state in {"BUILDING", "EXPANDING", "CONFIRMED", "DRY_COMPRESSION"}
            and sequence.level_test_count >= 2
        )
        if score >= 85 and clean and status in {"NEAR_BREAKOUT", "BUILDING"}:
            return "A+"
        if score >= 70 and status in {"NEAR_BREAKOUT", "BUILDING"}:
            return "A"
        if score >= 55:
            return "B"
        if score >= 45:
            return "C"
        return "D"

    @staticmethod
    def _explanation(bias: str, sequence: CandleSequenceAssessment, side: Side) -> str:
        if bias == "NEUTRAL":
            return (
                f"No clean trade preparation: structure is {sequence.structure_state}, "
                f"VWAP is {sequence.vwap_state}, trap risk is {sequence.trap_risk}."
            )
        level_word = "resistance" if side == Side.LONG else "support"
        pressure = "buyers" if bias == "BULLISH" else "sellers"
        return (
            f"{pressure.title()} are building pressure under {level_word} {sequence.key_level:.2f}; "
            f"{sequence.level_test_count} {sequence.level_test_quality.lower()} tests, "
            f"{sequence.compression_state.lower()} compression, VWAP {sequence.vwap_state}, "
            f"volume {sequence.volume_state.lower()}."
        )

    @staticmethod
    def _ideal_scenario(bias: str, sequence: CandleSequenceAssessment) -> str:
        if bias == "BULLISH":
            return (
                f"Ideal: hold VWAP, keep compressing below {sequence.key_level:.2f}, "
                "then break with expanding/confirmed volume without a long upper wick."
            )
        if bias == "BEARISH":
            return (
                f"Ideal: reject VWAP, keep compressing above {sequence.key_level:.2f}, "
                "then break with expanding/confirmed volume without a long lower wick."
            )
        return "Ideal: wait for tighter level memory, directional pressure, and clean VWAP behavior."

    @staticmethod
    def _invalid_scenario(bias: str, sequence: CandleSequenceAssessment) -> str:
        if bias == "BULLISH":
            return (
                f"Invalid if price loses VWAP/support {sequence.support:.2f}, "
                f"prints rejection above {sequence.key_level:.2f}, or becomes extended."
            )
        if bias == "BEARISH":
            return (
                f"Invalid if price reclaims VWAP/resistance {sequence.resistance:.2f}, "
                f"fails below {sequence.key_level:.2f}, or becomes extended."
            )
        return "Invalid until structure, VWAP, volume, and level tests align cleanly."
