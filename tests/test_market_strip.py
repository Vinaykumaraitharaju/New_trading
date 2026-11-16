from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from data.kotak_neo_feed import KotakNeoFeed
from reaction_alpha.api import create_app
from reaction_alpha.config import ReactionAlphaConfig
from reaction_alpha.market_strip import IST, MarketStrip, session


def at(value):
    return datetime.fromisoformat(value).replace(tzinfo=IST).timestamp()


@pytest.mark.parametrize("when,expected", [
    ("2026-11-13T09:15","open"), ("2026-11-13T15:30","closed"),
    ("2026-01-15T12:00","closed"), ("2026-11-10T12:00","closed"),
    ("2026-02-01T10:00","open"), ("2026-11-08T14:19","closed"),
    ("2026-11-08T14:20","open"), ("2026-11-08T15:30","closed"),
    ("2027-01-04T10:30","unknown")])
def test_cash_calendar(when, expected):
    assert session(at(when)) == expected


def test_independent_market_observations():
    s = MarketStrip(False)
    now = at("2026-11-13T10:00")
    s.observe("NIFTY", 110, now, 100, now)
    s.observe("SENSEX", 210, now-90, None, now)
    s.observe("BANKNIFTY", 90, now*1000, 100, now)
    for bad in (now-3, now, now+1, None):
        s.observe("NIFTY", 999, bad, 800, now)
    rows = s.snapshot(now, True)["indices"]
    assert [r["status"] for r in rows] == ["live","stale","live"]
    assert [r["percent"] for r in rows] == [10,None,-10]
    assert s.snapshot(now+20,True)["indices"][0]["status"] == "delayed"
    assert s.snapshot(now,False)["indices"][0]["status"] == "stale"
    after = s.snapshot(at("2026-11-14T10:00"),False)["indices"][0]
    assert (after["status"],after["epoch"],after["level"]) == ("last known",now,110)
    demo = MarketStrip(True)
    demo.observe("SENSEX", 200, now, 220, now)
    assert [r["status"] for r in demo.snapshot(now,False)["indices"]] == ["unavailable","simulated","unavailable"]


def test_sdk_index_names_are_exchange_scoped():
    feed = KotakNeoFeed("test")
    for exchange,name,symbol in [("nse_cm","Nifty 50","NIFTY"),("nse_cm","Nifty Bank","BANKNIFTY"),("bse_cm","SENSEX","SENSEX")]:
        assert feed._stream_symbol(dict(type="index",name=name,exchange_segment=exchange),"99") == symbol
    assert feed._stream_symbol(dict(type="index",name="SENSEX",exchange_segment="nse_cm"),"99") != "SENSEX"


def test_strip_reads_do_not_scan_or_authenticate(tmp_path, monkeypatch):
    app = create_app(ReactionAlphaConfig(simulated=True, paper_trade_db_path=str(tmp_path/"paper.db")))
    service = app.state.reaction_alpha
    fail = lambda *args, **kwargs: pytest.fail("Strip triggered an unrelated operation")
    monkeypatch.setattr(service,"pretrade_scan",fail)
    monkeypatch.setattr(service,"kotak_login_state",fail)
    monkeypatch.setattr(service,"snapshot",fail)
    service._router = SimpleNamespace(kotak=SimpleNamespace(stream_connected=False))
    client = TestClient(app)
    assert client.get("/api/market-strip").json()["scan"] is None
    service.market_strip.completed(123456,55)
    for _ in range(2):
        assert client.get("/api/market-strip").json()["scan"] == {"epoch":123456,"symbols":55}


def test_ranked_ticker_keeps_latest_observation_separate_from_scan(tmp_path, monkeypatch):
    import time

    app = create_app(ReactionAlphaConfig(simulated=True, paper_trade_db_path=str(tmp_path/"paper.db")))
    service = app.state.reaction_alpha
    calls = []
    def scan():
        calls.append(1)
        return {"status":"ok","stats":{"scanned":1},"setups":[{"symbol":"ABC","ltp":100}]}
    monkeypatch.setattr(service,"_pretrade_scan_from_store",scan)
    client = TestClient(app)
    client.get("/api/pretrade/top")
    now = time.time()
    service._remember_ticker("ABC",101,now)
    service._remember_ticker("ABC",98,now-1)
    service._remember_ticker("OTHER",200,now)
    for _ in range(2):
        assert client.get("/api/market-strip").json()["quotes"] == {
            "ABC":{"price":101,"epoch":now,"status":"simulated"}}
    assert client.get("/api/pretrade/top").json()["setups"][0]["ltp"] == 100
    assert len(calls)==1
    client.get("/api/pretrade/top?force=true")
    assert len(calls)==2
