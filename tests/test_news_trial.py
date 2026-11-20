from datetime import datetime
import sqlite3
from reaction_alpha.market_strip import IST
from reaction_alpha.mover_sweep import MoverSweep


def test_frozen_pre_move_headline_and_control(tmp_path):
    s=MoverSweep(tmp_path/"book")
    t=datetime(2026,11,19,10,tzinfo=IST).timestamp()
    with sqlite3.connect(s.path) as db:
        for sym,seen in [("INFY",t-1),("SBIN",t+1)]:
            db.execute("INSERT INTO mover_news_evidence_v1 VALUES(?,?,?,?,?,?,?)",
                       (sym,"https://example.org",seen,t-60,"Financial results",sym+" profit falls","source"))
    def snap(ts,p):
        return dict(prev_close=100,high=103,low=99,ltp=p,raw={"lstup_time":ts})
    for ts,p in [(t,101),(t+60,101),(t+18000,100)]:
        s.ingest({sym:snap(ts,p) for sym in ("INFY","SBIN")},ts)
    trial=s.report(t+18000)["news_trial"]
    assert trial["total"]==trial["measured"]==2
    assert trial["changed"]==1 and trial["news_net"]>trial["price_net"]
