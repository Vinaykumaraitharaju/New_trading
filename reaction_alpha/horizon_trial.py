"""Parallel paper research on identical entries; no changes to the published trade."""
from datetime import datetime
import sqlite3

from .market_strip import IST

WINDOWS = (10, 20, 30)


class HorizonTrials:
    def __init__(self, path):
        self.path = path
        self.live = {}
        with sqlite3.connect(path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS ra_horizon_v1 (
                id TEXT, minutes INTEGER, day TEXT, status TEXT, net_bps REAL,
                PRIMARY KEY(id,minutes))""")
            db.execute("UPDATE ra_horizon_v1 SET status='Missing data' WHERE status='Tracking'")

    def start(self, p, now, bid, ask):
        local = datetime.fromtimestamp(now, IST)
        close = local.replace(hour=15, minute=30, second=0, microsecond=0).timestamp()
        # All three horizons need the same full session opportunity.
        eligible = now + 1800 < close
        side = 1 if p["direction"] == "Bullish" else -1
        fill = (ask if side==1 else bid) if 0 < bid <= ask else None
        key = p["id"]
        with sqlite3.connect(self.path) as db:
            db.executemany("INSERT INTO ra_horizon_v1 VALUES (?,?,?,?,NULL)",
                           [(key,w,local.date().isoformat(),"Tracking" if eligible else "Too near close") for w in WINDOWS])
        if eligible:
            self.live[key] = dict(symbol=p["symbol"],start=now,last=now,side=side,fill=fill,
                                  stop=p["stop"],t1=p["t1"],pending=set(WINDOWS))

    def update(self, now, symbol=None, price=None, bid=0, ask=0, connected=True):
        finished = []
        for key,r in list(self.live.items()):
            if (symbol is not None and symbol!=r["symbol"]) or now<r["last"]:
                continue
            for w in list(r["pending"]):
                due = r["start"] + w*60
                status = None
                if not connected or now-r["last"]>45:
                    status = "Missing data"
                elif now>=due:
                    if price is not None and now-due<=15:
                        status = "Timed exit"
                    elif now-due>15:
                        status = "Missing data"
                elif price is not None and now>r["start"]:
                    if r["side"]*(price-r["stop"])<=0:
                        status = "Stop first"
                    elif r["side"]*(price-r["t1"])>=0:
                        status = "T1 first"
                if status:
                    exit_price = (bid if r["side"]==1 else ask) if 0<bid<=ask else None
                    net = None
                    if status!="Missing data" and r["fill"] and exit_price:
                        net = 10000*r["side"]*(exit_price/r["fill"]-1)-10
                    finished.append((status,net,key,w))
                    r["pending"].remove(w)
            if price is not None:
                r["last"]=now
            if not r["pending"]:
                del self.live[key]
        if finished:
            with sqlite3.connect(self.path) as db:
                db.executemany("UPDATE ra_horizon_v1 SET status=?,net_bps=? WHERE id=? AND minutes=?",finished)

    def report(self):
        with sqlite3.connect(self.path) as db:
            db.row_factory=sqlite3.Row
            return [dict(r) for r in db.execute("""WITH paired AS (
                SELECT id FROM ra_horizon_v1 GROUP BY id HAVING count(net_bps)=3)
                SELECT minutes,count(*) entries,sum(status='T1 first') hits,sum(status='Stop first') stops,
                sum(status='Timed exit') timed,sum(status='Missing data') missing,
                sum(status='Tracking') tracking,sum(status='Too near close') late,
                count(paired.id) paired,count(DISTINCT CASE WHEN paired.id IS NOT NULL THEN day END) sessions,
                round(avg(CASE WHEN paired.id IS NOT NULL THEN net_bps END),2) avg_net_bps
                FROM ra_horizon_v1 LEFT JOIN paired USING(id) GROUP BY minutes ORDER BY minutes""")]
