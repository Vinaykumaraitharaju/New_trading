from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path("storage") / "scanner_history.sqlite"


def init_db(path: Path = DB_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                source TEXT NOT NULL,
                symbols_scanned INTEGER NOT NULL,
                shortlisted INTEGER NOT NULL,
                top_json TEXT NOT NULL
            )
            """
        )


def save_scan(created_at: str, source: str, symbols_scanned: int, shortlisted: int, top_df: pd.DataFrame, path: Path = DB_PATH) -> None:
    init_db(path)
    payload = top_df.head(5).to_dict(orient="records") if not top_df.empty else []
    with sqlite3.connect(path) as con:
        con.execute(
            "INSERT INTO scans(created_at, source, symbols_scanned, shortlisted, top_json) VALUES (?, ?, ?, ?, ?)",
            (created_at, source, int(symbols_scanned), int(shortlisted), json.dumps(payload, default=str)),
        )


def recent_scans(limit: int = 8, path: Path = DB_PATH) -> pd.DataFrame:
    init_db(path)
    with sqlite3.connect(path) as con:
        return pd.read_sql_query(
            "SELECT created_at, source, symbols_scanned, shortlisted FROM scans ORDER BY id DESC LIMIT ?",
            con,
            params=(limit,),
        )
