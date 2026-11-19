"""Prospective, live-only price-touch forecasts. Never submits or simulates orders."""
from collections import defaultdict, deque
from datetime import datetime
from math import ceil, floor
from threading import RLock
import json
import sqlite3

from .market_strip import IST, NAMES, session
from .research_desk import day_schedule, deadlines, evaluate

GAP = 45
COVERAGE = "Need five-minute coverage, a quote within 10 seconds, and no gap over 45 seconds"
BOOK = "Valid bid and ask are missing"
VERSION = "opening-pressure-v1"
FINAL = {"No entry", "Invalidated", "Missed move", "Stop first", "No timely T1",
         "T2 reached", "T1 then stop", "T1 only", "Insufficient data"}


def candidate(symbol, samples, slot):
    return assess_candidate(symbol, samples, slot)[0]


def assess_candidate(symbol, samples, slot):
    rows = [r for r in samples if slot-300 <= r[0] < slot]
    if (len(rows) < 12 or rows[0][0] > slot-270 or slot-rows[-1][0] > 10
            or any(b[0]-a[0] > GAP for a, b in zip(rows, rows[1:]))):
        return None, COVERAGE
    prices = [r[1] for r in rows]
    price, bid, ask = rows[-1][1:4]
    if not 0 < bid <= ask:
        return None, BOOK
    hi, lo = max(r[4] for r in rows), min(r[5] for r in rows)
    span = hi-lo
    if span < max(price*.0015, 8*(ask-bid), .1):
        return None, "Observed range is too small relative to price or spread"
    drift = price-prices[0]
    sign = 1 if drift > 0 else -1
    travel = sum(abs(b-a) for a, b in zip(prices, prices[1:]))
    efficiency = abs(drift)/travel if travel else 0
    if efficiency < .5:
        return None, "Price path is too choppy: directional efficiency below 0.5"
    if (hi-price if sign == 1 else price-lo) > .2*span:
        return None, "Price has pulled away from the breakout edge of its range"
    # Publish beyond the observed range; don't reward an already-crossed entry.
    entry = (ceil(hi*100)+1 if sign == 1 else floor(lo*100)-1)/100
    risk = max(span*.5, 4*(ask-bid), .05)
    levels = [round(entry+sign*risk*k, 2) for k in (-1, 1, 2)]
    if min(levels) <= 0:
        return None, "Risk calculation produced a non-positive level"
    return dict(symbol=symbol, direction="Bullish" if sign == 1 else "Bearish",
                entry=entry, stop=levels[0], t1=levels[1], t2=levels[2],
                efficiency=round(efficiency, 3), observed=rows[-1][0], state="Waiting",
                entered=None, hit1=None, ended=None,
                evidence=dict(range_high=hi, range_low=lo, range_points=round(span, 4),
                              spread=round(ask-bid, 4), risk_points=round(risk, 4),
                              observations=len(rows), window_start=rows[0][0],
                              drift_percent=round(100*drift/prices[0], 3),
                              efficiency=round(efficiency, 3),
                              target_method="T1 = 1 risk unit; T2 = 2 risk units",
                              counter_evidence="A range breakout can fail; company catalysts are unverified",
                              company_news="Unavailable", results="Unavailable", order_book="Unavailable")), "Qualifies"


def market_change(samples, slot):
    rows = [r for r in samples if slot-300 <= r[0] < slot]
    if (len(rows) >= 2 and rows[0][0] <= slot-270 and slot-rows[-1][0] <= 10
            and all(b[0]-a[0] <= GAP for a, b in zip(rows, rows[1:]))):
        return rows[-1][1]/rows[0][1]-1
    return None


