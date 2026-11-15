"""Small, append-only training set. No broker credentials, orders or raw tick streams."""
import os
import re
import threading
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

VERSION = "direction-frequency-v1"
LABELS = ("BULLISH", "BEARISH", "NEUTRAL")
IST = ZoneInfo("Asia/Kolkata")
TABLE = """CREATE TABLE IF NOT EXISTS ra_experience_v1 (
    id INTEGER PRIMARY KEY, source TEXT NOT NULL, symbol TEXT NOT NULL, setup TEXT NOT NULL, direction TEXT NOT NULL,
    published TEXT NOT NULL, day TEXT NOT NULL, actual TEXT NOT NULL, shadow TEXT,
    UNIQUE(source,symbol,setup,direction,published))"""
COLUMNS = "source,symbol,setup,direction,published,day,actual,shadow"
INSERT = f"INSERT OR IGNORE INTO ra_experience_v1 ({COLUMNS}) VALUES (?,?,?,?,?,?,?,?)"
GROUPS = """SELECT source,setup,direction,COUNT(*) n,COUNT(DISTINCT day) days,
    SUM(actual='BULLISH') bullish,SUM(actual='BEARISH') bearish,SUM(actual='NEUTRAL') neutral,
    COUNT(shadow) paired,SUM(CASE WHEN shadow=actual THEN 1 ELSE 0 END) learned_correct,
    SUM(CASE WHEN shadow IS NOT NULL AND direction=actual THEN 1 ELSE 0 END) original_correct
    FROM ra_experience_v1 WHERE day < ? GROUP BY source,setup,direction"""


def init_memory(conn):
    conn.execute(TABLE)
    conn.execute("""CREATE TABLE IF NOT EXISTS ra_uploaded_v1 (
                 destination TEXT NOT NULL, experience_id INTEGER NOT NULL, PRIMARY KEY(destination, experience_id))""")
    select = """SELECT t.source,t.symbol,p.setup_type,p.direction,t.published_at,
                date(t.ended_at,'utc','+330 minutes'),t.actual,
                t.shadow_direction
                FROM pretrade_direction_trials t JOIN pretrade_predictions p ON p.id=t.setup_id
                WHERE t.actual IN ('BULLISH','BEARISH','NEUTRAL') AND t.ended_at IS NOT NULL"""
    # Capture the measured label in the same commit, even if the service dies before cloud sync.
    conn.execute(f"""CREATE TRIGGER IF NOT EXISTS ra_capture_v1 AFTER UPDATE OF actual ON pretrade_direction_trials
                 WHEN NEW.actual IS NOT NULL AND OLD.actual IS NULL BEGIN
                 INSERT OR IGNORE INTO ra_experience_v1 ({COLUMNS}) {select} AND t.setup_id=NEW.setup_id; END""")
    conn.execute(f"INSERT OR IGNORE INTO ra_experience_v1 ({COLUMNS}) {select}")


class Turso:
    def __init__(self, url, token):
        match = re.fullmatch(r"(?:https|libsql)://([a-z0-9-]+\.turso\.io)/?", url)
        if not match or not token:
            raise ValueError("Configure both TURSO_DATABASE_URL and TURSO_AUTH_TOKEN for the hosted database.")
        self.url = "https://" + match[1] + "/v2/pipeline"
        self.headers = {"Authorization": "Bearer " + token}

    def run(self, statements):
        def arg(v):
            return {"type": "null"} if v is None else {"type": "text", "value": str(v)}
        req = [{"type": "execute", "stmt": {"sql": sql, "args": [arg(v) for v in args]}}
               for sql, args in statements]
        r = requests.post(self.url, headers=self.headers, json={"requests": req + [{"type": "close"}]},
                          timeout=(3, 8), allow_redirects=False)
        r.raise_for_status()
        results = r.json()["results"]
        if len(results) != len(req)+1 or any(item["type"] != "ok" for item in results):
            raise RuntimeError("Database did not acknowledge the batch")
        last = results[-2]["response"]["result"]
        names = [c["name"] for c in last["cols"]]
        return [dict(zip(names, [int(v["value"]) if v["type"]=="integer" else v.get("value") for v in row]))
                for row in last["rows"]]


