"""Prospective, live-only price-touch forecasts. Never submits or simulates orders."""
from collections import defaultdict, deque
from datetime import datetime
from math import ceil, floor
from threading import RLock
import json
import sqlite3

from .market_strip import IST, NAMES, session

GAP = 45
VERSION = "opening-pressure-v1"
FINAL = {"No entry", "Invalidated", "Missed move", "Stop first", "No timely T1",
         "T2 reached", "T1 then stop", "T1 only", "Insufficient data"}


def candidate(symbol, samples, slot):
    rows = [r for r in samples if slot-300 <= r[0] < slot]
    if (len(rows) < 12 or rows[0][0] > slot-270 or slot-rows[-1][0] > 10
            or any(b[0]-a[0] > GAP for a, b in zip(rows, rows[1:]))):
        return None
    prices = [r[1] for r in rows]
    price, bid, ask = rows[-1][1:4]
    if not 0 < bid <= ask:
        return None
    hi, lo = max(r[4] for r in rows), min(r[5] for r in rows)
    span = hi-lo
    if span < max(price*.0015, 8*(ask-bid), .1):
        return None
    drift = price-prices[0]
    sign = 1 if drift > 0 else -1
    travel = sum(abs(b-a) for a, b in zip(prices, prices[1:]))
    efficiency = abs(drift)/travel if travel else 0
    if efficiency < .5 or (hi-price if sign == 1 else price-lo) > .2*span:
        return None
    # Publish beyond the observed range; don't reward an already-crossed entry.
    entry = (ceil(hi*100)+1 if sign == 1 else floor(lo*100)-1)/100
    risk = max(span*.5, 4*(ask-bid), .05)
    levels = [round(entry+sign*risk*k, 2) for k in (-1, 1, 2)]
    if min(levels) <= 0:
        return None
    return dict(symbol=symbol, direction="Bullish" if sign == 1 else "Bearish",
                entry=entry, stop=levels[0], t1=levels[1], t2=levels[2],
                efficiency=round(efficiency, 3), observed=rows[-1][0], state="Waiting",
                entered=None, hit1=None, ended=None)


class TimedEditions:
    def __init__(self, path):
        self.path = path
        self.lock = RLock()
        self.samples = defaultdict(lambda: deque(maxlen=360))
        self.active = None
        self.last_slot = 0
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS timed_editions(slot INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
            row = db.execute("SELECT payload FROM timed_editions ORDER BY slot DESC LIMIT 1").fetchone()
            if row:
                self.active = json.loads(row[0])
                self.last_slot = self.active["slot"]
                for p in self.active["picks"]:
                    if p["state"] not in FINAL:
                        p["state"] = "Insufficient data"
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
        last = p.get("last", self.active["published"])
        if now < last:
            return
        sign = 1 if p["direction"] == "Bullish" else -1
        if now-last > GAP:
            p["state"] = "Insufficient data"
        elif not p["hit1"] and now >= self.last_slot+600:
            p["state"] = "No timely T1" if p["entered"] else "No entry"
        elif now >= self.last_slot+1200:
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

    def tick(self, now, connected, context=None):
        with self.lock:
            if not connected:
                self.samples.clear()
            if self.active:
                changed = False
                for p in self.active["picks"]:
                    if p["state"] not in FINAL:
                        old = p["state"]
                        if not connected:
                            p.update(state="Insufficient data", ended=now)
                        else:
                            self.advance(p, now)
                        changed |= old != p["state"]
                if changed:
                    self.save()
            local = datetime.fromtimestamp(now, IST)
            minute = local.hour*60+local.minute
            slot = int(local.replace(second=0, microsecond=0).timestamp())
            if (minute < 560 or minute > 900 or (minute-560)%20 or now-slot >= 5
                    or slot <= self.last_slot or session(slot) != "open"):
                return
            picks = []
            market = [r for r in self.samples.get("NIFTY", ()) if slot-300 <= r[0] < slot]
            market_move = None
            if (len(market)>=2 and market[0][0]<=slot-270 and slot-market[-1][0]<=10
                    and all(b[0]-a[0]<=GAP for a,b in zip(market, market[1:]))):
                market_move = market[-1][1]/market[0][1]-1
            if connected:
                for symbol, rows in self.samples.items():
                    if symbol in NAMES:
                        continue
                    p = candidate(symbol, rows, slot)
                    if p and market_move is not None and market_move*(1 if p["direction"]=="Bullish" else -1)<-.001:
                        continue
                    if p and not any(r[0] >= slot and (r[4] >= p["entry"] if p["direction"]=="Bullish"
                                                        else r[5] <= p["entry"]) for r in rows):
                        picks.append(p)
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
                         shadow_score=p["efficiency"]+adjustment)
            for rank, p in enumerate(sorted(picks[:5], key=lambda p: -p["shadow_score"]), 1):
                p["shadow_rank"] = rank
            self.last_slot = slot
            self.active = dict(slot=slot, published=now, version=VERSION, picks=picks[:5],
                               context=context, connected=connected, nifty_move=market_move)
            self.save()

    def recent(self, limit):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute(
                "SELECT payload FROM timed_editions ORDER BY slot DESC LIMIT ?", (limit,))]
