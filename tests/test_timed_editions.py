from datetime import datetime
import json

import pytest

from reaction_alpha.edition_context import reference
from reaction_alpha.timed_editions import TimedEditions

SLOT = datetime.fromisoformat("2026-11-17T09:20:00+05:30").timestamp()


def edition(tmp_path, sign=1, n=1):
    book = TimedEditions(str(tmp_path/"paper.db"))
    for i in range(n):
        for t in range(0, 300, 5):
            price = 100 + sign*t/200
            book.observe(f"S{i}", SLOT-300+t, price, price-.01, price+.01)
    book.tick(SLOT, True)
    return book


@pytest.mark.parametrize("sign", [1, -1])
def test_fixed_edition_and_barriers(tmp_path, sign):
    b = edition(tmp_path, sign, 8)
    picks = b.recent(1)[0]["picks"]
    assert len(picks) == 5
    p = picks[0]
    for offset, key in [(2, "entry"), (3, "t1"), (4, "t2")]:
        b.observe(p["symbol"], SLOT+offset, p[key], 0, 0)
    b.tick(SLOT+4, True)
    done = b.recent(1)[0]["picks"][0]
    assert done["state"] == "T2 reached"
    assert done["entered"] == SLOT+2 and done["hit1"] == SLOT+3
    assert done["entry"] == p["entry"]
    restarted = TimedEditions(b.path)
    assert restarted.recent(1)[0]["picks"][1]["state"] == "Insufficient data"
    assert restarted.recent(1)[0]["picks"][0]["state"] == "T2 reached"


def test_gap_before_entry_is_not_a_win(tmp_path):
    b = edition(tmp_path)
    p = b.recent(1)[0]["picks"][0]
    b.observe("S0", SLOT+1, p["t1"], 0, 0)
    end = b.recent(1)[0]["picks"][0]
    assert end["state"] == "Missed move" and not end["entered"] and not end["hit1"]


def test_late_target_and_unobserved_interval(tmp_path):
    b = edition(tmp_path, n=2)
    p = b.active["picks"][0]
    for t in range(1, 600, 20):
        b.observe("S0", SLOT+t, p["entry"], 0, 0)
    b.observe("S0", SLOT+600, p["t1"], 0, 0)
    b.tick(SLOT+601, True)
    assert [p["state"] for p in b.active["picks"]] == ["No timely T1", "Insufficient data"]


def test_disconnected_empty_and_no_late_backfill(tmp_path):
    b = edition(tmp_path, n=0)
    b.tick(SLOT+1206, True)
    assert len(b.recent(10)) == 1
    b.tick(SLOT+2400, False)
    assert b.recent(1)[0]["picks"] == [] and not b.recent(1)[0]["connected"]


def test_dated_reference():
    assert reference(b'<root><day time="2026-11-16"><r currency="INR" rate="99"/><r currency="USD" rate="1.1"/></day></root>') == {
        "date":"2026-11-16", "usd_inr":90}


def test_publication_diagnostics_survive_restart(tmp_path):
    b = TimedEditions(str(tmp_path/"paper.db"))
    for t in range(0, 300, 5):
        for i in range(6):
            price = 100+t/200
            b.observe(str(i), SLOT-300+t, price, price-.01, price+.01)
        b.observe("FLAT", SLOT-300+t, 100, 99.99, 100.01)
        b.observe("NOBOOK", SLOT-300+t, 100, 0, 0)
    b.tick(SLOT, True, subscribed=[str(i) for i in range(6)]+["FLAT","NOBOOK","SILENT","NIFTY"])
    d = TimedEditions(b.path).recent(1)[0]["diagnostics"]
    assert [d[k] for k in ("subscribed","usable","qualified","published")] == [9,7,6,5]
    reasons = {r["symbol"]:r for r in d["excluded"]}
    assert reasons["SILENT"]["observations"] == 0
    assert "range" in reasons["FLAT"]["reason"]
    assert "bid" in reasons["NOBOOK"]["reason"]
    assert "top five" in reasons["5"]["reason"]


def test_opposing_index_filters_without_creating_index_pick(tmp_path):
    b = TimedEditions(str(tmp_path/"paper.db"))
    for t in range(0, 300, 5):
        b.observe("NIFTY", SLOT-300+t, 20000-t, 0, 0)
        b.observe("ABC", SLOT-300+t, 100+t/200, 100+t/200-.01, 100+t/200+.01)
    b.tick(SLOT, True)
    assert b.active["nifty_move"] < -.001 and not b.active["picks"]


def test_earlier_evidence_is_slot_and_version_specific(tmp_path):
    b = TimedEditions(str(tmp_path/"paper.db"))
    def insert(db, slot, version):
        data = {"slot":slot, "version":version, "picks":[
            {"direction":"Bullish", "state":"T1 only", "hit1":slot+100},
            {"direction":"Bullish", "state":"Insufficient data", "hit1":None}]}
        db.execute("INSERT INTO timed_editions VALUES (?,?)", (slot, json.dumps(data)))
    with b.connect() as db:
        insert(db, SLOT-86400, "opening-pressure-v1")
        insert(db, SLOT-2*86400, "old-version")
        insert(db, SLOT-86400+1200, "opening-pressure-v1")
    for t in range(0, 300, 5):
        price = 100+t/200
        b.observe("S0", SLOT-300+t, price, price-.01, price+.01)
    b.tick(SLOT, True)
    p = b.active["picks"][0]
    assert (p["prior_t1"], p["prior_calls"], p["prior_days"]) == (1,1,1)
    assert p["shadow_score"] == p["efficiency"]
