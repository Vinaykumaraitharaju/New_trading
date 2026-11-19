from datetime import datetime
import pytest
from reaction_alpha.market_strip import IST
from reaction_alpha.horizon_trial import HorizonTrials


@pytest.mark.parametrize("side", [1,-1])
def test_same_entry_times_out_then_later_hits(tmp_path,side):
    h=HorizonTrials(tmp_path/"db")
    t=datetime(2026,11,19,10,tzinfo=IST).timestamp()
    h.start(dict(id="x",symbol="X",direction="Bullish" if side==1 else "Bearish",stop=100-side,t1=100+side),t,99.99,100.01)
    for n in range(20,660,20):
        h.update(t+n,"X",100,99.99,100.01)
    h.update(t+660,"X",100+side,100+side-.01,100+side+.01)
    a,b,c=h.report()
    assert a["timed"]==1 and a["avg_net_bps"] < -10
    assert b["hits"]==c["hits"]==1 and b["avg_net_bps"]>0
    assert all(r["paired"]==1 for r in (a,b,c))


def test_censor_restart_close_and_unpriced_exit(tmp_path):
    path=tmp_path/"db"
    h=HorizonTrials(path)
    t=datetime(2026,11,19,10,tzinfo=IST).timestamp()
    p=dict(id="a",symbol="X",direction="Bullish",stop=99,t1=101)
    h.start(p,t,99,100)
    h.update(t+1,"X",99)
    h.start(dict(p,id="b"),t+2,99,100)
    h.start(dict(p,id="late"),t+5*3600,99,100)
    h=HorizonTrials(path)
    assert all((r["stops"],r["late"],r["missing"],r["paired"])==(1,1,1,0) for r in h.report())
