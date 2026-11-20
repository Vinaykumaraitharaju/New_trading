"""Timestamped media evidence for retrospective research, never a trigger input."""
from datetime import datetime
from email.utils import parsedate_to_datetime
import json
import re
import sqlite3
import time
from urllib.parse import urlsplit
from xml.etree import ElementTree

import requests
from data.stock_news import _normalize_text, _query_text
from .market_strip import IST


EVENTS = [
    ("Order or contract",r"order win|wins? .*order|bags? .*order|contract award|secures? .*contract"),
    ("Financial results",r"\b(earnings|profit|revenue|quarterly results|q[1-4] results)\b"),
    ("Regulatory event",r"\b(approval|probe|penalty|ban|recall|clearance)\b"),
    ("Ownership or management",r"\b(acquisition|merger|stake sale|resignation|resigns|buyback)\b"),
]


def evidence(xml,symbol,name,now):
    clean=re.sub(r"\s+(?:limited|ltd)\.?$","",name.strip(),flags=re.I)
    aliases=[s for s in (clean,symbol) if len(s)>=4]
    found=[]
    seen=set()
    for item in ElementTree.fromstring(xml).findall("./channel/item"):
        title=_normalize_text(item.findtext("title")).rsplit(" - ",1)[0]
        if not any(re.search(r"(?<!\w)"+re.escape(s)+r"(?!\w)",title,re.I) for s in aliases):
            continue
        try:
            stamp=parsedate_to_datetime(item.findtext("pubDate")).timestamp()
            link=(item.findtext("link") or "").strip()
            parsed=urlsplit(link)
        except (ValueError,TypeError,OverflowError):
            continue
        if not now-7*86400<=stamp<=now or parsed.scheme!="https" or not parsed.hostname or title.casefold() in seen:
            continue
        kind=next((k for k,p in EVENTS if re.search(p,title,re.I)),None)
        if kind:
            seen.add(title.casefold())
            found.append(dict(title=title[:300],publisher=_normalize_text(item.findtext("source")) or "Publisher unspecified",
                              url=link,published=stamp,kind=kind))
    return sorted(found,key=lambda r:-r["published"])[:2]


class MoverNews:
    def __init__(self,path):
        self.path=path
        with sqlite3.connect(path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS mover_news_v1(day TEXT,symbol TEXT,detected REAL,
                checked REAL,status TEXT,items TEXT,PRIMARY KEY(day,symbol))""")
            db.execute("""CREATE TABLE IF NOT EXISTS mover_news_evidence_v1(symbol TEXT,url TEXT,
                first_seen REAL,published REAL,category TEXT,title TEXT,publisher TEXT,PRIMARY KEY(symbol,url))""")

    def step(self,names,now):
        day=datetime.fromtimestamp(now,IST).date().isoformat()
        with sqlite3.connect(self.path) as db:
            db.execute("""INSERT OR IGNORE INTO mover_news_v1 SELECT day,symbol,checked,0,'Queued','[]'
                FROM mover_sweep_v1 WHERE day=? AND (high>=round(close*1.04,8) OR low<=round(close*.96,8))""",(day,))
            row=db.execute("""SELECT symbol FROM mover_news_v1 WHERE day=? AND checked<?
                ORDER BY checked,detected,symbol LIMIT 1""",(day,now-1800)).fetchone()
        if not row:
            return 15
        symbol=row[0]
        name=names.get(symbol,"")
        delay=8
        try:
            response=requests.get("https://news.google.com/rss/search",params={
                "q":_query_text(symbol,name)+" when:7d","hl":"en-IN","gl":"IN","ceid":"IN:en"},timeout=(3,8))
            response.raise_for_status()
            checked=time.time()
            items=evidence(response.content,symbol,name,checked)
            status="Possible catalyst" if items else "No matching event headline"
        except (requests.RequestException,ElementTree.ParseError,ValueError):
            items=None
            checked=time.time()
            status="News feed unavailable"
            delay=90
        with sqlite3.connect(self.path) as db:
            db.executemany("INSERT OR IGNORE INTO mover_news_evidence_v1 VALUES (?,?,?,?,?,?,?)",
                [(symbol,a["url"],checked,a["published"],a["kind"],a["title"],a["publisher"]) for a in items or []])
            db.execute("UPDATE mover_news_v1 SET checked=?,status=?,items=coalesce(?,items) WHERE day=? AND symbol=?",
                       (checked,status,json.dumps(items) if items is not None else None,day,symbol))
        return delay

    def run(self,stop,sweep):
        while not stop.is_set():
            try:
                delay=self.step(sweep.company_names,time.time())
            except sqlite3.Error:
                delay=60
            stop.wait(delay)
