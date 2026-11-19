from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from reaction_alpha.config import ReactionAlphaConfig
from reaction_alpha.paper_trade import PaperTradeBook
from reaction_alpha.service import ReactionAlphaService


@pytest.mark.parametrize("sign,side", [(1, "LONG"), (-1, "SHORT")])
def test_publication_to_outcome_survives_restart(tmp_path, sign, side):
    config = ReactionAlphaConfig(simulated=True, paper_trade_db_path=str(tmp_path / "journal.sqlite"))
    book = PaperTradeBook(config)
    start = datetime(2026, 11, 13, 10)
    setup = dict(symbol="ABC", side=side, entry_low=100, entry_high=100, ltp=100,
                 target1=100+sign, target2=100+2*sign, stop_loss=100-sign,
                 market_bias="BULLISH", nifty_5m="BEARISH", stock_5m=None, scanner_band="watchlist")
    book.archive_pretrade_setups([setup], generated_at=start, source="simulated")
    assert setup["setup_state"] == "WATCHING"

    def tick(seconds, price):
        book.update_pretrade_price(symbol="ABC", price=price, timestamp=start+timedelta(seconds=seconds))

    tick(2, 100)
    tick(1, 100-sign)
    tick(2, 100-sign)
    book = PaperTradeBook(config)
    revised = dict(setup, target1=500)
    book.archive_pretrade_setups([revised], generated_at=start+timedelta(seconds=3), source="simulated")
    assert (revised["setup_id"], revised["scanner_band"], revised["target1"]) == (setup["setup_id"], "trade-ready", 100+sign)
    tick(4, 100+sign)
    tick(5, 100-sign)
    tick(1802, 100+sign)
    report = book.pretrade_archive_report(session_date="2026-11-13")
    row, = report["recent"]
    assert (row["result"], row["first_barrier"], row["direction_30m"]) == ("SL_HIT", "T1", row["direction"])
    assert row["entered_at"] < row["t1_at"] < row["exited_at"]
    stats, = report["direction_30m_by_source"]
    assert (stats["paired"], stats["scanner_correct"], stats["market_correct"]) == (1, 1, int(sign == 1))
    nifty, stock = report["direction_scorecard"]
    assert (nifty["paired"], nifty["disagreements"], nifty["scanner_wins"], nifty["baseline_wins"]) == (1,int(sign==1),int(sign==1),0)
    assert (stock["measured"], stock["paired"]) == (1,0)


@pytest.mark.parametrize("seconds,price,expected", [(1, 104, "MISSED_ENTRY"), (3000, 104, "UNRESOLVED"), (1, 97, "INVALIDATED")])
def test_no_false_entry_or_win(tmp_path, seconds, price, expected):
    book = PaperTradeBook(ReactionAlphaConfig(paper_trade_max_hold_min=45, paper_trade_db_path=str(tmp_path/"paper.db")))
    start = datetime.now()
    book.archive_pretrade_setups([dict(symbol="X", side="LONG", ltp=99, entry_high=100,
                                      stop_loss=98, target1=102, target2=104)], generated_at=start)
    book.update_pretrade_price(symbol="X", price=price, timestamp=start+timedelta(seconds=seconds))
    row, = book.pretrade_archive_report()["recent"]
    assert (row["result"], row["entered_at"], row["first_barrier"]) == (expected, None, None)


def test_replayed_or_undated_quotes_are_not_evidence():
    received = datetime.now()
    tick = SimpleNamespace(raw={}, timestamp=received)
    assert ReactionAlphaService._fresh_trade_time(tick) is None
    tick.raw["last_trade_time"] = received.timestamp() - 60
    assert ReactionAlphaService._fresh_trade_time(tick) is None
    tick.raw["last_trade_time"] = received.timestamp() - 1
    assert ReactionAlphaService._fresh_trade_time(tick) is not None
