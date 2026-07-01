from __future__ import annotations

from datetime import datetime, timedelta
import unittest

from reaction_alpha.config import ReactionAlphaConfig
from reaction_alpha.engines.scoring_engine import UnifiedScoringEngine
from reaction_alpha.models import ComponentScore, ReactionResult, StructureResult, TickData
from reaction_alpha.paper_trade import PaperTradeBook, PendingTrigger
from reaction_alpha.service import ReactionAlphaService


def _build_service() -> ReactionAlphaService:
    config = ReactionAlphaConfig(
        symbols=["TEST"],
        simulated=True,
        top_n=5,
        heartbeat_sec=0.0,
    )
    return ReactionAlphaService(config)


def test_continuation_signal_reaches_trade_threshold() -> None:
    service = _build_service()
    start = datetime(2026, 4, 21, 9, 15, 0)
    total_volume = 0.0
    price = 100.0
    for index in range(36):
        if index < 20:
            price += 0.05
            volume_step = 8000
            bid_size = 2200
            ask_size = 1600
        else:
            price += 0.18
            volume_step = 42000
            bid_size = 5200
            ask_size = 1400
        total_volume += volume_step
        tick = TickData(
            symbol="TEST",
            instrument_token="SIM-TEST",
            exchange_segment="nse_cm",
            timestamp=start + timedelta(seconds=index * 5),
            price=round(price, 2),
            volume=total_volume,
            bid=round(price - 0.03, 2),
            ask=round(price + 0.03, 2),
            bid_size=bid_size,
            ask_size=ask_size,
            vwap=price - 0.1,
            raw={},
        )
        signal = service.process_tick(tick)
    assert signal is not None
    assert signal.stock == "TEST"
    assert signal.score >= 12
    assert signal.reaction in {"CONTINUATION", "ABSORPTION"}


def test_fake_move_penalty_can_remove_signal() -> None:
    service = _build_service()
    start = datetime(2026, 4, 21, 9, 15, 0)
    total_volume = 0.0
    price = 100.0
    for index in range(30):
        if index < 15:
            price += 0.25
            volume_step = 9000
        else:
            price -= 0.35
            volume_step = 9500
        total_volume += volume_step
        service.process_tick(
            TickData(
                symbol="TEST",
                instrument_token="SIM-TEST",
                exchange_segment="nse_cm",
                timestamp=start + timedelta(seconds=index * 5),
                price=round(price, 2),
                volume=total_volume,
                bid=round(price - 0.04, 2),
                ask=round(price + 0.04, 2),
                bid_size=1400,
                ask_size=4200 if index > 15 else 1400,
                vwap=100.1,
                raw={},
            )
        )
    payload = service.get_signal("TEST")
    if payload is not None:
        assert payload["score"] < 18


def test_adaptive_setup_guard_blocks_clean_invalidation_row(tmp_path) -> None:
    config = ReactionAlphaConfig(
        symbols=["TEST"],
        simulated=True,
        paper_trade_db_path=str(tmp_path / "paper_trades.db"),
        adaptive_setup_guard_min_entries=1,
    )
    book = PaperTradeBook(config)
    now = datetime.now().isoformat(timespec="seconds")
    with book._connect() as conn:
        conn.execute(
            """
            INSERT INTO paper_trades (
                symbol, signal, setup_type, regime, direction, state, result, score, confidence,
                created_at, updated_at, entry_trigger, stop_loss, target1, target2,
                entered_at, sl_category, t1_hit, t2_hit
            ) VALUES (
                'TEST', 'STRONG BULLISH', 'ABSORPTION_BUILDUP', 'CHOPPY', 'BULLISH',
                'CLOSED', 'SL_HIT', 16, '70%', ?, ?, 100, 99, 102, 104, ?,
                'clean_invalidation', 0, 0
            )
            """,
            (now, now, now),
        )

    guard = book.setup_risk_guard(
        setup_type="ABSORPTION_BUILDUP",
        regime="CHOPPY",
        direction="BULLISH",
    )

    assert guard["blocked"] is True
    assert guard["clean_invalidations"] == 1


