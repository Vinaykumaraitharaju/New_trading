"""Prospective fixed-watchlist comparison. Neither arm changes a trading rule."""
from datetime import datetime
import re

from .market_strip import IST

WATCH = ("RELIANCE","INFY","ICICIBANK","TCS","HDFCBANK","SBIN","BALAXI","CRAVATEX")


def initialize(db):
    db.execute("""CREATE TABLE IF NOT EXISTS news_trial_v1(day TEXT,symbol TEXT,start REAL,price REAL,
        base INTEGER,shadow INTEGER,headline TEXT,known REAL,finish REAL,end_price REAL,
        PRIMARY KEY(day,symbol))""")


def sample(db, batch):
    for day,symbol,close,hi,lo,price,ts,received in batch:
        if symbol not in WATCH or not 0<=received-ts<=60:
            continue
        t=datetime.fromtimestamp(ts,IST)
        minute=t.hour*60+t.minute
        if 555<=minute<660 and hi<close*1.04 and lo>close*.96:
            base=1 if price>close*1.002 else -1 if price<close*.998 else 0
            news=db.execute("""SELECT title,first_seen FROM mover_news_evidence_v1
                WHERE symbol=? AND first_seen<=? AND published<=? AND published>=?
                ORDER BY published DESC,url LIMIT 1""",(symbol,ts,ts,ts-86400)).fetchone()
            title,known=news or (None,None)
            up=bool(re.search(r"\b(order win|wins? .*order|secures? .*contract|profit (?:rises|jumps|grows))\b",title or "",re.I))
            down=bool(re.search(r"\b(penalty|probe|recall|profit (?:falls|drops|declines))\b",title or "",re.I))
            shadow=(1 if up else -1) if up!=down else base
            db.execute("INSERT OR IGNORE INTO news_trial_v1 VALUES(?,?,?,?,?,?,?,?,NULL,NULL)",
                       (day,symbol,ts,price,base,shadow,title,known))
        elif 900<=minute<930:
            db.execute("""UPDATE news_trial_v1 SET finish=?,end_price=?
                WHERE day=? AND symbol=? AND finish IS NULL AND start<?""",(ts,price,day,symbol,ts))


def report(db,today):
    groups=db.execute("""SELECT count(*) total,count(finish) measured,
        count(CASE WHEN finish IS NOT NULL AND base!=shadow THEN 1 END) changed,
        count(CASE WHEN finish IS NULL AND day<? THEN 1 END) missing,
        count(DISTINCT CASE WHEN finish IS NOT NULL THEN day END) sessions,
        avg(CASE WHEN finish IS NOT NULL THEN base*(end_price/price-1)*10000-abs(base)*10 END) price_net,
        avg(CASE WHEN finish IS NOT NULL THEN shadow*(end_price/price-1)*10000-abs(shadow)*10 END) news_net
        FROM news_trial_v1""",(today,)).fetchone()
    return dict(zip(("total","measured","changed","missing","sessions","price_net","news_net"),groups))
