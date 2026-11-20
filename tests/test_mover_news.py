from email.utils import formatdate
import sqlite3
from types import SimpleNamespace
from reaction_alpha.mover_news import evidence
from reaction_alpha.mover_sweep import MoverSweep


def rss(title,stamp,url="https://example.org/story"):
    return f"<rss><channel><item><title>{title} - Journal</title><link>{url}</link><source>Journal</source><pubDate>{formatdate(stamp,usegmt=True)}</pubDate></item></channel></rss>"


def test_evidence_requires_event_identity_date_and_safe_link():
    now=1795064305
    for title,stamp,url in [("Unrelated profit rises",now,"https://example.org"),
         ("Balaxi shares rally",now,"https://example.org"),("Balaxi profit rises",now+60,"https://example.org"),
         ("Balaxi profit rises",now-8*86400,"https://example.org"),("Balaxi profit rises",now,"javascript:void(0)")]:
        assert not evidence(rss(title,stamp,url),"BALAXI","Balaxi Pharmaceuticals Ltd",now)
    a,=evidence(rss("Balaxi profit rises",now),"BALAXI","",now)
    assert a["kind"]=="Financial results" and a["publisher"]=="Journal"


def test_worker_persists_link_and_does_not_refetch_on_report(tmp_path,monkeypatch):
    import reaction_alpha.mover_news as ns
    now=1795064305
    b=MoverSweep(tmp_path/"paper.db")
    with sqlite3.connect(b.path) as db:
        db.execute("INSERT INTO mover_sweep_v1 VALUES (?,?,?,?,?,?,?,?)",("2026-11-19","BALAXI",100,105,99,101,now,now))
    calls=[]
    def fetch(*args,**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(content=rss("Balaxi revenue grows",now-60),raise_for_status=lambda:None)
    monkeypatch.setattr(ns.requests,"get",fetch)
    monkeypatch.setattr(ns.time,"time",lambda:now)
    b.news.step({},now)
    b.news.step({},now+10)
    n=MoverSweep(b.path).report(now)["movers"][0]["news"]
    assert len(calls)==2 and calls[0]["params"]["q"]!=calls[1]["params"]["q"]
    assert n["detected"]==now and n["items"][0]["published"]==now-60