def test_choppy_pending_trigger_requires_acceptance_before_entry(tmp_path) -> None:
    config = ReactionAlphaConfig(
        symbols=["TEST"],
        simulated=True,
        paper_trade_db_path=str(tmp_path / "paper_trades.db"),
        paper_trade_entry_confirm_ratio=0.08,
        paper_trade_choppy_confirm_multiplier=1.45,
    )
    book = PaperTradeBook(config)
    now = datetime.now()
    candidate = PendingTrigger(
        id=1,
        symbol="TEST",
        direction="BULLISH",
        state="READY",
        created_at=now,
        expires_at=now + timedelta(minutes=5),
        entry_trigger=100.0,
        stop_loss=99.0,
        target1=102.0,
        target2=104.0,
        signal="STRONG BULLISH",
        setup_type="BREAKOUT_CONTINUATION",
        regime="CHOPPY",
        score=18,
        confidence="72%",
    )
    with book._connect() as conn:
        conn.execute(
            """
            INSERT INTO paper_candidates (
                id, symbol, signal, setup_type, regime, direction, score, confidence, state,
                created_at, updated_at, expires_at, entry_trigger, stop_loss, target1, target2
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate.id,
                candidate.symbol,
                candidate.signal,
                candidate.setup_type,
                candidate.regime,
                candidate.direction,
                candidate.score,
                candidate.confidence,
                candidate.state,
                now.isoformat(timespec="seconds"),
                now.isoformat(timespec="seconds"),
                candidate.expires_at.isoformat(timespec="seconds"),
                candidate.entry_trigger,
                candidate.stop_loss,
                candidate.target1,
                candidate.target2,
            ),
        )

    book._update_candidate(candidate, price=100.12, timestamp=now + timedelta(seconds=10))
    with book._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0] == 0

    book._update_candidate(candidate, price=100.24, timestamp=now + timedelta(seconds=20))
    with book._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0] == 1


class AdaptiveLiveScoringTest(unittest.TestCase):
    def test_live_scoring_applies_stock_reaction_profile(self) -> None:
        score = UnifiedScoringEngine(elite_threshold=18, strong_threshold=12).evaluate(
            reaction=ReactionResult("CONTINUATION", 4, ["reaction"], 100.0, 101.0, 99.0),
            structure=StructureResult("Bullish", "HH_HL", 3, True, False, 101.0, 99.0, ["structure"]),
            sr=ComponentScore("sr", 2, ["sr"]),
            pattern=ComponentScore("pattern", 1, ["pattern"]),
            volume=ComponentScore("volume", 5, ["volume"]),
            orderflow=ComponentScore("orderflow", 2, ["orderflow"]),
            vwap=ComponentScore("vwap", 2, ["vwap"]),
            volatility=ComponentScore("volatility", 1, ["volatility"]),
            speed=ComponentScore("speed", 2, ["speed"]),
            market_context=ComponentScore("market", 5, ["market"]),
            buildup=ComponentScore("buildup", 1, ["buildup"]),
            fake_move_penalty=ComponentScore("fake_move", 0, []),
            symbol="HDFCBANK",
            sector="Bank",
        )

        self.assertIn("adaptive_profile", score.components)
        self.assertTrue(score.reasons[0].startswith("Adaptive stock profile applied: HDFC Bank"))
        self.assertGreater(score.components["market"], 5)
        self.assertGreater(score.components["volume"], 5)
        self.assertLess(score.components["reaction"], 4)

    def test_pretrade_opportunity_intelligence_is_added(self) -> None:
        service = _build_service()
        setup = {
            "symbol": "TEST",
            "side": "LONG",
            "ltp": 100.0,
            "entry_high": 100.2,
            "entry_low": 99.8,
            "target1": 101.0,
            "stop_loss": 99.4,
            "pressure_state": "BUYER_PRESSURE",
            "volume_state": "BUILDING",
            "vwap_state": "ABOVE_HOLD",
            "trap_risk": "LOW",
            "structure_state": "HH_HL_BUILDING",
            "compression_state": "TIGHT",
            "level_tests": 3,
            "level_test_quality": "TIGHT",
            "final_selector_score": 72,
            "market_bias": "bullish",
            "sector": "Energy",
            "reaction_profile": "Energy / Commodity Sensitive",
            "invalidation_note": "Invalid below VWAP",
        }

        service._enrich_pretrade_opportunity(setup)

        self.assertEqual(setup["opportunity_phase"], "PRE_TRIGGER_READY")
        self.assertGreaterEqual(setup["demand_supply_score"], 80)
        self.assertGreaterEqual(setup["prebreakout_memory_score"], 80)
        self.assertGreater(setup["target_ahead_probability"], 60)
        self.assertGreater(setup["relative_opportunity_score"], 60)
        self.assertEqual(setup["confirmation_quality"], "REAL_ACCUMULATION")
        self.assertIn("market_intelligence", setup)
