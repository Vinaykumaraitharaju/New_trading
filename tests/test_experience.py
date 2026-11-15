from datetime import datetime, timedelta
import sqlite3

import pytest

from reaction_alpha.config import ReactionAlphaConfig
from reaction_alpha.experience import INSERT, Turso
from reaction_alpha.paper_trade import PaperTradeBook


class CloudFixture:
    """Run the production SQL independently of either deploy's local database."""
    def __init__(self, path):
        self.path = path
        self.url = "fixture://shared-memory"
        self.lose_ack = False

    def run(self, statements):
        with sqlite3.connect(self.path) as db:
            db.row_factory = sqlite3.Row
            for sql, args in statements:
                rows = db.execute(sql, args).fetchall()
        if self.lose_ack and statements[0][0] == INSERT:
            self.lose_ack = False
            raise ConnectionError("response lost after commit")
        return rows


def make(path):
    return PaperTradeBook(ReactionAlphaConfig(simulated=True, paper_trade_db_path=str(path)))


def test_training_recovers_after_empty_deploy_and_excludes_future_and_demo(tmp_path):
    cloud = CloudFixture(tmp_path/"hosted.db")
    day = "2026-11-12"
    prior = make(tmp_path/"old.db")
    with prior._connect() as db:
        for i in range(90):
            sim = i >= 60
            future = 30 <= i < 60
            d = "2026-11-12" if future else f"2026-11-{1+i%5:02d}"
            db.execute(INSERT, ("simulated" if sim else "Kotak Neo snapshot", "TEST", "BREAKOUT", "BULLISH",
                                str(i),d,"BULLISH" if sim or future else "BEARISH",None))
    prior.experience.remote = cloud
    cloud.lose_ack = True
    with pytest.raises(ConnectionError):
        prior.experience.sync(day)
    prior.experience.sync(day)
    new = make(tmp_path/"empty.db")
    new.experience.remote = cloud
    new.experience.sync(day)
    now = datetime.fromisoformat(day+"T11:00:00")
    setup = dict(symbol="TEST",side="LONG",setup_type="BREAKOUT",scanner_band="watchlist",
                 ltp=99,entry_high=100,stop_loss=98,target1=102,target2=104)
    new.archive_pretrade_setups([setup],generated_at=now,source="Kotak Neo snapshot")
    assert setup["shadow"]["direction"] == "BEARISH"
    assert setup["shadow"]["examples"] == 30
    assert setup["scanner_band"] == "watchlist"
    assert new.experience.predict("simulated","BREAKOUT","BULLISH",now)["direction"] == "BULLISH"
    new.update_pretrade_price(symbol="TEST",price=100,timestamp=now+timedelta(seconds=1))
    new.update_pretrade_price(symbol="TEST",price=97,timestamp=now+timedelta(minutes=30,seconds=1))
    new.experience.sync("2026-11-14")
    group = next(r for r in new.experience.report()["groups"] if r["source"]=="Kotak Neo snapshot")
    assert (group["paired"],group["learned_correct"],group["original_correct"]) == (1,1,0)
    assert new.experience.report()["pending_upload"] == 0


def test_insufficient_sessions_and_unmeasured_trials_abstain(tmp_path):
    book = make(tmp_path/"book.db")
    with book._connect() as db:
        for i in range(31):
            db.execute(INSERT,("simulated","X","A","BEARISH",str(i),"2026-11-01","BULLISH",None))
    book.experience.sync("2026-11-12")
    assert book.experience.predict("simulated","A","BEARISH",datetime(2026,11,12,12))["direction"] is None
    assert not book.experience.report()["pending_upload"]


def test_turso_batch_rejects_partial_success_and_hides_credentials(monkeypatch):
    remote = Turso("libsql://test-example.turso.io","secret")
    calls = []
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"results":[{"type":"error"},{"type":"ok"}]}
    def post(url, **options):
        calls.append((url,options))
        return Response()
    monkeypatch.setattr("reaction_alpha.experience.requests.post",post)
    with pytest.raises(RuntimeError,match="acknowledge"):
        remote.run([(INSERT,("one",None))])
    url,options = calls[0]
    assert url == "https://test-example.turso.io/v2/pipeline"
    assert options["json"]["requests"][0]["stmt"]["args"] == [{"type":"text","value":"one"},{"type":"null"}]
    with pytest.raises(ValueError):
        Turso("https://example.invalid","secret")
