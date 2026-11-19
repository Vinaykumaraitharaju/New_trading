from datetime import datetime, timedelta

from reaction_alpha.daily_movers import DailyMovers
from reaction_alpha.market_strip import IST


def test_movers_exact_boundaries_reversal_and_restart(tmp_path):
    path = tmp_path/"ticks.db"
    b = DailyMovers(path)
    t = datetime(2026,11,19,11,tzinfo=IST).timestamp()
    b.observe("NIFTY",t,104,100)
    b.observe("UNKNOWN",t,104,None)
    b.observe("ABC",t,101,100)
    b.observe("ABC",t+1,104,100,{"published":t+3,"received":t+3},
              {"epoch":t,"price":201,"previous_close":200})
    b.observe("ABC",t+2,96,100)
    b.observe("LATE",t+3,105,100)
    r=DailyMovers(path).report(t+4)
    assert r["covered"]==2 and len(r["movers"])==3
    up,down,late=r["movers"]
    assert up["percent"]==4 and up["filing"] is None and up["nifty_pct"]==.5
    assert down["percent"]==-4 and late["symbol"]=="LATE"
    assert len(r["forecasts"])==1 and r["forecasts"][0]["outcome"]=="Up"


def test_train_from_prior_sessions_only_include_controls_not_gaps(tmp_path):
    b=DailyMovers(tmp_path/"ledger.db")
    for i in range(5):
        day=datetime(2026,11,9,15,29,30,tzinfo=IST)+timedelta(days=i+int(i>=1))
        # Skip the exchange holiday and weekend.
        if day.weekday()==5:
            day+=timedelta(days=2)
        t=day.timestamp()
        for j in range(6):
            b.observe(str(j),t,101,100)
            b.observe(str(j),t+16,104 if j<4 else 101,100)
        b.observe("gap",t-120,101,100)
        b.observe("gap",t+16,101,100)
    t=datetime(2026,11,19,15,29,30,tzinfo=IST).timestamp()
    b.observe("NEW",t,101,100)
    f=b.report(t)["forecasts"][0]
    assert f["prior_counts"]=={"Up":20,"Neither":10}
    assert f["prediction"]=="Up" and f["prior_days"]==5
    b.observe("NEW",t+2,96,100)
    r=b.report(t+86400)
    assert r["paired"]==1 and r["correct"]==0 and r["movers"]==[]
