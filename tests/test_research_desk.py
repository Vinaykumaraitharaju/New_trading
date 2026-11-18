from datetime import datetime
import json

from reaction_alpha.research_desk import day_schedule, deadlines, evaluate
from reaction_alpha.timed_editions import TimedEditions, VERSION


def at(value):
    return datetime.fromisoformat(value + "+05:30").timestamp()


DAY = "2026-11-18T"


def test_upcoming_today_never_defaults_to_yesterday():
    yesterday = dict(slot=at("2026-11-17T15:00:00"), picks=[])
    s = day_schedule(at(DAY + "09:15:00"), [yesterday])
    assert len(s["slots"]) == 19
    assert s["selected_slot"] == at(DAY + "09:20:00")
    assert s["slots"][-1]["slot"] == at(DAY + "15:20:00")
    assert all(r["slot"] > yesterday["slot"] for r in s["slots"])
    assert s["slots"][-1]["t2_deadline"] == at(DAY + "15:30:00")


def test_published_current_window_and_no_backfill():
    slot = at(DAY + "09:20:00")
    assert day_schedule(slot+60, [dict(slot=slot)])["selected_slot"] == slot
    missing = day_schedule(slot+60, [])
    assert missing["selected_slot"] == slot+1200
    assert missing["slots"][0]["phase"] == "Not recorded"


def test_calendar_closed_unknown_and_special_session():
    assert day_schedule(at("2026-11-24T09:15:00"), [])["slots"] == []
    assert day_schedule(at("2027-01-04T09:15:00"), [])["session"] == "unknown"
    special = day_schedule(at("2026-11-08T09:15:00"), [])
    assert special["slots"][0]["slot"] == at("2026-11-08T14:20:00")


def seed(book, slot):
    for t in range(0, 300, 5):
        p = 100+t/200
        book.observe("ABC", slot-300+t, p, p-.01, p+.01)


def test_snapshot_preview_is_unpublished_and_read_only(tmp_path):
    book = TimedEditions(str(tmp_path/"paper.db"))
    now = at(DAY+"09:39:00")
    seed(book, now)
    book.tick(now, True)
    data = book.snapshot(now)
    assert data["preview"]["picks"][0]["state"] == "Provisional"
    assert data["preview"]["for_slot"] == at(DAY+"09:40:00")
    assert book.recent(40) == []
    book.tick(now+1, False)
    assert not book.snapshot(now+1)["preview"]["picks"]
    assert not book.snapshot(at(DAY+"15:31:00"))["preview"]["picks"]


def test_last_window_expires_at_close_and_levels_are_frozen(tmp_path):
    book = TimedEditions(str(tmp_path/"paper.db"))
    slot = at(DAY+"15:20:00")
    seed(book, slot)
    book.tick(slot, True)
    p = book.active["picks"][0]
    original = {k:p[k] for k in ("entry", "stop", "t1", "t2", "evidence")}
    assert p["id"] == f"{int(slot)}:ABC"
    book.observe("ABC", slot+1, p["entry"], 0, 0)
    for t in range(2, 600, 20):
        book.observe("ABC", slot+t, p["t1"], 0, 0)
    book.observe("ABC", slot+600, p["t2"], 0, 0)
    assert p["state"] == "T1 only"
    assert p["ended"] == deadlines(slot)[1]
    assert {k:p[k] for k in original} == original
    assert [x["state"] for x in p["timeline"]] == ["Published", "Entered", "T1 reached", "T1 only"]


def test_learning_excludes_today_other_versions_and_censored_entries():
    before = at(DAY+"00:00:00")
    picks = [dict(state="T1 only", entered=100, hit1=150, shadow_rank=1),
             dict(state="No timely T1", entered=100, hit1=None),
             dict(state="No entry", entered=None, hit1=None),
             dict(state="Missed move", entered=None, hit1=None),
             dict(state="Insufficient data", entered=100, hit1=130)]
    records = [dict(slot=before-86400, version=VERSION, picks=picks),
               dict(slot=before, version=VERSION, picks=picks),
               dict(slot=before-86400, version="other", picks=picks)]
    r = evaluate(records, VERSION, before)
    assert r["calls"] == 5 and r["sessions"] == 1
    assert (r["evaluated_entries"], r["on_time_t1"]) == (2, 1)
    assert r["median_winner_seconds"] == 50
    assert r["winner_timing_samples"] == 1
    assert r["entry_hit_interval"][0] < 50 < r["entry_hit_interval"][1]
    assert r["paired_editions"] == 1


def test_archived_link_fetches_record_older_than_research_window(tmp_path):
    book = TimedEditions(str(tmp_path/"paper.db"))
    old = at("2026-01-05T09:20:00")
    payload = dict(slot=old, version=VERSION, picks=[])
    with book.connect() as db:
        db.execute("INSERT INTO timed_editions VALUES (?,?)", (old, json.dumps(payload)))
        for i in range(1, 42):
            newer = dict(slot=old+i*1200, version=VERSION, picks=[])
            db.execute("INSERT INTO timed_editions VALUES (?,?)", (newer["slot"], json.dumps(newer)))
    assert payload not in book.snapshot(at(DAY+"09:15:00"))["editions"]
    assert payload in book.snapshot(at(DAY+"09:15:00"), old)["editions"]


def test_preview_explains_missing_coverage_and_opposing_market(tmp_path):
    book = TimedEditions(str(tmp_path/"paper.db"))
    now = at(DAY+"09:39:00")
    seed(book, now)
    book.observe("NEW", now-1, 100, 99, 101)
    for t in range(0, 300, 5):
        book.observe("NIFTY", now-300+t, 20000-t, 0, 0)
    book.tick(now, True)
    preview = book.snapshot(now)["preview"]
    assert not preview["picks"]
    assert preview["checked"] == 2
    assert "NIFTY" in preview["excluded"][0]["reason"]
    assert "five-minute coverage" in preview["excluded"][1]["reason"]
