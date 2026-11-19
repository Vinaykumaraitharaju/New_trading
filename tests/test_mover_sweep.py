from datetime import datetime
import pandas as pd
from reaction_alpha.market_strip import IST
from reaction_alpha.mover_sweep import eq_universe,MoverSweep


def test_eq_filter_and_persisted_reversal(tmp_path):
    m=eq_universe(pd.DataFrame([dict(trading_symbol=n,pSymbol=i) for i,n in enumerate(["A-EQ","B-BE","C-EQ"],1)]))
    assert set(m)=={"A","C"}
    b=MoverSweep(tmp_path/"paper.db")
    t=datetime(2026,11,19,12,tzinfo=IST).timestamp()
    r=dict(prev_close=100,high=104,low=96,ltp=101,raw={"last_traded_time":"19/11/2026 12:00:00"})
    assert b.ingest({"A":r,"B":dict(r,raw={}),"C":dict(r,raw={"ltt":t-86400})},t+1)==1
    item,=MoverSweep(b.path).report(t)["movers"]
    assert item["up"] and item["down"] and item["current_pct"]==1
    assert not b.report(t+86400)["movers"]
