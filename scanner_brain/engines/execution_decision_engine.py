from __future__ import annotations

from scanner_brain.core.enums import EntryType, Side
from scanner_brain.core.models import ExecutionAssessment, MarketContext, PredictionAssessment, StockSnapshot, TechnicalAssessment


class ExecutionDecisionEngine:
    """Separates tradability now from directional prediction quality."""

    def evaluate(
        self,
        stock: StockSnapshot,
        market: MarketContext,
        prediction: PredictionAssessment,
        technical: TechnicalAssessment,
        *,
        stop_loss: float,
        target1: float,
        target2: float,
        rr: float,
    ) -> ExecutionAssessment:
        direction = "LONG" if technical.side == Side.LONG else "SHORT"
        trigger_price = technical.resistance if technical.side == Side.LONG else technical.support
        volume_missing = any("volume" in item.lower() for item in technical.missing)
        poor_rr = rr < 1.2
        market_conflict = (
            technical.side == Side.LONG and market.market_bias == "bearish"
        ) or (
            technical.side == Side.SHORT and market.market_bias == "bullish"
        )
        breakout_ready = (
            prediction.status == "NEAR_BREAKOUT"
            and prediction.breakout_probability in {"MEDIUM", "HIGH"}
            and prediction.trap_risk != "HIGH"
            and technical.entry_type in {EntryType.IDEAL, EntryType.ACCEPTABLE}
        )

        warnings = []
        if volume_missing:
            warnings.append("Volume confirmation is missing.")
        if market_conflict:
            warnings.append("Market is not aligned.")
        if technical.entry_type == EntryType.CHASING or prediction.exhaustion_state == "CHASE_RISK_HIGH":
            warnings.append("Price is too far from VWAP.")
        if poor_rr:
            warnings.append("Risk reward is poor.")
        if prediction.trap_risk == "HIGH":
            warnings.append("Trap risk is high.")
        if prediction.status == "NO_SETUP":
            warnings.append("No setup is forming yet.")

        entry_quality = self._entry_quality(technical.entry_type, prediction)
        if technical.entry_type == EntryType.CHASING or poor_rr or prediction.trap_risk == "HIGH" or prediction.status in {"NO_SETUP", "EXHAUSTED"}:
            state = "AVOID"
        elif breakout_ready and not volume_missing and not market_conflict:
            state = "TRADE"
        else:
            state = "WAIT"

        grade = state
        entry_trigger = (
            f"Above {trigger_price:.2f} with volume"
            if technical.side == Side.LONG
            else f"Below {trigger_price:.2f} with volume"
        )
        invalidation = (
            f"Long idea fails if price loses VWAP or {stop_loss:.2f}."
            if technical.side == Side.LONG
            else f"Short idea fails if price reclaims VWAP or {stop_loss:.2f}."
        )
        avoid_reason = warnings[0] if state == "AVOID" and warnings else ""
        explanation = self._explanation(state, prediction, technical, trigger_price, warnings)
        activation_rules = [
            entry_trigger,
            "Stay on the right side of VWAP.",
            "Break candle should not instantly reverse.",
        ]
        if volume_missing:
            activation_rules.append("Wait for volume to improve before entry.")
        if prediction.exhaustion_state in {"EXTENDED", "CHASE_RISK_HIGH"}:
            activation_rules.append("Do not enter if the break is already extended from VWAP.")
        return ExecutionAssessment(
            state=state,
            direction=direction if state != "AVOID" else "NONE",
            grade=grade,
            entry_trigger=entry_trigger,
            entry_quality=entry_quality,
            stop_loss=round(stop_loss, 2),
            target1=round(target1, 2),
            target2=round(target2, 2),
            avoid_reason=avoid_reason,
            invalidation=invalidation,
            explanation=explanation,
            activation_rules=activation_rules,
            warnings=warnings,
        )

    @staticmethod
    def _entry_quality(entry_type: EntryType, prediction: PredictionAssessment) -> str:
        if entry_type == EntryType.IDEAL and prediction.exhaustion_state == "FRESH":
            return "IDEAL"
        if entry_type in {EntryType.IDEAL, EntryType.ACCEPTABLE} and prediction.exhaustion_state in {"FRESH", "ACCEPTABLE"}:
            return "ACCEPTABLE"
        if entry_type == EntryType.RISKY or prediction.exhaustion_state == "EXTENDED":
            return "RISKY"
        return "LATE"

    @staticmethod
    def _explanation(
        state: str,
        prediction: PredictionAssessment,
        technical: TechnicalAssessment,
        trigger_price: float,
        warnings: list[str],
    ) -> str:
        if state == "TRADE":
            return f"TRADE only on confirmed break of {trigger_price:.2f}; pressure is ready but the trigger must print with volume."
        if state == "WAIT":
            blocker = warnings[0] if warnings else "breakout confirmation is pending"
            return f"WAIT - setup is forming, but enter only on confirmed break of {trigger_price:.2f}. Blocker: {blocker.lower()}"
        reason = warnings[0] if warnings else technical.entry_reason
        return f"AVOID - execution quality is not clean now. Reason: {reason.lower()}"
