from __future__ import annotations

import pandas as pd

from scanner_brain.core.enums import Decision, Grade, Side
from scanner_brain.core.models import FinalAssessment, ScanResult, StockSnapshot


class TradeOutputEngine:
    def to_dataframe(self, result: ScanResult, snapshots: dict[str, StockSnapshot]) -> pd.DataFrame:
        rows = []
        for rank, setup in enumerate(result.setups, start=1):
            stock = snapshots.get(setup.symbol, StockSnapshot(setup.symbol))
            action = self._action(setup)
            execution_status = setup.execution_state or self._execution_status(setup)
            trade_direction = setup.execution_direction or ("LONG" if setup.side == Side.LONG else "SHORT")
            execution_headline = self._execution_headline(setup, execution_status, trade_direction)
            trader_logic = self._trader_logic(setup, stock)
            activation_rules = self._activation_rules(setup, stock)
            pre_trade_note = self._pre_trade_note(setup, execution_status, activation_rules)
            rows.append(
                {
                    "rank": rank,
                    "symbol": setup.symbol,
                    "name": stock.name or setup.symbol,
                    "sector": stock.sector,
                    "ltp": round(stock.ltp, 2),
                    "direction": setup.side.value,
                    "side": setup.side.value,
                    "action": action,
                    "market_bias": setup.market_bias,
                    "market_strength": setup.market_strength,
                    "risk_state": setup.risk_state,
                    "market_explanation": setup.market_explanation,
                    "prediction_bias": setup.prediction_bias,
                    "prediction_strength": setup.prediction_strength,
                    "final_selector_score": setup.final_selector_score,
                    "selection_bucket": setup.selection_bucket,
                    "conviction_label": setup.conviction_label,
                    "positive_count": setup.positive_count,
                    "negative_count": setup.negative_count,
                    "neutral_count": setup.neutral_count,
                    "pass_count": setup.pass_count,
                    "fail_count": setup.fail_count,
                    "conflict_score": setup.conflict_score,
                    "hard_blocks": setup.hard_blocks,
                    "boosters": setup.boosters,
                    "major_passes": setup.major_passes,
                    "major_failures": setup.major_failures,
                    "factor_heatmap": setup.scorecard.factor_heatmap if setup.scorecard else {},
                    "group_scores": {
                        key: {
                            "score": value.score,
                            "weight": value.weight,
                            "weighted_points": value.weighted_points,
                            "positive": value.positive,
                            "negative": value.negative,
                            "neutral": value.neutral,
                            "passes": value.passes,
                            "failures": value.failures,
                            "summary": value.summary,
                        }
                        for key, value in (setup.scorecard.group_scores.items() if setup.scorecard else [])
                    },
                    "score_drift": setup.scorecard.score_drift if setup.scorecard else 0.0,
                    "signal_stability": setup.scorecard.signal_stability if setup.scorecard else "fresh",
                    "live_conviction_change": setup.scorecard.live_conviction_change if setup.scorecard else "new",
                    "prediction_grade": setup.prediction_grade,
                    "pre_breakout_status": setup.pre_breakout_status,
                    "breakout_probability": setup.breakout_probability,
                    "trap_risk": setup.trap_risk,
                    "structure_state": setup.structure_state,
                    "compression_state": setup.compression_state,
                    "pressure_state": setup.pressure_state,
                    "vwap_state": setup.vwap_state,
                    "volume_state": setup.volume_state,
                    "exhaustion_state": setup.exhaustion_state,
                    "level_tests": setup.level_tests,
                    "level_test_quality": setup.level_test_quality,
                    "time_quality": setup.time_quality,
                    "prediction_explanation": setup.prediction_explanation,
                    "key_level": setup.key_level,
                    "pressure_side": setup.pressure_side,
                    "ideal_scenario": setup.ideal_scenario,
                    "invalid_scenario": setup.invalid_scenario,
                    "why_selected": setup.why_selected,
                    "what_must_happen": setup.what_must_happen,
                    "why_not_higher": setup.why_not_higher,
                    "why_ranked_here": setup.why_ranked_here,
                    "preparation_signals": setup.preparation_signals,
                    "prediction_warnings": setup.prediction_warnings,
                    "trade_status": execution_status,
                    "trade_direction": trade_direction,
                    "execution_grade": setup.execution_grade,
                    "execution_state": execution_status,
                    "execution_explanation": setup.execution_explanation,
                    "execution_headline": execution_headline,
                    "entry_quality": setup.execution_entry_quality,
                    "avoid_reason": setup.avoid_reason,
                    "entry_type": setup.entry_type.value,
                    "entry_reason": setup.entry_reason,
                    "pre_trade_note": pre_trade_note,
                    "grade": setup.grade.value,
                    "confidence": setup.final_score,
                    "final_score": setup.final_score,
                    "setup_type": setup.setup_type,
                    "entry_low": setup.entry_low,
                    "entry_high": setup.entry_high,
                    "stop_loss": setup.stop_loss,
                    "target1": setup.target1,
                    "target2": setup.target2,
                    "rr": setup.rr,
                    "trailing_note": "After T1, trail using VWAP/open proxy and latest swing.",
                    "trend": "Bullish" if setup.side == Side.LONG else "Bearish",
                    "vwap_side": "Context supportive" if "VWAP/open proxy supportive" in setup.passed else "Context weak",
                    "volume_spike": 1.0 if "volume confirmation present" in setup.passed else 0.5,
                    "vwap": round(stock.vwap_proxy, 2),
                    "open": round(stock.open, 2),
                    "day_high": round(stock.high, 2),
                    "day_low": round(stock.low, 2),
                    "prev_close": round(stock.prev_close, 2),
                    "live_change": round(stock.ltp - stock.prev_close, 2) if stock.prev_close else 0.0,
                    "live_change_pct": round(stock.change_pct, 2),
                    "patterns": ", ".join(setup.detected_patterns) if setup.detected_patterns else "None",
                    "passed_factors": setup.passed,
                    "validation_factors": setup.validation_factors,
                    "missing_factors": setup.missing,
                    "failed_factors": setup.failed,
                    "contradictions": setup.contradictions,
                    "invalidation_note": setup.invalidation_note,
                    "confidence_note": setup.confidence_note,
                    "remarks": self._remarks(setup),
                    "reasons": setup.reasons,
                    "trader_logic": trader_logic,
                    "activation_rules": activation_rules,
                    "validation_summary": self._validation_summary(setup),
                    "cautions": [setup.entry_reason] + setup.warnings + setup.missing[:3] + [setup.invalidation_note],
                    "vwap_distance_pct": setup.vwap_distance_pct,
                    "vwap_distance_atr": setup.vwap_distance_atr,
                    "snapshot_mode": setup.snapshot_mode,
                    "scan_stats": f"{result.stats.scanned} scanned | {result.stats.shortlisted} shortlisted | {result.stats.elapsed_ms:.0f} ms",
                }
            )
        return pd.DataFrame(rows)

    @staticmethod
    def _action(setup: FinalAssessment) -> str:
        prefix = "BUY" if setup.side == Side.LONG else "SELL"
        if setup.prediction_grade == "D" or setup.entry_type.value == "CHASING" or setup.grade == Grade.REJECT:
            return f"AVOID {prefix}"
        if setup.prediction_grade == "A+":
            return f"STRONG {prefix}"
        if setup.prediction_grade == "A":
            return f"WATCH {prefix} PREP"
        return f"WATCH FOR {prefix}"

    @staticmethod
    def _execution_status(setup: FinalAssessment) -> str:
        if setup.entry_type.value == "CHASING":
            return "AVOID"
        if setup.grade in {Grade.A_PLUS, Grade.A} and not setup.failed and len(setup.warnings) <= 2:
            return "TRADE"
        if setup.grade == Grade.REJECT or len(setup.failed) >= 3:
            return "AVOID"
        return "WAIT"

    @staticmethod
    def _execution_headline(setup: FinalAssessment, status: str, trade_direction: str) -> str:
        if status == "TRADE":
            return f"{trade_direction} TRADE | {setup.entry_type.value} ENTRY | {setup.execution_grade}"
        if status == "WAIT":
            return f"WAIT FOR {trade_direction} | {setup.entry_type.value} ENTRY | {setup.pre_breakout_status.upper()}"
        return f"AVOID {trade_direction} | {setup.entry_type.value} ENTRY"

    @staticmethod
    def _trader_logic(setup: FinalAssessment, stock: StockSnapshot) -> list[str]:
        vwap = stock.vwap_proxy
        logic = [
            setup.prediction_explanation or ("Price above VWAP -> buyers in control." if stock.ltp >= vwap else "Price below VWAP -> sellers in control."),
            f"Execution: {setup.execution_explanation or setup.entry_reason}",
            f"Sequence: {setup.structure_state}, {setup.pressure_state}, VWAP {setup.vwap_state}, volume {setup.volume_state}.",
        ]
        if setup.side == Side.LONG:
            logic.append(f"Long only if resistance breaks without stretching away from VWAP {vwap:.2f}.")
            logic.append(f"If price loses VWAP or {setup.stop_loss:.2f}, long thesis fails.")
        else:
            logic.append(f"Short only if support breaks without stretching away from VWAP {vwap:.2f}.")
            logic.append(f"If price reclaims VWAP or {setup.stop_loss:.2f}, short thesis fails.")
        if "volume confirmation present" in setup.passed:
            logic.append("Volume confirms the move -> better quality setup.")
        elif any("volume" in item.lower() for item in setup.missing):
            logic.append("Volume not fully confirmed -> wait, do not chase.")
        if setup.entry_type.value == "CHASING":
            logic.append("Move is extended from VWAP -> reject and wait for pullback.")
        elif setup.exhaustion_state in {"EXTENDED", "CHASE_RISK_HIGH"}:
            logic.append("Move is late from VWAP -> avoid fresh entries until price resets.")
        elif setup.failed:
            logic.append(f"Problem: {setup.failed[0]} -> avoid until fixed.")
        elif setup.prediction_grade == "A+":
            logic.append("Preparation is strong -> this is a top watchlist name.")
        elif setup.prediction_grade == "A":
            logic.append("Pressure is building -> wait for trigger before entry.")
        else:
            logic.append("Weak setup -> watch only.")
        return logic

    @staticmethod
    def _activation_rules(setup: FinalAssessment, stock: StockSnapshot) -> list[str]:
        vwap = stock.vwap_proxy
        if setup.side == Side.LONG:
            if setup.entry_type.value == "CHASING":
                return [
                    "Wait for pullback to VWAP before entry.",
                    f"Enter only if price later breaks {setup.entry_high:.2f} while still holding close to VWAP {vwap:.2f}.",
                ]
            rules = [
                f"Enter ONLY IF price breaks {setup.entry_high:.2f}.",
                f"Price must stay close to or reclaim VWAP near {vwap:.2f} before entry.",
            ]
        else:
            if setup.entry_type.value == "CHASING":
                return [
                    "Wait for pullback to VWAP before short entry.",
                    f"Enter only if price later breaks {setup.entry_low:.2f} while still holding close to VWAP {vwap:.2f}.",
                ]
            rules = [
                f"Enter ONLY IF price breaks {setup.entry_low:.2f}.",
                f"Price must stay close to or reject from VWAP near {vwap:.2f} before entry.",
            ]
        if any("volume" in item.lower() for item in setup.missing):
            rules.append("Volume improves before entry.")
        else:
            rules.append("Breakout/breakdown candle does not instantly reverse.")
        return rules

    @staticmethod
    def _validation_summary(setup: FinalAssessment) -> str:
        passed = len(setup.passed)
        missing = len(setup.missing)
        failed = len(setup.failed)
        return (
            f"{setup.positive_count}+ / {setup.negative_count}- / {setup.neutral_count} neutral | "
            f"Prediction {setup.prediction_grade} {setup.pre_breakout_status} | "
            f"Breakout {setup.breakout_probability} | Trap {setup.trap_risk} | "
            f"Tests {setup.level_tests} {setup.level_test_quality}"
        )

    @staticmethod
    def _pre_trade_note(setup: FinalAssessment, status: str, activation_rules: list[str]) -> str:
        if status == "TRADE":
            return f"{setup.entry_type.value} entry. Execute only if {activation_rules[0].lower()}"
        if status == "AVOID":
            return f"Avoid now: {setup.entry_reason}"
        blocker = setup.missing[0] if setup.missing else "trigger is still pending"
        if setup.entry_type.value == "RISKY":
            return "Wait for pullback to VWAP before entry."
        return f"{setup.prediction_bias.title()} setup, but wait: {blocker}."

    @staticmethod
    def _remarks(setup: FinalAssessment) -> str:
        parts = [setup.prediction_grade, setup.execution_state, setup.entry_type.value, setup.setup_type]
        if setup.detected_patterns:
            parts.append("Patterns: " + ", ".join(setup.detected_patterns[:2]))
        if any("snapshot-mode" in item or "live volume unavailable" in item for item in setup.missing):
            parts.append("Snapshot fallback: live volume unavailable")
        parts.append(setup.prediction_explanation or setup.entry_reason)
        parts.append(setup.execution_explanation or setup.entry_reason)
        return " | ".join(parts)