class Experience:
    def __init__(self, book):
        self.book = book
        self.remote = None
        self.groups = {}
        self.day = None
        self.last_sync = None
        self.state = "Local only"
        self.guard = threading.Lock()
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.thread = None
        self.initialized = False

    def configure_cloud(self):
        url, token = os.getenv("TURSO_DATABASE_URL"), os.getenv("TURSO_AUTH_TOKEN")
        if url or token:
            self.remote = Turso(url or "", token or "")
            self.state = "Awaiting cloud sync"

    def sync(self, today=None):
        today = today or datetime.now(IST).date().isoformat()
        if self.remote:
            if not self.initialized:
                self.remote.run([(TABLE, ())])
                self.initialized = True
            with self.book._connect() as conn:
                pending = conn.execute(f"""SELECT rowid AS local_id,{COLUMNS} FROM ra_experience_v1
                    WHERE rowid NOT IN (SELECT experience_id FROM ra_uploaded_v1 WHERE destination=?)
                    ORDER BY rowid LIMIT 100""", (self.remote.url,)).fetchall()
            if pending:
                self.remote.run([(INSERT, tuple(row)[1:]) for row in pending])
                with self.book._connect() as conn:
                    conn.executemany("INSERT OR IGNORE INTO ra_uploaded_v1 VALUES (?,?)",
                                     [(self.remote.url, r[0]) for r in pending])
            # Reload aggregates on cold start and at session boundaries, not on every tick.
            if self.day != today or any(r["day"] < today for r in pending):
                rows = self.remote.run([(GROUPS, (today,))])
            else:
                return
        else:
            with self.book._connect() as conn:
                rows = conn.execute(GROUPS, (today,)).fetchall()
        with self.guard:
            self.groups = {(r["source"],r["setup"],r["direction"]):dict(r) for r in rows}
            self.day = today
            self.state = "Cloud connected" if self.remote else "Local only"
            self.last_sync = datetime.now(IST).isoformat(timespec="seconds")

    def start(self):
        def work():
            while True:
                finishing = self.stop.is_set()
                self.wake.clear()
                try:
                    self.sync()
                except Exception:
                    logging.getLogger(__name__).warning("Experience sync unavailable; local examples retained for retry")
                    with self.guard:
                        self.state = "Sync failed; retrying"
                        self.day = None
                if finishing:
                    return
                self.wake.wait(60)
        self.thread = threading.Thread(target=work, name="experience-sync", daemon=True)
        self.thread.start()

    def shutdown(self):
        self.stop.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=12)

    def predict(self, source, setup, direction, stamp):
        day = stamp.astimezone(IST).date().isoformat()
        with self.guard:
            row = self.groups.get((source,setup,direction), {}) if self.day == day else {}
        counts = sorted(((row.get(label.lower(),0),label) for label in LABELS), reverse=True)
        enough = row.get("n",0)>=30 and row.get("days",0)>=5 and counts[0][0]>counts[1][0]
        return {"version": VERSION, "direction": counts[0][1] if enough else None,
                "examples":row.get("n",0), "sessions":row.get("days",0)}

    def report(self):
        with self.book._connect() as conn:
            pending = conn.execute("""SELECT COUNT(*) FROM ra_experience_v1 WHERE rowid NOT IN
                                   (SELECT experience_id FROM ra_uploaded_v1 WHERE destination=?)""",
                                   (self.remote.url,)).fetchone()[0] if self.remote else None
        with self.guard:
            return {"storage":self.state, "last_sync":self.last_sync, "before_session":self.day,
                    "pending_upload":pending,"version":VERSION, "groups":list(self.groups.values())}
