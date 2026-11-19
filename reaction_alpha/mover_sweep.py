"""Read-only NSE EQ discovery, isolated from live triggers and forecast labels."""
from datetime import datetime
from math import isfinite
import sqlite3
import time
import logging

from .market_strip import IST, session


def eq_universe(master):
    result = {}
    for r in master.to_dict("records"):
        name = str(r.get("trading_symbol") or "").strip().upper()
        series = str(r.get("pGroup") or r.get("series") or "").strip().upper()
        if not name.endswith("-EQ") and series != "EQ":
            continue
        token = next((r[k] for k in ("instrument_token","pSymbol","token","scrip_token") if r.get(k)), None)
        if token and name:
            result[name.removesuffix("-EQ")] = {"instrument_token":str(token), "exchange_segment":"nse_cm"}
    return result


def trade_epoch(raw):
    value = next((raw[k] for k in ("last_trade_time","last_traded_time","lastTradeTime","ltt") if raw.get(k)), None)
    try:
        n = float(value)
        return n/1000 if n >= 1e12 else n
    except (TypeError, ValueError):
        pass
    for fmt in ("%d/%m/%Y %H:%M:%S","%d-%m-%Y %H:%M:%S","%Y-%m-%d %H:%M:%S","%d-%b-%Y %H:%M:%S"):
        try:
            return datetime.strptime(str(value),fmt).replace(tzinfo=IST).timestamp()
        except ValueError:
            continue
    return None


class MoverSweep:
    def __init__(self,path):
        self.path = path
        self.status = "Waiting for an open session and connected Kotak feed"
        self.total = 0
        with sqlite3.connect(path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS mover_sweep_v1(day TEXT,symbol TEXT,close REAL,high REAL,low REAL,
                price REAL,trade REAL,checked REAL,PRIMARY KEY(day,symbol))""")

    def ingest(self, quotes, now):
        day = datetime.fromtimestamp(now,IST).date()
        batch = []
        for symbol,r in quotes.items():
            ts = trade_epoch(r.get("raw") or {})
            if not ts or not isfinite(ts) or not now-86400 < ts <= now or datetime.fromtimestamp(ts,IST).date()!=day or session(ts)!="open":
                continue
            try:
                close,hi,lo,ltp = (float(r[k]) for k in ("prev_close","high","low","ltp"))
            except (KeyError,ValueError,TypeError):
                continue
            if all(isfinite(x) and x>0 for x in (close,hi,lo,ltp)) and lo<=ltp<=hi:
                batch.append((day.isoformat(),symbol,close,hi,lo,ltp,ts,now))
        with sqlite3.connect(self.path) as db:
            db.executemany("""INSERT INTO mover_sweep_v1 VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(day,symbol)
                DO UPDATE SET high=excluded.high, low=excluded.low,price=excluded.price,close=excluded.close,
                trade=excluded.trade,checked=excluded.checked WHERE excluded.trade>=trade""",batch)
        return len(batch)

    def report(self,now):
        day = datetime.fromtimestamp(now,IST).date().isoformat()
        with sqlite3.connect(self.path) as db:
            db.row_factory=sqlite3.Row
            n=db.execute("SELECT count(*) FROM mover_sweep_v1 WHERE day=?",(day,)).fetchone()[0]
            moves=[dict(r) for r in db.execute("""SELECT symbol,price,trade,100*(price-close)/close AS current_pct,
                100*(high-close)/close AS high_pct,100*(low-close)/close AS low_pct,
                high>=round(close*1.04,8) AS up,low<=round(close*.96,8) AS down FROM mover_sweep_v1
                WHERE day=? AND (high>=round(close*1.04,8) OR low<=round(close*.96,8))
                ORDER BY max(abs(high_pct),abs(low_pct)) DESC,symbol""",(day,))]
        return dict(universe=self.total,covered=n,status=self.status,movers=moves)

    def run(self,stop,get_feed):
        day=None
        cursor=0
        while not stop.is_set():
            delay=5
            try:
                now=time.time()
                feed=get_feed()
                if session(now)!="open" or not feed or not feed.stream_connected:
                    self.status="Paused: outside session or feed disconnected"
                else:
                    today=datetime.fromtimestamp(now,IST).date()
                    if today!=day:
                        instruments=eq_universe(feed.scrip_master("nse_cm"))
                        names=sorted(instruments)
                        if not names:
                            raise ValueError("Empty NSE EQ universe")
                        self.total,day,cursor=len(names),today,0
                    chunk=names[cursor:cursor+50]
                    quotes=feed.quote_token_snapshot({k:instruments[k] for k in chunk})
                    accepted=self.ingest(quotes,time.time())
                    cursor=(cursor+len(chunk))%len(names)
                    self.status=f"Last batch: {accepted}/{len(chunk)} dated quotes usable"
            except Exception as exc:
                self.status="Sweep unavailable; retrying after 60 seconds"
                logging.getLogger(__name__).warning("Mover sweep paused (%s)",type(exc).__name__)
                delay=60
            stop.wait(delay)
