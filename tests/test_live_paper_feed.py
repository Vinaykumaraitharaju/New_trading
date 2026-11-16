import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from reaction_alpha.api import create_app
from reaction_alpha.config import ReactionAlphaConfig
from reaction_alpha.service import ReactionAlphaService


@pytest.fixture
def live(tmp_path, monkeypatch):
    router = SimpleNamespace(kotak=SimpleNamespace(stream_connected=True))
    monkeypatch.setattr("reaction_alpha.service.build_router", lambda: router)
    service = ReactionAlphaService(ReactionAlphaConfig(simulated=False, paper_trade_db_path=str(tmp_path/"paper.db")))
    service._evaluate_signal = Mock(return_value=None)
    service._broadcast_if_due = Mock()
    service.paper_trades.update_symbol = Mock()
    service.paper_trades.update_pretrade_price = Mock()
    return service


def tick(service, epoch, **overrides):
    raw = dict(last_trade_time=epoch, last_update_time=epoch, bp=100.1, sp=100.2, bq=4, sq=5, v=30)
    raw.update(overrides)
    result = service._parse_tick(SimpleNamespace(symbol="ABC", instrument_token="1", exchange_segment="nse_cm",
                                                 ltp=100.15, raw=raw))
    result.timestamp = datetime.fromtimestamp(epoch + 0.5)
    return result


MORNING = datetime.fromisoformat("2026-11-16T10:00:00+05:30").timestamp()


def test_live_accepts_new_trades_not_replays(live):
    for epoch, volume in [(MORNING, 30), (MORNING, 30), (MORNING-1, 50), (MORNING, 31)]:
        live.process_tick(tick(live, epoch, v=volume))
    assert live.paper_trades.update_symbol.call_count == 2
    live.paper_trades.update_symbol.assert_called_with(symbol="ABC", price=100.15,
        timestamp=datetime.fromtimestamp(MORNING), bid=100.1, ask=100.2, close_only=False)
    live._router.kotak.stream_connected = False
    live.process_tick(tick(live, MORNING+1))
    assert live.paper_trades.update_symbol.call_count == 2


@pytest.mark.parametrize("bad", [dict(bp=None), dict(sp=99), dict(sq=0), dict(last_update_time=0),
                                 dict(last_update_time=MORNING-16)])
def test_verified_trade_without_firm_book_only_updates_forecast(live, bad):
    live.process_tick(tick(live, MORNING, **bad))
    live.paper_trades.update_symbol.assert_not_called()
    live.paper_trades.update_pretrade_price.assert_called_once()


def test_stale_trade_does_not_trigger_or_fill(live):
    live.process_tick(tick(live, MORNING, last_trade_time=MORNING-20))
    live.paper_trades.update_symbol.assert_not_called()
    live.paper_trades.update_pretrade_price.assert_not_called()


def test_live_cutoff_is_in_indian_time(live):
    live.process_tick(tick(live, MORNING+5*3600+20*60))
    assert live.paper_trades.update_symbol.call_args.kwargs["close_only"]


def test_stream_routes_use_separate_services(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = create_app(ReactionAlphaConfig(simulated=True, paper_trade_db_path=str(tmp_path/"paper.db")))
    async def read(route):
        response = await next(r.endpoint for r in app.routes if r.path == route)()
        try:
            return json.loads((await anext(response.body_iterator)).removeprefix("data: "))
        finally:
            await response.body_iterator.aclose()
    for path, service in [("/api/market-strip/stream", app.state.reaction_alpha),
                          ("/api/demo/market-strip/stream", app.state.reaction_alpha_demo)]:
        service.market_strip_snapshot = Mock(return_value={"source": path})
        assert asyncio.run(read(path)) == {"source": path}
