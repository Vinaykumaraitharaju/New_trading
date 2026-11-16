import asyncio
from datetime import datetime, timedelta
from itertools import islice
import json
import random

import pytest

from reaction_alpha.api import quote_events
from reaction_alpha.config import ReactionAlphaConfig
from reaction_alpha.demo_tape import trade_arrivals
from reaction_alpha.paper_trade import PaperTradeBook, PendingTrigger


def test_arrivals_are_independent_and_stoppable():
    class Clock:
        now = 0.0
        stopped = False

        def is_set(self):
            return self.stopped

        def wait(self, delay):
            self.now += delay
            return self.stopped

    clock = Clock()
    events = trade_arrivals(["A", "B"], clock, rng=random.Random(42), clock=lambda: clock.now)
    samples = [(s, clock.now) for s in islice(events, 50)]
    gaps = [b[1] - a[1] for a, b in zip(samples, samples[1:])]
    assert {s for s, _ in samples} == {"A", "B"}
    assert min(gaps) < 0.1 < max(gaps)
    assert any(a[0] == b[0] for a, b in zip(samples, samples[1:]))
    clock.stopped = True
    assert next(events, None) is None


def test_demo_stream_skips_unchanged_snapshot():
    class Demo:
        prices = iter([100, 100, 101])

        def market_strip_snapshot(self):
            return {"price": next(self.prices)}

    async def read():
        events = quote_events(Demo())
        try:
            return [json.loads((await anext(events)).removeprefix("data: ")) for _ in range(2)]
        finally:
            await events.aclose()

    assert asyncio.run(read()) == [{"price": 100}, {"price": 101}]


@pytest.mark.parametrize("side,sign", [("BULLISH", 1), ("BEARISH", -1)])
def test_demo_paper_fill_uses_opposite_quotes(tmp_path, monkeypatch, side, sign):
    book = PaperTradeBook(ReactionAlphaConfig(simulated=True, paper_trading_enabled=True,
                          paper_trade_db_path=str(tmp_path / "paper.db"), paper_trade_slippage_bps=0))
    now = datetime.now()
    candidate = PendingTrigger(id=1, symbol="TEST", direction=side, state="READY", created_at=now,
                               expires_at=now + timedelta(minutes=5), entry_trigger=100,
                               stop_loss=100-sign, target1=100+sign, target2=100+2*sign,
                               signal=side, setup_type="BREAKOUT", regime="TREND", score=20, confidence="")
    monkeypatch.setattr(book, "_load_candidates", lambda _: [candidate])
    price = 100 + sign * 0.24
    book.update_symbol(symbol="TEST", price=price, timestamp=now, bid=price-.02, ask=price+.02)
    monkeypatch.setattr(book, "_load_candidates", lambda _: [])
    price = 100 + sign * 2.1
    book.update_symbol(symbol="TEST", price=price, timestamp=now+timedelta(seconds=1), bid=price-.02, ask=price+.02)
    with book._connect() as conn:
        row = conn.execute("SELECT trigger_price, exit_price, result FROM paper_trades").fetchone()
    assert row["trigger_price"] == pytest.approx(100+sign*.26)
    assert row["exit_price"] == pytest.approx(100+sign*2.08)
    assert row["result"] == "T2_HIT"
