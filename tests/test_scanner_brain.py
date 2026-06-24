from __future__ import annotations

import unittest

import pandas as pd

from scanner_brain.core.enums import Bias, EntryType, MarketStateLabel, Side
from scanner_brain.config.scoring_profiles import ScoringProfile
from scanner_brain.core.models import MarketContext, MarketRegime, PatternAssessment, StockSnapshot, TechnicalAssessment
from scanner_brain.engines.alignment_scoring_engine import AlignmentScoringEngine
from scanner_brain.engines.prebreakout_prediction_engine import PreBreakoutPredictionEngine
from scanner_brain.engines.technical_validation_engine import TechnicalValidationEngine
from scanner_brain.services.scanner_service import ScannerBrainService


class ScannerBrainServiceTest(unittest.TestCase):
    @staticmethod
    def _market_context(bias: Bias = Bias.BULLISH) -> MarketContext:
        return MarketContext(
            market_bias="bullish" if bias == Bias.BULLISH else "bearish" if bias == Bias.BEARISH else "neutral",
            market_strength=68.0 if bias == Bias.BULLISH else 34.0 if bias == Bias.BEARISH else 50.0,
            sector_support_map={},
            risk_state="risk-on" if bias == Bias.BULLISH else "risk-off" if bias == Bias.BEARISH else "neutral",
            explanation="Market context ready",
            reasons=["test"],
            regime=MarketRegime(MarketStateLabel.BULL if bias == Bias.BULLISH else MarketStateLabel.BEAR if bias == Bias.BEARISH else MarketStateLabel.NEUTRAL, 60.0, bias, ["test"]),
        )

    @staticmethod
    def _pattern() -> PatternAssessment:
        return PatternAssessment(detected=[], bias=Bias.NEUTRAL, score_adjustment=0.0, reasons=[])

    def test_scan_returns_ranked_top_setups_and_rejections(self) -> None:
        candles = pd.DataFrame(
            [
                {"datetime": f"2026-04-18 09:{15 + i:02d}:00", "open": o, "high": h, "low": l, "close": c, "volume": v}
                for i, (o, h, l, c, v) in enumerate(
                    [
                        (100.2, 100.8, 99.9, 100.4, 1100),
                        (100.4, 101.0, 100.1, 100.8, 1150),
                        (100.7, 101.2, 100.4, 101.0, 1180),
                        (100.9, 101.3, 100.6, 101.1, 1220),
                        (101.0, 101.4, 100.8, 101.25, 1260),
                        (101.15, 101.45, 100.95, 101.3, 1340),
                        (101.2, 101.48, 101.0, 101.38, 1420),
                        (101.3, 101.5, 101.08, 101.42, 1500),
                    ]
                )
            ]
        )
        quotes = pd.DataFrame(
            [
                {
                    "symbol": "RELIANCE",
                    "ltp": 101.42,
                    "open": 100.2,
                    "high": 101.5,
                    "low": 99.9,
                    "prev_close": 99.8,
                    "volume": 900000,
                    "change_pct": 1.62,
                    "raw": {"candles": candles, "vwap": 100.95},
                },
                {
                    "symbol": "INFY",
                    "ltp": 1450,
                    "open": 1470,
                    "high": 1478,
                    "low": 1444,
                    "prev_close": 1485,
                    "volume": 700000,
                    "change_pct": -2.35,
                },
                {
                    "symbol": "TCS",
                    "ltp": 3900,
                    "open": 3890,
                    "high": 3910,
                    "low": 3860,
                    "prev_close": 3885,
                    "volume": 100000,
                    "change_pct": 0.38,
                },
            ]
        )
        universe = pd.DataFrame(
            [
                {"symbol": "RELIANCE", "name": "Reliance", "sector": "Energy"},
                {"symbol": "INFY", "name": "Infosys", "sector": "IT"},
                {"symbol": "TCS", "name": "TCS", "sector": "IT"},
            ]
        )
        market = pd.DataFrame(
            [
                {"symbol": "NIFTY", "label": "NIFTY", "is_index": True, "ltp": 22600, "change_pct": 0.45, "prev_close": 22500},
                {"symbol": "BANKNIFTY", "label": "BANKNIFTY", "is_index": True, "ltp": 48200, "change_pct": 0.35, "prev_close": 48000},
            ]
        )

        ranked, rejected, result = ScannerBrainService().scan(
            quotes=quotes,
            universe=universe,
            market_frame=market,
            min_score=35,
        )

        self.assertLessEqual(len(ranked), 5)
        self.assertIn("final_selector_score", ranked.columns)
        self.assertIn("why_selected", ranked.columns)
        self.assertEqual(ranked.iloc[0]["symbol"], "RELIANCE")
        self.assertNotEqual(ranked.iloc[0]["selection_bucket"], "RISKY")
        self.assertTrue(any(item.get("symbol") == "TCS" for item in rejected.to_dict("records")))
        self.assertEqual(result.stats.scanned, 3)
        self.assertEqual(result.stats.shortlisted, 2)
        self.assertIsNotNone(result.market_context)

    def test_prediction_engine_detects_bullish_pressure_from_candle_sequence(self) -> None:
        candles = pd.DataFrame(
            [
                {"datetime": f"2026-04-18 09:{15 + i:02d}:00", "open": o, "high": h, "low": l, "close": c, "volume": v}
                for i, (o, h, l, c, v) in enumerate(
                    [
                        (100.2, 100.8, 99.9, 100.4, 1100),
                        (100.4, 101.0, 100.1, 100.8, 1150),
                        (100.7, 101.2, 100.4, 101.0, 1180),
                        (100.9, 101.3, 100.6, 101.1, 1220),
                        (101.0, 101.4, 100.8, 101.25, 1260),
                        (101.15, 101.45, 100.95, 101.3, 1340),
                        (101.2, 101.48, 101.0, 101.38, 1420),
                        (101.3, 101.5, 101.08, 101.42, 1500),
                    ]
                )
            ]
        )
        stock = StockSnapshot(
            symbol="BUILD",
            ltp=101.42,
            open=100.2,
            high=101.5,
            low=99.9,
            prev_close=99.8,
            volume=1500,
            change_pct=1.62,
            raw={"candles": candles, "vwap": 100.95},
        )
        technical = TechnicalAssessment(
            side=Side.LONG,
            setup_type="Momentum watch",
            score=74.0,
            entry_type=EntryType.ACCEPTABLE,
            entry_reason="test",
            passed=[],
            missing=[],
            failed=[],
            contradictions=[],
            reasons=[],
            support=100.8,
            resistance=101.5,
            trigger=101.5,
            atr_proxy=0.6,
        )

        result = PreBreakoutPredictionEngine().evaluate(
            stock,
            self._market_context(Bias.BULLISH),
            None,
            technical,
            self._pattern(),
        )

        self.assertEqual(result.bias, "BULLISH")
        self.assertIn(result.status, {"BUILDING", "NEAR_BREAKOUT"})
        self.assertIn(result.breakout_probability, {"MEDIUM", "HIGH"})
        self.assertEqual(result.structure_state, "HH_HL_BUILDING")
        self.assertEqual(result.vwap_state, "ABOVE_HOLD")
        self.assertTrue(any("resistance" in item.lower() or "breakout" in item.lower() for item in result.preparation_signals))

    def test_prediction_engine_marks_stretched_move_as_exhausted(self) -> None:
        candles = pd.DataFrame(
            [
                {"datetime": f"2026-04-18 14:{35 + i:02d}:00", "open": o, "high": h, "low": l, "close": c, "volume": v}
                for i, (o, h, l, c, v) in enumerate(
                    [
                        (100.0, 101.0, 99.8, 100.9, 1200),
                        (100.9, 102.1, 100.7, 101.9, 1350),
                        (101.8, 103.2, 101.7, 102.9, 1500),
                        (102.9, 104.4, 102.7, 104.2, 1900),
                        (104.3, 106.0, 104.2, 105.8, 2300),
                        (105.9, 108.2, 105.7, 107.9, 2900),
                    ]
                )
            ]
        )
        stock = StockSnapshot(
            symbol="LATE",
            ltp=107.9,
            open=100.0,
            high=108.2,
            low=99.8,
            prev_close=99.7,
            volume=2900,
            change_pct=8.2,
            raw={"candles": candles, "vwap": 101.9},
        )
        technical = TechnicalAssessment(
            side=Side.LONG,
            setup_type="Momentum watch",
            score=79.0,
            entry_type=EntryType.RISKY,
            entry_reason="test",
            passed=[],
            missing=[],
            failed=[],
            contradictions=[],
            reasons=[],
            support=104.0,
            resistance=108.2,
            trigger=108.2,
            atr_proxy=1.4,
        )

        result = PreBreakoutPredictionEngine().evaluate(
            stock,
            self._market_context(Bias.BULLISH),
            None,
            technical,
            self._pattern(),
        )

        self.assertEqual(result.trap_risk, "HIGH")
        self.assertEqual(result.status, "EXHAUSTED")
        self.assertIn("VWAP", result.invalid_scenario)

    def test_snapshot_fallback_is_low_opportunity_when_live_volume_is_missing(self) -> None:
        quotes = pd.DataFrame(
            [
                {
                    "symbol": "A",
                    "ltp": 210,
                    "open": 205,
                    "high": 212,
                    "low": 202,
                    "prev_close": 204,
                    "volume": 0,
                    "change_pct": 2.94,
                },
                {
                    "symbol": "B",
                    "ltp": 320,
                    "open": 328,
                    "high": 330,
                    "low": 318,
                    "prev_close": 331,
                    "volume": 0,
                    "change_pct": -3.32,
                },
                {
                    "symbol": "C",
                    "ltp": 150,
                    "open": 148,
                    "high": 151,
                    "low": 146,
                    "prev_close": 147,
                    "volume": 0,
                    "change_pct": 2.04,
                },
            ]
        )
        universe = pd.DataFrame(
            [
                {"symbol": "A", "name": "A", "sector": "Alpha"},
                {"symbol": "B", "name": "B", "sector": "Beta"},
                {"symbol": "C", "name": "C", "sector": "Alpha"},
            ]
        )

        ranked, rejected, result = ScannerBrainService().scan(
            quotes=quotes,
            universe=universe,
            market_frame=pd.DataFrame(),
            min_score=35,
        )

        self.assertTrue(ranked.empty)
        self.assertTrue(any("snapshot" in str(reason).lower() for reason in rejected.get("reason", pd.Series(dtype=str)).tolist()))
        self.assertTrue(any("low opportunity" in str(reason).lower() for reason in rejected.get("reason", pd.Series(dtype=str)).tolist()))
        self.assertEqual(result.stats.scanned, 3)

    def test_intraday_trade_plan_caps_far_short_targets(self) -> None:
        stock = StockSnapshot(
            symbol="CDSL",
            ltp=1379.0,
            open=1490.0,
            high=1504.0,
            low=1065.26,
            prev_close=1510.0,
            change_pct=-8.7,
        )
        technical = TechnicalAssessment(
            side=Side.SHORT,
            setup_type="Breakdown continuation",
            score=82.0,
            entry_type=EntryType.ACCEPTABLE,
            entry_reason="Price is still close enough to VWAP for a manageable entry.",
            passed=[],
            missing=[],
            failed=[],
            contradictions=[],
            reasons=[],
            support=1065.26,
            resistance=1504.0,
            trigger=1065.26,
            atr_proxy=197.43,
        )

        entry_low, entry_high, stop, target1, target2, rr = AlignmentScoringEngine(ScoringProfile())._trade_plan(stock, technical)

        self.assertGreater(entry_low, 1365.0)
        self.assertLess(stop, 1410.0)
        self.assertGreater(target1, 1330.0)
        self.assertGreater(target2, 1310.0)
        self.assertLess(target2, target1)
        self.assertGreater(rr, 1.0)

    def test_technical_engine_marks_far_vwap_breakout_as_chasing(self) -> None:
        stock = StockSnapshot(
            symbol="CHASE",
            ltp=210.0,
            open=197.0,
            high=211.0,
            low=196.5,
            prev_close=196.0,
            volume=1200000,
            change_pct=7.14,
            raw={"vwap": 201.0},
        )

        technical = TechnicalValidationEngine(ScoringProfile()).evaluate(stock)

        self.assertEqual(technical.entry_type, EntryType.CHASING)
        self.assertTrue(any("chasing" in item.lower() for item in technical.failed))

    def test_scan_filters_chasing_names_and_keeps_only_cleaner_top_setups(self) -> None:
        quotes = pd.DataFrame(
            [
                {
                    "symbol": "CLEAN1",
                    "ltp": 101.1,
                    "open": 100.4,
                    "high": 101.4,
                    "low": 99.8,
                    "prev_close": 100.0,
                    "volume": 900000,
                    "change_pct": 1.1,
                    "vwap": 100.7,
                },
                {
                    "symbol": "CLEAN2",
                    "ltp": 204.2,
                    "open": 203.0,
                    "high": 204.8,
                    "low": 201.8,
                    "prev_close": 202.6,
                    "volume": 950000,
                    "change_pct": 0.79,
                    "vwap": 203.7,
                },
                {
                    "symbol": "CHASE",
                    "ltp": 157.0,
                    "open": 149.0,
                    "high": 157.8,
                    "low": 148.7,
                    "prev_close": 148.4,
                    "volume": 1800000,
                    "change_pct": 5.8,
                    "vwap": 151.0,
                },
            ]
        )
        universe = pd.DataFrame(
            [
                {"symbol": "CLEAN1", "name": "Clean One", "sector": "Energy"},
                {"symbol": "CLEAN2", "name": "Clean Two", "sector": "Energy"},
                {"symbol": "CHASE", "name": "Chasing Move", "sector": "Energy"},
            ]
        )
        market = pd.DataFrame(
            [
                {"symbol": "NIFTY", "label": "NIFTY", "is_index": True, "ltp": 22600, "change_pct": 0.55, "prev_close": 22500},
                {"symbol": "BANKNIFTY", "label": "BANKNIFTY", "is_index": True, "ltp": 48220, "change_pct": 0.42, "prev_close": 48000},
            ]
        )

        ranked, rejected, result = ScannerBrainService().scan(
            quotes=quotes,
            universe=universe,
            market_frame=market,
            min_score=35,
        )

        self.assertNotIn("CHASE", ranked.get("symbol", pd.Series(dtype=str)).tolist())
        self.assertTrue(any("VWAP" in str(reason) or "extended" in str(reason) for reason in rejected.get("reason", pd.Series(dtype=str)).tolist()))
        self.assertLessEqual(len(ranked), 5)
        self.assertEqual(result.stats.selected, len(ranked))


if __name__ == "__main__":
    unittest.main()
