from __future__ import annotations

import unittest

from scanner_brain.config.scoring_profiles import ScoringProfile
from scanner_brain.core.enums import Bias, Decision, EntryType, Grade, MarketStateLabel, Side
from scanner_brain.core.models import FinalAssessment, MarketContext, MarketRegime, SectorAssessment
from scanner_brain.engines.final_selector_engine import FinalSelectorEngine


class FinalSelectorEngineTest(unittest.TestCase):
    @staticmethod
    def _market() -> MarketContext:
        return MarketContext(
            market_bias="bullish",
            market_strength=72.0,
            sector_support_map={},
            risk_state="risk-on",
            explanation="Bullish tape",
            reasons=["market supports longs"],
            regime=MarketRegime(MarketStateLabel.BULL, 72.0, Bias.BULLISH, ["market supports longs"]),
        )

    @staticmethod
    def _setup(symbol: str, **overrides) -> FinalAssessment:
        payload = dict(
            symbol=symbol,
            side=Side.LONG,
            final_score=70.0,
            grade=Grade.B,
            decision=Decision.WATCHLIST,
            setup_type="Institutional setup",
            entry_type=EntryType.ACCEPTABLE,
            entry_reason="Near trigger",
            passed=[],
            missing=[],
            failed=[],
            warnings=[],
            reasons=[],
            detected_patterns=[],
            confidence_note="",
            entry_low=100.0,
            entry_high=101.0,
            stop_loss=99.0,
            target1=102.2,
            target2=103.4,
            rr=1.7,
            invalidation_note="Invalid below VWAP or stop.",
            prediction_bias="BULLISH",
            prediction_strength=78.0,
            pre_breakout_status="NEAR_BREAKOUT",
            prediction_grade="A",
            breakout_probability="HIGH",
            trap_risk="LOW",
            structure_state="HH_HL_BUILDING",
            compression_state="TIGHT",
            pressure_state="BUYER_PRESSURE",
            vwap_state="ABOVE_HOLD",
            volume_state="BUILDING",
            exhaustion_state="FRESH",
            level_tests=3,
            level_test_quality="TIGHT",
            time_quality="OPENING",
            prediction_explanation="Pressure building under level with VWAP support.",
            key_level=101.0,
            execution_state="WAIT",
            execution_grade="WAIT",
            execution_direction="LONG",
            execution_entry_quality="ACCEPTABLE",
            execution_explanation="WAIT - trigger pending.",
            market_bias="bullish",
            market_strength=72.0,
            sector="Leaders",
        )
        payload.update(overrides)
        return FinalAssessment(**payload)

    def test_strong_wait_near_trigger_ranks_above_weak_single_test(self) -> None:
        strong = self._setup("STRONG")
        weak = self._setup(
            "WEAK",
            prediction_strength=62.0,
            breakout_probability="MEDIUM",
            structure_state="RANGE_COMPRESSION",
            compression_state="NONE",
            volume_state="WEAK",
            level_tests=1,
            level_test_quality="LOOSE",
            execution_entry_quality="RISKY",
        )
        selected, rejected = FinalSelectorEngine(ScoringProfile()).select(
            [weak, strong],
            market_context=self._market(),
            sectors={"Leaders": SectorAssessment("Leaders", 80.0, Bias.BULLISH, 1, [])},
            min_score=35,
        )

        self.assertEqual(selected[0].symbol, "STRONG")
        self.assertEqual(len(selected), 1)
        self.assertTrue(any(item["symbol"] == "WEAK" for item in rejected))
        self.assertEqual(selected[0].selection_bucket, "NEAR_TRIGGER")

    def test_chase_risk_candidate_is_filtered_before_top_five(self) -> None:
        chase = self._setup(
            "CHASE",
            execution_state="AVOID",
            execution_entry_quality="LATE",
            vwap_state="EXTENDED",
            exhaustion_state="CHASE_RISK_HIGH",
            trap_risk="HIGH",
        )
        selected, rejected = FinalSelectorEngine(ScoringProfile()).select(
            [chase],
            market_context=self._market(),
            sectors={"Leaders": SectorAssessment("Leaders", 80.0, Bias.BULLISH, 1, [])},
            min_score=35,
        )

        self.assertEqual(selected, [])
        self.assertTrue(any(item["symbol"] == "CHASE" for item in rejected))

    def test_trade_ready_clean_rr_gets_top_bucket(self) -> None:
        trade = self._setup(
            "TRADE",
            execution_state="TRADE",
            execution_grade="TRADE",
            execution_entry_quality="IDEAL",
            volume_state="CONFIRMED",
            rr=2.1,
        )
        selected, _ = FinalSelectorEngine(ScoringProfile()).select(
            [trade],
            market_context=self._market(),
            sectors={"Leaders": SectorAssessment("Leaders", 80.0, Bias.BULLISH, 1, [])},
            min_score=35,
        )

        self.assertEqual(selected[0].selection_bucket, "TRADE_READY")
        self.assertGreaterEqual(selected[0].final_selector_score, 78.0)

    def test_non_identical_similar_setups_get_distinct_scores_and_rank_reasons(self) -> None:
        setups = [
            self._setup("A", level_tests=3, volume_state="CONFIRMED", rr=1.9),
            self._setup("B", level_tests=3, volume_state="EXPANDING", rr=1.8),
            self._setup("C", level_tests=2, volume_state="BUILDING", rr=1.7),
            self._setup("D", level_tests=2, compression_state="MODERATE", rr=1.6),
            self._setup("E", level_tests=1, level_test_quality="LOOSE", volume_state="BUILDING", rr=1.5),
        ]
        selected, _ = FinalSelectorEngine(ScoringProfile()).select(
            setups,
            market_context=self._market(),
            sectors={"Leaders": SectorAssessment("Leaders", 80.0, Bias.BULLISH, 1, [])},
            min_score=35,
        )

        scores = [item.final_selector_score for item in selected]
        self.assertEqual(len(scores), len(set(scores)))
        self.assertGreater(scores[0], scores[-1])
        self.assertTrue(all(item.why_ranked_here for item in selected))
        self.assertIn("Ranked #1", selected[0].why_ranked_here)

    def test_truly_identical_setups_can_keep_identical_scores(self) -> None:
        selected, _ = FinalSelectorEngine(ScoringProfile()).select(
            [self._setup("TWIN1"), self._setup("TWIN2")],
            market_context=self._market(),
            sectors={"Leaders": SectorAssessment("Leaders", 80.0, Bias.BULLISH, 1, [])},
            min_score=35,
        )

        self.assertEqual(selected[0].final_selector_score, selected[1].final_selector_score)

    def test_snapshot_fallback_with_degraded_data_does_not_fill_top_picks(self) -> None:
        degraded = self._setup(
            "DEGRADED",
            snapshot_mode=True,
            missing=["live volume unavailable"],
            prediction_warnings=["Snapshot mode: candle memory is missing."],
        )
        selected, rejected = FinalSelectorEngine(ScoringProfile()).select(
            [degraded],
            market_context=self._market(),
            sectors={"Leaders": SectorAssessment("Leaders", 80.0, Bias.BULLISH, 1, [])},
            min_score=35,
        )

        self.assertEqual(selected, [])
        self.assertTrue(any(item["symbol"] == "DEGRADED" for item in rejected))
        self.assertTrue(any(item["symbol"] == "MARKET" for item in rejected))

    def test_all_wait_selection_reports_no_trade_ready_confirmation(self) -> None:
        selected, rejected = FinalSelectorEngine(ScoringProfile()).select(
            [self._setup("WAIT1"), self._setup("WAIT2", level_tests=2, volume_state="EXPANDING")],
            market_context=self._market(),
            sectors={"Leaders": SectorAssessment("Leaders", 80.0, Bias.BULLISH, 1, [])},
            min_score=35,
        )

        self.assertTrue(selected)
        self.assertTrue(all(item.execution_state == "WAIT" for item in selected))
        self.assertTrue(any("no trade-ready confirmation" in item["reason"] for item in rejected))


if __name__ == "__main__":
    unittest.main()
