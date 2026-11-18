"""Read-only planning and evaluation. Neither function invents future observations."""
from collections import Counter
from datetime import datetime
from statistics import median

from .market_strip import IST, session


def deadlines(slot):
    close = datetime.fromtimestamp(slot, IST).replace(hour=15, minute=30, second=0, microsecond=0).timestamp()
    return min(slot + 600, close), min(slot + 1200, close)


def day_schedule(now, editions):
    local = datetime.fromtimestamp(now, IST)
    saved = {e["slot"]: e for e in editions}
    rows = []
    for minute in range(560, 921, 20):
        slot = int(local.replace(hour=minute // 60, minute=minute % 60, second=0, microsecond=0).timestamp())
        if session(slot) != "open":
            continue
        t1, t2 = deadlines(slot)
        phase = "Scheduled" if slot > now else "Not recorded"
        if slot in saved:
            phase = "Published" if now < t2 else "Completed"
        elif 0 < slot - now <= 1200:
            phase = "Developing"
        rows.append(dict(slot=slot, phase=phase, t1_deadline=t1, t2_deadline=t2))
    active = [r for r in rows if r["phase"] == "Published"]
    future = [r for r in rows if r["slot"] > now]
    selected = (active or future or rows[-1:])
    return dict(date=local.date().isoformat(), timezone="Asia/Kolkata", session=session(now),
                slots=rows, selected_slot=selected[0]["slot"] if selected else None,
                session_close=int(local.replace(hour=15, minute=30, second=0, microsecond=0).timestamp()))


def evaluate(editions, version, before):
    """Only completed prior-session editions of the same rule version contribute."""
    states = Counter()
    sessions = set()
    times = []
    entered = wins = 0
    paired = baseline = shadow = 0
    terminal = {"No entry", "Invalidated", "Missed move", "Stop first", "No timely T1",
                "T2 reached", "T1 then stop", "T1 only", "Insufficient data"}
    for e in editions:
        if e.get("version") != version or e["slot"] >= before:
            continue
        for p in e["picks"]:
            states[p["state"]] += 1
            sessions.add(datetime.fromtimestamp(e["slot"], IST).date().isoformat())
            # Censored calls are separate even when they contain an earlier T1.
            if p["state"] in terminal - {"Insufficient data"} and p.get("entered"):
                entered += 1
                wins += bool(p.get("hit1"))
                if p.get("hit1"):
                    times.append(p["hit1"] - p["entered"])
        a = e["picks"][0] if e["picks"] else None
        b = next((p for p in e["picks"] if p.get("shadow_rank") == 1), None)
        if a and b and all(p["state"] in terminal - {"Insufficient data"} for p in (a, b)):
            paired += 1
            baseline += bool(a.get("hit1"))
            shadow += bool(b.get("hit1"))
    interval = None
    if entered:
        # Wilson 95% interval describes sampling uncertainty, not a new-call probability.
        z = 1.96
        rate = wins / entered
        den = 1 + z*z/entered
        centre = (rate + z*z/(2*entered))/den
        half = z*((rate*(1-rate)/entered + z*z/(4*entered*entered))**.5)/den
        interval = [round(100*(centre-half), 1), round(100*(centre+half), 1)]
    return dict(version=version, sessions=len(sessions), calls=sum(states.values()),
                states=dict(states), evaluated_entries=entered, on_time_t1=wins,
                entry_hit_interval=interval, median_winner_seconds=median(times) if times else None,
                winner_timing_samples=len(times), paired_editions=paired,
                baseline_top1_hits=baseline, shadow_top1_hits=shadow,
                policy="Shadow only; no automatic promotion", window_days=90,
                news_model="Not trained: timestamped company-event history unavailable")