class TimedEditions:
    def __init__(self, path):
        self.path = path
        self.lock = RLock()
        self.samples = defaultdict(lambda: deque(maxlen=360))
        self.active = None
        self.last_slot = 0
        self.connected = False
        self._research_cache = None
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS timed_editions(slot INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
            row = db.execute("SELECT payload FROM timed_editions ORDER BY slot DESC LIMIT 1").fetchone()
            if row:
                self.active = json.loads(row[0])
                self.last_slot = self.active["slot"]
                for p in self.active["picks"]:
                    if p["state"] not in FINAL:
                        p["state"] = "Insufficient data"
                        p.setdefault("timeline", []).append(dict(at=None, state="Insufficient data", reason="Service restarted; observation continuity lost"))
                self.save()

    def connect(self):
        return sqlite3.connect(self.path, timeout=5)

    def save(self):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO timed_editions VALUES (?,?)",
                       (self.last_slot, json.dumps(self.active, allow_nan=False)))

    def observe(self, symbol, epoch, price, bid, ask):
        if symbol in NAMES and symbol != "NIFTY":
            return
        with self.lock:
            buf = self.samples[symbol]
            if buf and epoch < buf[-1][0]:
                return
            hi = lo = price
            if buf and int(epoch) == int(buf[-1][0]):
                previous = buf.pop()
                hi, lo = max(price, previous[4]), min(price, previous[5])
            buf.append((epoch, price, bid, ask, hi, lo))
            if not self.active:
                return
            for p in self.active["picks"]:
                if symbol != p["symbol"] or p["state"] in FINAL or epoch <= self.active["published"]:
                    continue
                old = p["state"]
                self.advance(p, epoch, price)
                if p["state"] != old:
                    self.save()

    def advance(self, p, now, price=None):
        old = p["state"]
        last = p.get("last", self.active["published"])
        if now < last:
            return
        sign = 1 if p["direction"] == "Bullish" else -1
        if now-last > GAP:
            p["state"] = "Insufficient data"
        elif not p["hit1"] and now >= deadlines(self.last_slot)[0]:
            p["state"] = "No timely T1" if p["entered"] else "No entry"
        elif now >= deadlines(self.last_slot)[1]:
            p["state"] = "T1 only"
        elif price is None:
            return
        elif sign*(price-p["stop"]) <= 0:
            p["state"] = "T1 then stop" if p["hit1"] else "Stop first" if p["entered"] else "Invalidated"
        elif not p["entered"]:
            if sign*(price-p["t1"]) >= 0:
                p["state"] = "Missed move"
            elif sign*(price-p["entry"]) >= 0:
                p.update(state="Entered", entered=now)
        elif sign*(price-p["t1"]) >= 0:
            if not p["hit1"]:
                p.update(state="T1 reached", hit1=now)
            if sign*(price-p["t2"]) >= 0:
                p["state"] = "T2 reached"
        if price is not None:
            p["last"] = now
        if p["state"] in FINAL:
            p["ended"] = now
        if old != p["state"]:
            p.setdefault("timeline", []).append(dict(at=now, state=p["state"], price=price))

    def tick(self, now, connected, context=None, subscribed=None):
        with self.lock:
            self.connected = connected
            if not connected:
                self.samples.clear()
            if self.active:
                changed = False
                for p in self.active["picks"]:
                    if p["state"] not in FINAL:
                        old = p["state"]
                        if not connected:
                            p.update(state="Insufficient data", ended=now)
                            p.setdefault("timeline", []).append(dict(at=now, state=p["state"], reason="Broker disconnected"))
                        else:
                            self.advance(p, now)
                        changed |= old != p["state"]
                if changed:
                    self.save()
            local = datetime.fromtimestamp(now, IST)
            minute = local.hour*60+local.minute
            slot = int(local.replace(second=0, microsecond=0).timestamp())
            if (minute < 560 or minute > 920 or (minute-560)%20 or now-slot >= 5
                    or slot <= self.last_slot or session(slot) != "open"):
                return
            picks = []
            market_move = market_change(self.samples.get("NIFTY", ()), slot)
            universe = sorted(set(self.samples if subscribed is None else subscribed) - NAMES.keys())
            rejected = []
            usable = 0
            for symbol in universe:
                rows = self.samples.get(symbol, ())
                count = sum(slot-300 <= r[0] < slot for r in rows)
                p = None
                if not connected:
                    reason = "Feed disconnected at publication"
                elif not count:
                    reason = "Zero verified observations in the five-minute window"
                else:
                    p, reason = assess_candidate(symbol, rows, slot)
                    usable += int(reason not in {COVERAGE, BOOK})
                    if p and market_move is not None and market_move*(1 if p["direction"]=="Bullish" else -1)<-.001:
                        p, reason = None, "Opposing five-minute NIFTY move"
                    if p and any(r[0] >= slot and (r[4] >= p["entry"] if p["direction"]=="Bullish"
                                                   else r[5] <= p["entry"]) for r in rows):
                        p, reason = None, "Entry crossed before publication"
                if p:
                    picks.append(p)
                else:
                    rejected.append(dict(symbol=symbol, reason=reason, observations=count if connected else None))
            picks.sort(key=lambda p: (-p["efficiency"], p["symbol"]))
            # Frozen prior-session evidence; never reinterpret missing observations as losses.
            day_start = int(local.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
            earlier = defaultdict(list)
            with self.connect() as db:
                for (payload,) in db.execute("SELECT payload FROM timed_editions WHERE slot>=? AND slot<?",
                                              (day_start-90*86400, day_start)):
                    edition = json.loads(payload)
                    if edition["version"] != VERSION or (slot-edition["slot"])%86400:
                        continue
                    for past in edition["picks"]:
                        if past["hit1"] or past["state"] in FINAL-{"Insufficient data"}:
                            earlier[past["direction"]].append((edition["slot"], bool(past["hit1"])))
            for p in picks:
                evidence = earlier[p["direction"]]
                hits = sum(hit for _, hit in evidence)
                days = len({s for s, _ in evidence})
                # Experimental ranking only, never a published probability.
                adjustment = .1*((hits+1)/(len(evidence)+2)-.5) if len(evidence)>=30 and days>=5 else 0
                p.update(prior_calls=len(evidence), prior_t1=hits, prior_days=days,
                         shadow_score=p["efficiency"]+adjustment,
                         id=f"{slot}:{p['symbol']}",
                         timeline=[dict(at=now, state="Published", reason="Levels frozen")])
            for rank, p in enumerate(sorted(picks[:5], key=lambda p: -p["shadow_score"]), 1):
                p["shadow_rank"] = rank
            self.last_slot = slot
            rejected.extend(dict(symbol=p["symbol"], reason="Qualified but ranked outside the top five",
                                 observations=p["evidence"]["observations"]) for p in picks[5:])
            self.active = dict(slot=slot, published=now, version=VERSION, picks=picks[:5],
                               diagnostics=dict(subscribed=len(universe), usable=usable, qualified=len(picks),
                                                published=min(5,len(picks)), excluded=rejected),
                               context=context, connected=connected, nifty_move=market_move,
                               t1_deadline=deadlines(slot)[0], t2_deadline=deadlines(slot)[1])
            self.save()

    def recent(self, limit):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute(
                "SELECT payload FROM timed_editions ORDER BY slot DESC LIMIT ?", (limit,))]

    def comparison_labels(self, symbols, now):
        with self.lock:
            if not self.connected or session(now) != "open":
                return {}
            labels = {}
            for symbol in set(symbols) | {"NIFTY"}:
                move = market_change(self.samples.get(symbol, ()), now)
                if move is not None:
                    labels[symbol] = "BULLISH" if move > .002 else "BEARISH" if move < -.002 else "NEUTRAL"
            return labels

    def snapshot(self, now, selected_slot=None):
        """Cheap read projection; does not call the broker, scan, or publish an edition."""
        local = datetime.fromtimestamp(now, IST)
        midnight = local.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        visible = self.recent(40)
        # Prior-session labels are fixed for this day. Keep history reads and
        # evaluation off the quote-processing lock, and cache the daily report.
        with self.connect() as db:
            if not self._research_cache or self._research_cache[0] != midnight:
                earlier = [json.loads(row[0]) for row in db.execute(
                    "SELECT payload FROM timed_editions WHERE slot >= ? AND slot < ?", (midnight-90*86400, midnight))]
                self._research_cache = (midnight, evaluate(earlier, VERSION, midnight))
            if selected_slot and not any(e["slot"] == selected_slot for e in visible):
                row = db.execute("SELECT payload FROM timed_editions WHERE slot = ?", (selected_slot,)).fetchone()
                if row:
                    visible.append(json.loads(row[0]))
        with self.lock:
            connected = self.connected
            samples = {s: tuple(rows) for s, rows in self.samples.items()}
        schedule = day_schedule(now, visible)
        previews, diagnostics = [], []
        benchmark = market_change(samples.get("NIFTY", ()), now)
        next_slot = next((r["slot"] for r in schedule["slots"] if r["slot"] > now), None)
        if connected and session(now) == "open" and next_slot and next_slot-now <= 1200:
            for symbol, rows in samples.items():
                if symbol not in NAMES:
                    p, reason = assess_candidate(symbol, rows, now)
                    if p and benchmark is not None and benchmark*(1 if p["direction"] == "Bullish" else -1) < -.001:
                        p, reason = None, "NIFTY five-minute move opposes this direction by more than 0.1%"
                    if p:
                        p.update(state="Provisional", for_slot=next_slot)
                        previews.append(p)
                    else:
                        diagnostics.append(dict(symbol=symbol, reason=reason))
            previews.sort(key=lambda p: (-p["efficiency"], p["symbol"]))
        return dict(editions=visible, schedule=schedule,
                    preview=dict(for_slot=next_slot, as_of=now, picks=previews[:5], connected=connected,
                                 nifty_move=benchmark, checked=len(previews)+len(diagnostics),
                                 excluded=sorted(diagnostics, key=lambda r: r["symbol"])),
                    research=self._research_cache[1])
