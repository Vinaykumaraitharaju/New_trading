"""Prospective, live-only studies of observed +/-4% moves. Never sends orders."""
from collections import Counter, defaultdict
from datetime import datetime
import json
from math import isfinite
import sqlite3
from threading import RLock

from .market_strip import IST, NAMES, session


class DailyMovers:
    def __init__(self, path):
        self.path = path
        self.day = None
        self.rows = {}
        self.lock = RLock()
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS daily_movers_v1(day TEXT,symbol TEXT,payload TEXT NOT NULL,PRIMARY KEY(day,symbol))")

    def _load(self, day):
        groups = defaultdict(list)
        self.paired = self.correct = self.neither_correct = 0
        with sqlite3.connect(self.path) as db:
            for (raw,) in db.execute("SELECT payload FROM daily_movers_v1 WHERE day < ? AND day >= date(?, '-180 days')", (day, day)):
                row = json.loads(raw)
                if row["group"] and row["outcome"]:
                    groups[row["group"]].append((row["day"], row["outcome"]))
                    if row["prediction"]:
                        self.paired += 1
                        self.correct += row["prediction"] == row["outcome"]
                        self.neither_correct += row["outcome"] == "Neither"
            self.rows = {s:json.loads(raw) for s,raw in db.execute(
                "SELECT symbol,payload FROM daily_movers_v1 WHERE day=?", (day,))}
        self.groups, self.day = groups, day

    def observe(self, symbol, ts, price, close, filing=None, nifty=None):
        if symbol in NAMES or not close or not all(isfinite(v) and v > 0 for v in (price,close)) or session(ts) != "open":
            return
        local = datetime.fromtimestamp(ts, IST)
        day = local.date().isoformat()
        with self.lock:
            if self.day != day:
                self._load(day)
            row = self.rows.get(symbol)
            if row and (ts < row["last"] or close != row["close"]):
                return
            move = 100*(price-close)/close
            side = "Up" if price >= round(close*1.04, 8) else "Down" if price <= round(close*.96, 8) else None
            dirty = not row
            if not row:
                bucket = ("up" if move >= 1 else "down" if move <= -1 else "near close")
                group = None if side else f"{local.hour:02d}:{local.minute//30*30:02d} / {bucket}"
                prior = self.groups.get(group, [])
                counts = Counter(label for _,label in prior)
                days = len({d for d,_ in prior})
                leaders = counts.most_common()
                prediction = leaders[0][0] if len(prior)>=30 and days>=5 and (len(leaders)==1 or leaders[0][1]>leaders[1][1]) else None
                row = self.rows[symbol] = dict(symbol=symbol,day=day,close=close,start=ts,start_pct=move,
                    group=group,prior_counts=dict(counts),prior_days=days,prediction=prediction,
                    outcome=None,hits={},gap=False,last=ts,saved=ts)
            if ts-row["last"] > 45 and not row["gap"]:
                row["gap"],dirty = True,True
            row.update(last=ts,price=price,percent=move)
            if side and side not in row["hits"]:
                verified = filing and filing.get("published",ts+1)<=ts and filing.get("received",ts+1)<=ts
                benchmark = None
                if nifty and nifty.get("previous_close") and 0 <= ts-nifty["epoch"] <= 15:
                    benchmark = 100*(nifty["price"]-nifty["previous_close"])/nifty["previous_close"]
                row["hits"][side] = dict(at=ts,price=price,percent=move,nifty_pct=benchmark,filing=filing if verified else None,
                                         first_observation=row["start"],initial_pct=row["start_pct"])
                if row["group"] and not row["outcome"] and not row["gap"]:
                    row["outcome"] = side
                dirty = True
            # No-touch labels require observation through the closing seconds.
            if local.hour==15 and local.minute==29 and local.second>=45 and row["group"] and not row["gap"] and not row["hits"] and row["outcome"] is None:
                row["outcome"] = "Neither"
                dirty = True
            if side and row["outcome"]=="Neither":
                row["outcome"] = side
            if dirty or ts-row["saved"]>=60:
                row["saved"]=ts
                with sqlite3.connect(self.path) as db:
                    db.execute("INSERT OR REPLACE INTO daily_movers_v1 VALUES (?,?,?)",(day,symbol,json.dumps(row,allow_nan=False)))

    def report(self, now):
        day = datetime.fromtimestamp(now,IST).date().isoformat()
        with self.lock:
            if self.day != day:
                self._load(day)
            rows = list(self.rows.values())
            return dict(day=day, covered=len(rows), training_examples=sum(map(len,self.groups.values())),
                paired=self.paired,correct=self.correct,neither_correct=self.neither_correct,
                movers=[dict(symbol=r["symbol"],close=r["close"],side=side,**hit)
                        for r in sorted(rows,key=lambda r:r["symbol"]) for side,hit in r["hits"].items()],
                forecasts=[{k:r[k] for k in ("symbol","start","start_pct","prediction","prior_counts","prior_days","outcome")}
                           for r in rows if r["group"]])
