from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, time as dt_time, timedelta
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .config import ReactionAlphaConfig
from .models import TradeSignal


@dataclass(slots=True)
class ActivePaperTrade:
    id: int
    symbol: str
    direction: str
    state: str
    created_at: datetime
    entry_trigger: float
    stop_loss: float
    target1: float
    target2: float
    t1_hit: bool
    t2_hit: bool
    mae_points: float
    mfe_points: float
    trigger_price: float | None


@dataclass(slots=True)
class PendingTrigger:
    id: int
    symbol: str
    direction: str
    state: str
    created_at: datetime
    expires_at: datetime
    entry_trigger: float
    stop_loss: float
    target1: float
    target2: float
    signal: str
    setup_type: str
    regime: str
    score: int
    confidence: str


class PaperTradeBook:
    def __init__(self, config: ReactionAlphaConfig) -> None:
        self.config = config
        self._lock = threading.RLock()
        self.db_path = Path(config.paper_trade_db_path)
        if not self.db_path.is_absolute():
            self.db_path = Path.cwd() / self.db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @staticmethod
    def session_date(timestamp: datetime | None = None) -> str:
        current = timestamp or datetime.now(ZoneInfo("Asia/Kolkata"))
        if current.tzinfo is None:
            current = current.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
        return current.astimezone(ZoneInfo("Asia/Kolkata")).date().isoformat()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    signal TEXT NOT NULL,
                    setup_type TEXT NOT NULL,
                    regime TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    state TEXT NOT NULL,
                    result TEXT NOT NULL DEFAULT 'OPEN',
                    score INTEGER NOT NULL DEFAULT 0,
                    confidence TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    entry_trigger REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    target1 REAL NOT NULL,
                    target2 REAL NOT NULL,
                    trigger_price REAL,
                    entered_at TEXT,
                    exit_price REAL,
                    exited_at TEXT,
                    gross_pnl_points REAL NOT NULL DEFAULT 0,
                    cost_points REAL NOT NULL DEFAULT 0,
                    pnl_points REAL NOT NULL DEFAULT 0,
                    mae_points REAL NOT NULL DEFAULT 0,
                    mfe_points REAL NOT NULL DEFAULT 0,
                    sl_category TEXT,
                    t1_hit INTEGER NOT NULL DEFAULT 0,
                    t2_hit INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL UNIQUE,
                    signal TEXT NOT NULL,
                    setup_type TEXT NOT NULL,
                    regime TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    score INTEGER NOT NULL DEFAULT 0,
                    confidence TEXT NOT NULL DEFAULT '',
                    state TEXT NOT NULL DEFAULT 'READY',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    entry_trigger REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    target1 REAL NOT NULL,
                    target2 REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pretrade_predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    setup_type TEXT NOT NULL,
                    regime TEXT NOT NULL,
                    scanner_band TEXT NOT NULL DEFAULT '',
                    scanner_label TEXT NOT NULL DEFAULT '',
                    state TEXT NOT NULL DEFAULT 'WATCHING',
                    result TEXT NOT NULL DEFAULT 'OPEN',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    entered_at TEXT,
                    exited_at TEXT,
                    initial_price REAL NOT NULL,
                    latest_price REAL NOT NULL,
                    entry_trigger REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    target1 REAL NOT NULL,
                    target2 REAL NOT NULL,
                    exit_price REAL,
                    score REAL NOT NULL DEFAULT 0,
                    target_probability REAL NOT NULL DEFAULT 0,
                    relative_opportunity REAL NOT NULL DEFAULT 0,
                    observation_count INTEGER NOT NULL DEFAULT 1,
                    t1_hit INTEGER NOT NULL DEFAULT 0,
                    t2_hit INTEGER NOT NULL DEFAULT 0,
                    mfe_points REAL NOT NULL DEFAULT 0,
                    mae_points REAL NOT NULL DEFAULT 0,
                    context_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_paper_trades_symbol_state ON paper_trades(symbol, state)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_paper_trades_created_at ON paper_trades(created_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_paper_candidates_updated_at ON paper_candidates(updated_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pretrade_predictions_symbol_state ON pretrade_predictions(symbol, state)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pretrade_predictions_created_at ON pretrade_predictions(created_at DESC)")
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(paper_trades)").fetchall()}
            if "gross_pnl_points" not in columns:
                conn.execute("ALTER TABLE paper_trades ADD COLUMN gross_pnl_points REAL NOT NULL DEFAULT 0")
            if "cost_points" not in columns:
                conn.execute("ALTER TABLE paper_trades ADD COLUMN cost_points REAL NOT NULL DEFAULT 0")
            if "sl_category" not in columns:
                conn.execute("ALTER TABLE paper_trades ADD COLUMN sl_category TEXT")
            self._migrate_pending_trades_to_candidates(conn)

    def _migrate_pending_trades_to_candidates(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            """
            SELECT *
            FROM paper_trades
            WHERE state = 'PENDING'
            """
        ).fetchall()
        for row in rows:
            expires_at = (
                datetime.fromisoformat(str(row["created_at"])) + timedelta(minutes=self.config.paper_trade_pending_expiry_min)
            ).isoformat(timespec="seconds")
            conn.execute(
                """
                INSERT INTO paper_candidates (
                    symbol, signal, setup_type, regime, direction, score, confidence, state,
                    created_at, updated_at, expires_at, entry_trigger, stop_loss, target1, target2
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'READY', ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    signal = excluded.signal,
                    setup_type = excluded.setup_type,
                    regime = excluded.regime,
                    direction = excluded.direction,
                    score = excluded.score,
                    confidence = excluded.confidence,
                    updated_at = excluded.updated_at,
                    expires_at = excluded.expires_at,
                    entry_trigger = excluded.entry_trigger,
                    stop_loss = excluded.stop_loss,
                    target1 = excluded.target1,
                    target2 = excluded.target2
                """,
                (
                    str(row["symbol"]).upper(),
                    str(row["signal"]),
                    str(row["setup_type"]),
                    str(row["regime"]),
                    str(row["direction"]),
                    int(row["score"] or 0),
                    str(row["confidence"] or ""),
                    str(row["created_at"]),
                    str(row["updated_at"]),
                    expires_at,
                    float(row["entry_trigger"]),
                    float(row["stop_loss"]),
                    float(row["target1"]),
                    float(row["target2"]),
                ),
            )
        if rows:
            conn.execute("DELETE FROM paper_trades WHERE state = 'PENDING'")

    def archive_pretrade_setups(self, setups: list[dict[str, Any]], *, generated_at: datetime | None = None, source: str = "") -> None:
        if not setups:
            return
        now_dt = generated_at or datetime.now()
        now = now_dt.isoformat(timespec="seconds")
        expires_at = (now_dt + timedelta(minutes=max(self.config.paper_trade_max_hold_min, 1))).isoformat(timespec="seconds")
        with self._lock, self._connect() as conn:
            for setup in setups:
                parsed = self._parse_pretrade_setup(setup)
                if parsed is None:
                    continue
                existing = conn.execute(
                    """
                    SELECT id
                    FROM pretrade_predictions
                    WHERE symbol = ? AND direction = ? AND setup_type = ? AND state IN ('WATCHING', 'ENTERED')
                    ORDER BY id DESC LIMIT 1
                    """,
                    (parsed["symbol"], parsed["direction"], parsed["setup_type"]),
                ).fetchone()
                context = self._pretrade_context_json(setup, source=source)
                if existing is not None:
                    conn.execute(
                        """
                        UPDATE pretrade_predictions
                        SET updated_at = ?, last_seen_at = ?, latest_price = ?, scanner_band = ?, scanner_label = ?,
                            score = MAX(score, ?), target_probability = MAX(target_probability, ?),
                            relative_opportunity = MAX(relative_opportunity, ?), observation_count = observation_count + 1,
                            context_json = ?
                        WHERE id = ?
                        """,
                        (
                            now,
                            now,
                            parsed["ltp"],
                            parsed["scanner_band"],
                            parsed["scanner_label"],
                            parsed["score"],
                            parsed["target_probability"],
                            parsed["relative_opportunity"],
                            context,
                            int(existing["id"]),
                        ),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO pretrade_predictions (
                            symbol, direction, setup_type, regime, scanner_band, scanner_label, state, result,
                            created_at, updated_at, last_seen_at, expires_at, initial_price, latest_price,
                            entry_trigger, stop_loss, target1, target2, score, target_probability,
                            relative_opportunity, context_json
                        ) VALUES (?, ?, ?, ?, ?, ?, 'WATCHING', 'OPEN', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            parsed["symbol"],
                            parsed["direction"],
                            parsed["setup_type"],
                            parsed["regime"],
                            parsed["scanner_band"],
                            parsed["scanner_label"],
                            now,
                            now,
                            now,
                            expires_at,
                            parsed["ltp"],
                            parsed["ltp"],
                            parsed["entry"],
                            parsed["stop"],
                            parsed["target1"],
                            parsed["target2"],
                            parsed["score"],
                            parsed["target_probability"],
                            parsed["relative_opportunity"],
                            context,
                        ),
                    )
                self._update_pretrade_predictions_for_symbol(conn, symbol=parsed["symbol"], price=parsed["ltp"], timestamp=now_dt)

    def update_pretrade_prices(self, rows: list[dict[str, Any]], *, timestamp: datetime | None = None) -> None:
        if not rows:
            return
        now_dt = timestamp or datetime.now()
        with self._lock, self._connect() as conn:
            for row in rows:
                symbol = str(row.get("symbol") or "").upper().strip()
                price = self._number(row.get("ltp") or row.get("price"))
                if symbol and price > 0:
                    self._update_pretrade_predictions_for_symbol(conn, symbol=symbol, price=price, timestamp=now_dt)

    def update_pretrade_price(self, *, symbol: str, price: float, timestamp: datetime) -> None:
        key = str(symbol or "").upper().strip()
        if not key or price <= 0:
            return
        with self._lock, self._connect() as conn:
            self._update_pretrade_predictions_for_symbol(conn, symbol=key, price=price, timestamp=timestamp)

    def pretrade_archive_summary(self, *, session_date: str | None = None) -> dict[str, Any]:
        where_clause = "WHERE substr(created_at, 1, 10) = ?" if session_date else ""
        params: tuple[Any, ...] = (session_date,) if session_date else ()
        with self._lock, self._connect() as conn:
            totals = conn.execute(
                f"""
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN state IN ('WATCHING', 'ENTERED') THEN 1 ELSE 0 END) AS active,
                    SUM(CASE WHEN state = 'CLOSED' THEN 1 ELSE 0 END) AS closed,
                    SUM(CASE WHEN entered_at IS NOT NULL THEN 1 ELSE 0 END) AS entered,
                    SUM(CASE WHEN result = 'MISSED_ENTRY' THEN 1 ELSE 0 END) AS missed,
                    SUM(CASE WHEN t1_hit = 1 THEN 1 ELSE 0 END) AS t1_hits,
                    SUM(CASE WHEN t2_hit = 1 THEN 1 ELSE 0 END) AS t2_hits,
                    SUM(CASE WHEN result = 'SL_HIT' THEN 1 ELSE 0 END) AS sl_hits,
                    SUM(CASE WHEN result IN ('TIME_EXIT', 'TIME_EXIT_T1') THEN 1 ELSE 0 END) AS time_exits
                FROM pretrade_predictions
                {where_clause}
                """,
                params,
            ).fetchone()
            by_band = conn.execute(
                f"""
                SELECT scanner_band, COUNT(*) AS total,
                       SUM(CASE WHEN entered_at IS NOT NULL THEN 1 ELSE 0 END) AS entered,
                       SUM(CASE WHEN t1_hit = 1 THEN 1 ELSE 0 END) AS t1_hits,
                       SUM(CASE WHEN t2_hit = 1 THEN 1 ELSE 0 END) AS t2_hits,
                       SUM(CASE WHEN result = 'SL_HIT' THEN 1 ELSE 0 END) AS sl_hits
                FROM pretrade_predictions
                {where_clause}
                GROUP BY scanner_band
                ORDER BY total DESC
                LIMIT 8
                """,
                params,
            ).fetchall()
        total = int(totals["total"] or 0)
        entered = int(totals["entered"] or 0)
        closed = int(totals["closed"] or 0)
        t1_hits = int(totals["t1_hits"] or 0)
        t2_hits = int(totals["t2_hits"] or 0)
        sl_hits = int(totals["sl_hits"] or 0)
        return {
            "total_predictions": total,
            "active_predictions": int(totals["active"] or 0),
            "closed_predictions": closed,
            "entered_predictions": entered,
            "missed_entries": int(totals["missed"] or 0),
            "entry_conversion_pct": int(round((entered / total) * 100)) if total else 0,
            "t1_hit_rate": int(round((t1_hits / entered) * 100)) if entered else 0,
            "t2_hit_rate": int(round((t2_hits / entered) * 100)) if entered else 0,
            "sl_hit_rate": int(round((sl_hits / entered) * 100)) if entered else 0,
            "time_exit_rate": int(round((int(totals["time_exits"] or 0) / entered) * 100)) if entered else 0,
            "by_band": [
                {
                    "scanner_band": str(row["scanner_band"] or "watchlist"),
                    "total": int(row["total"] or 0),
                    "entered": int(row["entered"] or 0),
                    "t1_hit_rate": int(round((int(row["t1_hits"] or 0) / int(row["entered"] or 1)) * 100)) if int(row["entered"] or 0) else 0,
                    "t2_hit_rate": int(round((int(row["t2_hits"] or 0) / int(row["entered"] or 1)) * 100)) if int(row["entered"] or 0) else 0,
                    "sl_hit_rate": int(round((int(row["sl_hits"] or 0) / int(row["entered"] or 1)) * 100)) if int(row["entered"] or 0) else 0,
                }
                for row in by_band
            ],
        }

    def pretrade_archive_report(self, *, session_date: str | None = None, limit: int = 80) -> dict[str, Any]:
        where_clause = "WHERE substr(created_at, 1, 10) = ?" if session_date else ""
        params: tuple[Any, ...] = (session_date,) if session_date else ()
        with self._lock, self._connect() as conn:
            by_setup = conn.execute(
                f"""
                SELECT setup_type, regime, direction, scanner_band,
                       COUNT(*) AS total,
                       SUM(CASE WHEN state IN ('WATCHING', 'ENTERED') THEN 1 ELSE 0 END) AS active,
                       SUM(CASE WHEN entered_at IS NOT NULL THEN 1 ELSE 0 END) AS entered,
                       SUM(CASE WHEN result = 'MISSED_ENTRY' THEN 1 ELSE 0 END) AS missed,
                       SUM(CASE WHEN t1_hit = 1 THEN 1 ELSE 0 END) AS t1_hits,
                       SUM(CASE WHEN t2_hit = 1 THEN 1 ELSE 0 END) AS t2_hits,
                       SUM(CASE WHEN result = 'SL_HIT' THEN 1 ELSE 0 END) AS sl_hits,
                       SUM(CASE WHEN result IN ('TIME_EXIT', 'TIME_EXIT_T1') THEN 1 ELSE 0 END) AS time_exits,
                       AVG(score) AS avg_score,
                       AVG(target_probability) AS avg_probability,
                       AVG(relative_opportunity) AS avg_opportunity,
                       AVG(CASE WHEN state = 'CLOSED' THEN mfe_points END) AS avg_mfe,
                       AVG(CASE WHEN state = 'CLOSED' THEN mae_points END) AS avg_mae
                FROM pretrade_predictions
                {where_clause}
                GROUP BY setup_type, regime, direction, scanner_band
                ORDER BY total DESC, entered DESC, t2_hits DESC, sl_hits ASC
                LIMIT 40
                """,
                params,
            ).fetchall()
            by_symbol = conn.execute(
                f"""
                SELECT symbol,
                       COUNT(*) AS total,
                       SUM(CASE WHEN state IN ('WATCHING', 'ENTERED') THEN 1 ELSE 0 END) AS active,
                       SUM(CASE WHEN entered_at IS NOT NULL THEN 1 ELSE 0 END) AS entered,
                       SUM(CASE WHEN t1_hit = 1 THEN 1 ELSE 0 END) AS t1_hits,
                       SUM(CASE WHEN t2_hit = 1 THEN 1 ELSE 0 END) AS t2_hits,
                       SUM(CASE WHEN result = 'SL_HIT' THEN 1 ELSE 0 END) AS sl_hits,
                       SUM(CASE WHEN result = 'MISSED_ENTRY' THEN 1 ELSE 0 END) AS missed,
                       AVG(score) AS avg_score
                FROM pretrade_predictions
                {where_clause}
                GROUP BY symbol
                ORDER BY total DESC, entered DESC, t2_hits DESC, sl_hits ASC, symbol ASC
                LIMIT 40
                """,
                params,
            ).fetchall()
            recent = conn.execute(
                f"""
                SELECT id, symbol, direction, setup_type, regime, scanner_band, state, result,
                       created_at, updated_at, entered_at, exited_at, initial_price, latest_price,
                       entry_trigger, stop_loss, target1, target2, score, target_probability,
                       relative_opportunity, observation_count, t1_hit, t2_hit, mfe_points, mae_points
                FROM pretrade_predictions
                {where_clause}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                params + (int(limit),),
            ).fetchall()
        return {
            "session_date": session_date or self.session_date(),
            "summary": self.pretrade_archive_summary(session_date=session_date),
            "by_setup": [self._archive_group_row(row) for row in by_setup],
            "by_symbol": [self._archive_symbol_row(row) for row in by_symbol],
            "recent": [
                {
                    "id": int(row["id"]),
                    "symbol": str(row["symbol"]),
                    "direction": str(row["direction"]),
                    "setup_type": str(row["setup_type"]),
                    "regime": str(row["regime"] or ""),
                    "scanner_band": str(row["scanner_band"] or "watchlist"),
                    "state": str(row["state"]),
                    "result": str(row["result"]),
                    "created_at": str(row["created_at"]),
                    "updated_at": str(row["updated_at"]),
                    "entered_at": row["entered_at"],
                    "exited_at": row["exited_at"],
                    "initial_price": round(float(row["initial_price"] or 0.0), 2),
                    "latest_price": round(float(row["latest_price"] or 0.0), 2),
                    "entry_trigger": round(float(row["entry_trigger"] or 0.0), 2),
                    "stop_loss": round(float(row["stop_loss"] or 0.0), 2),
                    "target1": round(float(row["target1"] or 0.0), 2),
                    "target2": round(float(row["target2"] or 0.0), 2),
                    "score": round(float(row["score"] or 0.0), 1),
                    "target_probability": round(float(row["target_probability"] or 0.0), 1),
                    "relative_opportunity": round(float(row["relative_opportunity"] or 0.0), 1),
                    "observation_count": int(row["observation_count"] or 0),
                    "t1_hit": bool(row["t1_hit"]),
                    "t2_hit": bool(row["t2_hit"]),
                    "mfe_points": round(float(row["mfe_points"] or 0.0), 2),
                    "mae_points": round(float(row["mae_points"] or 0.0), 2),
                }
                for row in recent
            ],
        }

    @staticmethod
    def _archive_group_row(row: sqlite3.Row) -> dict[str, Any]:
        total = int(row["total"] or 0)
        entered = int(row["entered"] or 0)
        t1_hits = int(row["t1_hits"] or 0)
        t2_hits = int(row["t2_hits"] or 0)
        sl_hits = int(row["sl_hits"] or 0)
        time_exits = int(row["time_exits"] or 0)
        return {
            "setup_type": str(row["setup_type"] or ""),
            "regime": str(row["regime"] or ""),
            "direction": str(row["direction"] or ""),
            "scanner_band": str(row["scanner_band"] or "watchlist"),
            "total": total,
            "active": int(row["active"] or 0),
            "entered": entered,
            "missed": int(row["missed"] or 0),
            "entry_conversion_pct": int(round((entered / total) * 100)) if total else 0,
            "t1_hit_rate": int(round((t1_hits / entered) * 100)) if entered else 0,
            "t2_hit_rate": int(round((t2_hits / entered) * 100)) if entered else 0,
            "sl_hit_rate": int(round((sl_hits / entered) * 100)) if entered else 0,
            "time_exit_rate": int(round((time_exits / entered) * 100)) if entered else 0,
            "avg_score": round(float(row["avg_score"] or 0.0), 1),
            "avg_probability": round(float(row["avg_probability"] or 0.0), 1),
            "avg_opportunity": round(float(row["avg_opportunity"] or 0.0), 1),
            "avg_mfe": round(float(row["avg_mfe"] or 0.0), 2),
            "avg_mae": round(float(row["avg_mae"] or 0.0), 2),
        }

    @staticmethod
    def _archive_symbol_row(row: sqlite3.Row) -> dict[str, Any]:
        total = int(row["total"] or 0)
        entered = int(row["entered"] or 0)
        t1_hits = int(row["t1_hits"] or 0)
        t2_hits = int(row["t2_hits"] or 0)
        sl_hits = int(row["sl_hits"] or 0)
        return {
            "symbol": str(row["symbol"] or ""),
            "total": total,
            "active": int(row["active"] or 0),
            "entered": entered,
            "missed": int(row["missed"] or 0),
            "entry_conversion_pct": int(round((entered / total) * 100)) if total else 0,
            "t1_hit_rate": int(round((t1_hits / entered) * 100)) if entered else 0,
            "t2_hit_rate": int(round((t2_hits / entered) * 100)) if entered else 0,
            "sl_hit_rate": int(round((sl_hits / entered) * 100)) if entered else 0,
            "avg_score": round(float(row["avg_score"] or 0.0), 1),
        }

    @staticmethod
    def _parse_pretrade_setup(setup: dict[str, Any]) -> dict[str, Any] | None:
        symbol = str(setup.get("symbol") or "").upper().strip()
        side = str(setup.get("side") or setup.get("direction") or setup.get("trade_direction") or "").upper()
        if side in {"LONG", "BULLISH", "BUY"}:
            direction = "BULLISH"
            entry = PaperTradeBook._number(setup.get("entry_high") or setup.get("entry_trigger") or setup.get("entry"))
        elif side in {"SHORT", "BEARISH", "SELL"}:
            direction = "BEARISH"
            entry = PaperTradeBook._number(setup.get("entry_low") or setup.get("entry_trigger") or setup.get("entry"))
        else:
            return None
        ltp = PaperTradeBook._number(setup.get("ltp") or setup.get("last_price"))
        stop = PaperTradeBook._number(setup.get("stop_loss") or setup.get("sl"))
        target1 = PaperTradeBook._number(setup.get("target1") or setup.get("t1"))
        target2 = PaperTradeBook._number(setup.get("target2") or setup.get("t2"))
        if not symbol or min(ltp, entry, stop, target1, target2) <= 0:
            return None
        return {
            "symbol": symbol,
            "direction": direction,
            "setup_type": str(setup.get("setup_type") or "UNKNOWN").upper(),
            "regime": str(setup.get("regime") or setup.get("market_bias") or "").upper(),
            "scanner_band": str(setup.get("scanner_band") or "watchlist").lower(),
            "scanner_label": str(setup.get("scanner_label") or ""),
            "ltp": ltp,
            "entry": entry,
            "stop": stop,
            "target1": target1,
            "target2": target2,
            "score": PaperTradeBook._first_number(
                setup,
                "final_selector_score",
                "selector_score",
                "final_score",
                "score",
                "confidence",
            ),
            "target_probability": PaperTradeBook._first_number(
                setup,
                "target_ahead_probability",
                "target_probability",
                "t1_probability",
                "probability",
            ),
            "relative_opportunity": PaperTradeBook._first_number(
                setup,
                "relative_opportunity_score",
                "opportunity_score",
                "relative_opportunity",
                "opportunity",
                "final_selector_score",
                "final_score",
                "score",
                "confidence",
            ),
        }

    @staticmethod
    def _number(value: Any, default: float = 0.0) -> float:
        try:
            if isinstance(value, str):
                value = value.replace("%", "").replace(",", "").strip()
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _first_number(setup: dict[str, Any], *keys: str, default: float = 0.0) -> float:
        for key in keys:
            value = PaperTradeBook._number(setup.get(key), default=default)
            if value != default:
                return value
        return default

    @staticmethod
    def _pretrade_context_json(setup: dict[str, Any], *, source: str) -> str:
        keys = [
            "symbol",
            "name",
            "side",
            "setup_type",
            "scanner_band",
            "scanner_label",
            "final_selector_score",
            "selector_score",
            "final_score",
            "score",
            "confidence",
            "target_ahead_probability",
            "target_probability",
            "relative_opportunity_score",
            "opportunity_score",
            "trade_status",
            "pre_breakout_status",
            "prediction_grade",
            "breakout_probability",
            "trap_risk",
            "structure_state",
            "compression_state",
            "pressure_state",
            "vwap_state",
            "volume_state",
            "exhaustion_state",
            "trigger_distance_pct",
            "target1_distance_pct",
            "risk_distance_pct",
            "opportunity_phase",
            "confirmation_quality",
            "missing_confirmation",
            "why_selected",
            "why_not_higher",
            "why_ranked_here",
        ]
        payload = {key: setup.get(key) for key in keys if key in setup}
        payload["source"] = source
        return json.dumps(payload, default=str, separators=(",", ":"))

    def _update_pretrade_predictions_for_symbol(self, conn: sqlite3.Connection, *, symbol: str, price: float, timestamp: datetime) -> None:
        now = timestamp.isoformat(timespec="seconds")
        rows = conn.execute(
            """
            SELECT *
            FROM pretrade_predictions
            WHERE symbol = ? AND state IN ('WATCHING', 'ENTERED')
            ORDER BY id ASC
            """,
            (symbol,),
        ).fetchall()
        for row in rows:
            self._update_pretrade_prediction_row(conn, row=row, price=price, timestamp=timestamp, now=now)

    def _update_pretrade_prediction_row(self, conn: sqlite3.Connection, *, row: sqlite3.Row, price: float, timestamp: datetime, now: str) -> None:
        direction = str(row["direction"])
        state = str(row["state"])
        entry = float(row["entry_trigger"])
        stop = float(row["stop_loss"])
        target1 = float(row["target1"])
        target2 = float(row["target2"])
        entered_at = row["entered_at"]
        expires_at = datetime.fromisoformat(str(row["expires_at"]))
        expired = timestamp >= expires_at
        entered_now = False
        if state == "WATCHING":
            entered_now = (direction == "BULLISH" and price >= entry) or (direction == "BEARISH" and price <= entry)
            if entered_now:
                state = "ENTERED"
                entered_at = now
            elif expired:
                conn.execute(
                    """
                    UPDATE pretrade_predictions
                    SET state = 'CLOSED', result = 'MISSED_ENTRY', updated_at = ?, latest_price = ?, exited_at = ?, exit_price = ?
                    WHERE id = ?
                    """,
                    (now, price, now, price, int(row["id"])),
                )
                return

        if state != "ENTERED":
            conn.execute(
                """
                UPDATE pretrade_predictions
                SET updated_at = ?, latest_price = ?
                WHERE id = ?
                """,
                (now, price, int(row["id"])),
            )
            return

        favorable = (price - entry) if direction == "BULLISH" else (entry - price)
        adverse = (entry - price) if direction == "BULLISH" else (price - entry)
        mfe_points = max(float(row["mfe_points"] or 0.0), favorable)
        mae_points = max(float(row["mae_points"] or 0.0), adverse)
        t1_hit = bool(row["t1_hit"]) or ((direction == "BULLISH" and price >= target1) or (direction == "BEARISH" and price <= target1))
        t2_hit = bool(row["t2_hit"]) or ((direction == "BULLISH" and price >= target2) or (direction == "BEARISH" and price <= target2))
        sl_hit = (direction == "BULLISH" and price <= stop) or (direction == "BEARISH" and price >= stop)
        result = "OPEN"
        closed_state = "ENTERED"
        exited_at: str | None = None
        exit_price: float | None = None
        if t2_hit:
            result = "T2_HIT"
            closed_state = "CLOSED"
            exited_at = now
            exit_price = price
        elif sl_hit:
            result = "SL_HIT"
            closed_state = "CLOSED"
            exited_at = now
            exit_price = price
        elif expired:
            result = "TIME_EXIT_T1" if t1_hit else "TIME_EXIT"
            closed_state = "CLOSED"
            exited_at = now
            exit_price = price

        conn.execute(
            """
            UPDATE pretrade_predictions
            SET state = ?, result = ?, updated_at = ?, latest_price = ?, entered_at = COALESCE(entered_at, ?),
                exited_at = COALESCE(?, exited_at), exit_price = COALESCE(?, exit_price),
                t1_hit = ?, t2_hit = ?, mfe_points = ?, mae_points = ?
            WHERE id = ?
            """,
            (
                closed_state,
                result,
                now,
                price,
                entered_at,
                exited_at,
                exit_price,
                1 if t1_hit else 0,
                1 if t2_hit else 0,
                round(max(mfe_points, 0.0), 4),
                round(max(mae_points, 0.0), 4),
                int(row["id"]),
            ),
        )

    def register_signal(self, signal: TradeSignal, *, direction: str) -> None:
        if not self.config.paper_trading_enabled or direction not in {"BULLISH", "BEARISH"}:
            return
        if signal.state not in {"READY", "EXECUTE"}:
            self.remove_candidate(signal.stock)
            return
        with self._lock, self._connect() as conn:
            open_trade = conn.execute(
                """
                SELECT id FROM paper_trades
                WHERE symbol = ? AND state = 'OPEN'
                ORDER BY id DESC LIMIT 1
                """,
                (signal.stock.upper(),),
            ).fetchone()
            if open_trade is not None:
                return
            now = datetime.now().isoformat(timespec="seconds")
            now_dt = datetime.fromisoformat(now)
            expires_at = (
                datetime.now() + timedelta(minutes=self.config.paper_trade_pending_expiry_min)
            ).isoformat(timespec="seconds")
            existing_candidate = conn.execute(
                """
                SELECT id, signal, setup_type, regime, direction, score, confidence, state,
                       created_at, updated_at, expires_at, entry_trigger, stop_loss, target1, target2
                FROM paper_candidates
                WHERE symbol = ?
                ORDER BY id DESC LIMIT 1
                """,
                (signal.stock.upper(),),
            ).fetchone()
            if existing_candidate is not None:
                created_at = datetime.fromisoformat(str(existing_candidate["created_at"]))
                frozen = (now_dt - created_at).total_seconds() < max(self.config.paper_trade_candidate_freeze_sec, 0)
                same_setup = (
                    str(existing_candidate["setup_type"]) == signal.setup_type
                    and str(existing_candidate["direction"]) == direction
                )
                if same_setup or frozen:
                    conn.execute(
                        """
                        UPDATE paper_candidates
                        SET signal = ?, regime = ?, score = ?, confidence = ?, state = ?, updated_at = ?, expires_at = ?
                        WHERE id = ?
                        """,
                        (
                            signal.signal if same_setup else str(existing_candidate["signal"]),
                            signal.regime if same_setup else str(existing_candidate["regime"]),
                            max(int(existing_candidate["score"] or 0), int(signal.score)),
                            signal.confidence,
                            signal.state,
                            now,
                            expires_at,
                            int(existing_candidate["id"]),
                        ),
                    )
                    return
                conn.execute("DELETE FROM paper_candidates WHERE id = ?", (int(existing_candidate["id"]),))
            conn.execute(
                """
                INSERT INTO paper_candidates (
                    symbol, signal, setup_type, regime, direction, score, confidence, state,
                    created_at, updated_at, expires_at, entry_trigger, stop_loss, target1, target2
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    signal = excluded.signal,
                    setup_type = excluded.setup_type,
                    regime = excluded.regime,
                    direction = excluded.direction,
                    score = excluded.score,
                    confidence = excluded.confidence,
                    state = excluded.state,
                    updated_at = excluded.updated_at,
                    expires_at = excluded.expires_at,
                    entry_trigger = excluded.entry_trigger,
                    stop_loss = excluded.stop_loss,
                    target1 = excluded.target1,
                    target2 = excluded.target2
                """,
                (
                    signal.stock.upper(),
                    signal.signal,
                    signal.setup_type,
                    signal.regime,
                    direction,
                    signal.score,
                    signal.confidence,
                    signal.state,
                    now,
                    now,
                    expires_at,
                    signal.entry,
                    signal.sl,
                    signal.t1,
                    signal.t2,
                ),
            )

    def remove_candidate(self, symbol: str) -> None:
        key = str(symbol or "").upper().strip()
        if not key:
            return
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM paper_candidates WHERE symbol = ?", (key,))

    def update_symbol(self, *, symbol: str, price: float, timestamp: datetime) -> None:
        if not self.config.paper_trading_enabled or price <= 0:
            return
        for candidate in self._load_candidates(symbol.upper()):
            self._update_candidate(candidate, price=price, timestamp=timestamp)
        for trade in self._load_open_trades(symbol.upper()):
            self._update_trade(trade, price=price, timestamp=timestamp)

    def force_market_close_if_needed(self, timestamp: datetime | None = None) -> None:
        if not self.config.paper_trading_enabled:
            return
        current = timestamp or datetime.now()
        now_ist = current.astimezone(ZoneInfo("Asia/Kolkata")) if current.tzinfo else current.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
        if now_ist.time() < dt_time(15, 20):
            return
        exit_stamp = now_ist.isoformat(timespec="seconds")
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, trigger_price, entry_trigger
                FROM paper_trades
                WHERE state = 'OPEN'
                """
            ).fetchall()
            for row in rows:
                entry = float(row["trigger_price"]) if row["trigger_price"] is not None else float(row["entry_trigger"])
                cost_points = self._execution_cost(entry)
                conn.execute(
                    """
                    UPDATE paper_trades
                    SET state = 'CLOSED', result = 'MARKET_CLOSE_EXIT', updated_at = ?, exited_at = ?,
                        exit_price = COALESCE(exit_price, ?),
                        cost_points = COALESCE(cost_points, 0) + ?
                    WHERE id = ?
                    """,
                    (exit_stamp, exit_stamp, entry, round(cost_points, 4), int(row["id"])),
                )
            conn.execute("DELETE FROM paper_candidates")

    def _load_candidates(self, symbol: str) -> list[PendingTrigger]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM paper_candidates
                WHERE symbol = ?
                ORDER BY id ASC
                """,
                (symbol,),
            ).fetchall()
        return [
            PendingTrigger(
                id=int(row["id"]),
                symbol=str(row["symbol"]),
                direction=str(row["direction"]),
                state=str(row["state"] or "READY"),
                created_at=datetime.fromisoformat(str(row["created_at"])),
                expires_at=datetime.fromisoformat(str(row["expires_at"])),
                entry_trigger=float(row["entry_trigger"]),
                stop_loss=float(row["stop_loss"]),
                target1=float(row["target1"]),
                target2=float(row["target2"]),
                signal=str(row["signal"]),
                setup_type=str(row["setup_type"]),
                regime=str(row["regime"]),
                score=int(row["score"] or 0),
                confidence=str(row["confidence"] or ""),
            )
            for row in rows
        ]

    def _load_open_trades(self, symbol: str) -> list[ActivePaperTrade]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, symbol, direction, state, created_at, entry_trigger, stop_loss, target1, target2,
                       t1_hit, t2_hit, mae_points, mfe_points, trigger_price
                FROM paper_trades
                WHERE symbol = ? AND state = 'OPEN'
                ORDER BY id ASC
                """,
                (symbol,),
            ).fetchall()
        return [
            ActivePaperTrade(
                id=int(row["id"]),
                symbol=str(row["symbol"]),
                direction=str(row["direction"]),
                state=str(row["state"]),
                created_at=datetime.fromisoformat(str(row["created_at"])),
                entry_trigger=float(row["entry_trigger"]),
                stop_loss=float(row["stop_loss"]),
                target1=float(row["target1"]),
                target2=float(row["target2"]),
                t1_hit=bool(row["t1_hit"]),
                t2_hit=bool(row["t2_hit"]),
                mae_points=float(row["mae_points"]),
                mfe_points=float(row["mfe_points"]),
                trigger_price=float(row["trigger_price"]) if row["trigger_price"] is not None else None,
            )
            for row in rows
        ]

    def _update_candidate(self, candidate: PendingTrigger, *, price: float, timestamp: datetime) -> None:
        now = timestamp.isoformat(timespec="seconds")
        expired = timestamp >= candidate.expires_at
        confirm_buffer = self._entry_confirmation_buffer(candidate)
        max_chase = max(self._max_chase_buffer(candidate), confirm_buffer * 1.15)
        if candidate.direction == "BULLISH":
            entered = (candidate.entry_trigger + confirm_buffer) <= price <= (candidate.entry_trigger + max_chase)
        else:
            entered = (candidate.entry_trigger - confirm_buffer) >= price >= (candidate.entry_trigger - max_chase)
        with self._lock, self._connect() as conn:
            if entered:
                trigger_price = self._apply_entry_slippage(direction=candidate.direction, entry_price=price)
                cost_points = self._execution_cost(trigger_price)
                conn.execute(
                    """
                    INSERT INTO paper_trades (
                        symbol, signal, setup_type, regime, direction, state, result, score, confidence,
                        created_at, updated_at, entry_trigger, stop_loss, target1, target2, trigger_price,
                        entered_at, gross_pnl_points, cost_points, pnl_points, mae_points, mfe_points, t1_hit, t2_hit
                    ) VALUES (?, ?, ?, ?, ?, 'OPEN', 'OPEN', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 0, 0, 0, 0, 0)
                    """,
                    (
                        candidate.symbol,
                        candidate.signal,
                        candidate.setup_type,
                        candidate.regime,
                        candidate.direction,
                        candidate.score,
                        candidate.confidence,
                        now,
                        now,
                        candidate.entry_trigger,
                        candidate.stop_loss,
                        candidate.target1,
                        candidate.target2,
                        trigger_price,
                        now,
                        round(cost_points, 4),
                    ),
                )
                conn.execute("DELETE FROM paper_candidates WHERE id = ?", (candidate.id,))
            elif expired:
                conn.execute(
                    """
                    INSERT INTO paper_trades (
                        symbol, signal, setup_type, regime, direction, state, result, score, confidence,
                        created_at, updated_at, entry_trigger, stop_loss, target1, target2,
                        gross_pnl_points, cost_points, pnl_points, mae_points, mfe_points, t1_hit, t2_hit
                    ) VALUES (?, ?, ?, ?, ?, 'CLOSED', 'EXPIRED', ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, 0, 0)
                    """,
                    (
                        candidate.symbol,
                        candidate.signal,
                        candidate.setup_type,
                        candidate.regime,
                        candidate.direction,
                        candidate.score,
                        candidate.confidence,
                        candidate.created_at.isoformat(timespec="seconds"),
                        now,
                        candidate.entry_trigger,
                        candidate.stop_loss,
                        candidate.target1,
                        candidate.target2,
                    ),
                )
                conn.execute("DELETE FROM paper_candidates WHERE id = ?", (candidate.id,))
            else:
                conn.execute("UPDATE paper_candidates SET updated_at = ? WHERE id = ?", (now, candidate.id))

    def candidate_status(self, *, direction: str, entry_trigger: float, stop_loss: float, target1: float, live_price: float | None, regime: str = "") -> dict[str, Any]:
        if live_price is None or live_price <= 0 or entry_trigger <= 0:
            return {
                "status": "Awaiting price",
                "distance_points": None,
                "distance_pct": None,
            }
        risk = max(abs(entry_trigger - stop_loss), 0.01)
        reward = max(abs(target1 - entry_trigger), risk)
        confirm_buffer = max(reward * self.config.paper_trade_entry_confirm_ratio, risk * 0.12, entry_trigger * 0.0008, 0.08)
        max_chase = max(reward * self.config.paper_trade_max_chase_ratio, risk * 0.45, entry_trigger * 0.0018, 0.15)
        if str(regime or "").upper() == "CHOPPY":
            confirm_buffer *= float(self.config.paper_trade_choppy_confirm_multiplier)
            max_chase *= float(self.config.paper_trade_choppy_chase_multiplier)
        max_chase = max(max_chase, confirm_buffer * 1.15)
        if direction == "BULLISH":
            distance = entry_trigger - live_price
            if live_price >= entry_trigger + max_chase:
                status = "Extended beyond entry"
            elif live_price >= entry_trigger + confirm_buffer:
                status = "Entry confirmed"
            elif live_price >= entry_trigger:
                status = "At entry"
            elif live_price <= stop_loss + (risk * 0.2):
                status = "Near invalidation"
            else:
                status = "Awaiting breakout"
        else:
            distance = live_price - entry_trigger
            if live_price <= entry_trigger - max_chase:
                status = "Extended beyond entry"
            elif live_price <= entry_trigger - confirm_buffer:
                status = "Entry confirmed"
            elif live_price <= entry_trigger:
                status = "At entry"
            elif live_price >= stop_loss - (risk * 0.2):
                status = "Near invalidation"
            else:
                status = "Awaiting breakdown"
        distance_pct = (distance / entry_trigger) * 100 if entry_trigger else None
        return {
            "status": status,
            "distance_points": round(distance, 2),
            "distance_pct": round(distance_pct, 2) if distance_pct is not None else None,
        }

    def _update_trade(self, trade: ActivePaperTrade, *, price: float, timestamp: datetime) -> None:
        now = timestamp.isoformat(timespec="seconds")
        entry = trade.trigger_price if trade.trigger_price is not None else trade.entry_trigger
        favorable = (price - entry) if trade.direction == "BULLISH" else (entry - price)
        adverse = (entry - price) if trade.direction == "BULLISH" else (price - entry)
        mfe_points = max(trade.mfe_points, favorable)
        mae_points = max(trade.mae_points, adverse)
        t1_hit = trade.t1_hit or ((trade.direction == "BULLISH" and price >= trade.target1) or (trade.direction == "BEARISH" and price <= trade.target1))
        t2_hit = trade.t2_hit or ((trade.direction == "BULLISH" and price >= trade.target2) or (trade.direction == "BEARISH" and price <= trade.target2))
        timed_out = timestamp >= trade.created_at + timedelta(minutes=self.config.paper_trade_max_hold_min)
        stop_hit = (trade.direction == "BULLISH" and price <= trade.stop_loss) or (trade.direction == "BEARISH" and price >= trade.stop_loss)
        hold_sec = max((timestamp - trade.created_at).total_seconds(), 0.0)
        risk = max(abs(entry - trade.stop_loss), 0.01)
        early_invalid = (
            self.config.paper_trade_early_exit_enabled
            and not trade.t1_hit
            and hold_sec >= float(self.config.paper_trade_early_exit_min_hold_sec)
            and max(mfe_points, 0.0) <= risk * float(self.config.paper_trade_early_exit_mfe_r)
            and adverse >= risk * float(self.config.paper_trade_early_exit_adverse_r)
        )

        state = "OPEN"
        result = "OPEN"
        exit_price: float | None = None
        exited_at: str | None = None
        sl_category: str | None = None
        if t2_hit:
            state = "CLOSED"
            result = "T2_HIT"
            exit_price = self._apply_exit_slippage(direction=trade.direction, exit_price=price)
            exited_at = now
        elif early_invalid:
            state = "CLOSED"
            result = "EARLY_INVALIDATION"
            exit_price = self._apply_exit_slippage(direction=trade.direction, exit_price=price)
            exited_at = now
        elif stop_hit:
            state = "CLOSED"
            result = "SL_HIT"
            sl_category = self._classify_sl_hit(
                trade=trade,
                entry=entry,
                timestamp=timestamp,
                mfe_points=max(mfe_points, 0.0),
            )
            exit_price = self._apply_exit_slippage(direction=trade.direction, exit_price=price)
            exited_at = now
        elif timed_out:
            state = "CLOSED"
            result = "TIME_EXIT_T1" if t1_hit else "TIME_EXIT"
            exit_price = self._apply_exit_slippage(direction=trade.direction, exit_price=price)
            exited_at = now

        realized_price = exit_price if exit_price is not None else price
        gross_pnl_points = (realized_price - entry) if trade.direction == "BULLISH" else (entry - realized_price)
        incremental_cost = self._execution_cost(exit_price) if exit_price is not None else 0.0
        pnl_points = gross_pnl_points - incremental_cost
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE paper_trades
                SET state = ?, result = ?, updated_at = ?, exit_price = COALESCE(?, exit_price), exited_at = COALESCE(?, exited_at),
                    gross_pnl_points = ?, cost_points = COALESCE(cost_points, 0) + ?, pnl_points = ?,
                    mae_points = ?, mfe_points = ?, sl_category = COALESCE(?, sl_category), t1_hit = ?, t2_hit = ?
                WHERE id = ?
                """,
                (
                    state,
                    result,
                    now,
                    exit_price,
                    exited_at,
                    round(gross_pnl_points, 2),
                    round(incremental_cost, 4),
                    round(pnl_points, 2),
                    round(max(mae_points, 0.0), 2),
                    round(max(mfe_points, 0.0), 2),
                    sl_category,
                    1 if t1_hit else 0,
                    1 if t2_hit else 0,
                    trade.id,
                ),
            )

    def recent_trades(self, limit: int = 100, session_date: str | None = None) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            if session_date:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM paper_trades
                    WHERE substr(created_at, 1, 10) = ? AND entered_at IS NOT NULL
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (session_date, int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM paper_trades
                    WHERE entered_at IS NOT NULL
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (int(limit),),
                ).fetchall()
        return [dict(row) for row in rows]

    def pending_triggers(self, limit: int = 40, session_date: str | None = None) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            if session_date:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM paper_candidates
                    WHERE substr(created_at, 1, 10) = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (session_date, int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM paper_candidates
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (int(limit),),
                ).fetchall()
        return [dict(row) for row in rows]

    def setup_risk_guard(
        self,
        *,
        setup_type: str,
        regime: str,
        direction: str,
        session_date: str | None = None,
    ) -> dict[str, Any]:
        if not self.config.adaptive_setup_guard_enabled:
            return {"blocked": False, "reason": ""}
        params: tuple[Any, ...] = (
            str(setup_type or ""),
            str(regime or ""),
            str(direction or ""),
        )
        date_filter = ""
        if session_date:
            date_filter = "AND substr(created_at, 1, 10) = ?"
            params = params + (session_date,)
        with self._lock, self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT
                    SUM(CASE WHEN entered_at IS NOT NULL THEN 1 ELSE 0 END) AS entries,
                    SUM(CASE WHEN result = 'SL_HIT' THEN 1 ELSE 0 END) AS sl_hits,
                    SUM(CASE WHEN result = 'SL_HIT' AND COALESCE(sl_category, '') = 'clean_invalidation' THEN 1 ELSE 0 END) AS clean_invalidations,
                    SUM(CASE WHEN t1_hit = 1 THEN 1 ELSE 0 END) AS t1_hits,
                    SUM(CASE WHEN t2_hit = 1 THEN 1 ELSE 0 END) AS t2_hits,
                    AVG(CASE WHEN entered_at IS NOT NULL AND state = 'CLOSED' THEN pnl_points END) AS avg_pnl_points
                FROM paper_trades
                WHERE setup_type = ? AND regime = ? AND direction = ?
                {date_filter}
                """,
                params,
            ).fetchone()
        entries = int(row["entries"] or 0) if row else 0
        sl_hits = int(row["sl_hits"] or 0) if row else 0
        clean_invalidations = int(row["clean_invalidations"] or 0) if row else 0
        t1_hits = int(row["t1_hits"] or 0) if row else 0
        t2_hits = int(row["t2_hits"] or 0) if row else 0
        avg_pnl_points = float(row["avg_pnl_points"] or 0.0) if row else 0.0
        min_entries = max(int(self.config.adaptive_setup_guard_min_entries), 1)
        if entries < min_entries:
            return {"blocked": False, "reason": "", "entries": entries, "sl_rate": 0, "clean_rate": 0, "expectancy_points": 0.0}
        sl_rate = sl_hits / max(entries, 1)
        clean_rate = clean_invalidations / max(entries, 1)
        no_follow_through = t1_hits == 0 and t2_hits == 0
        clean_failure_dominates = clean_invalidations > 0 and clean_rate >= float(self.config.adaptive_setup_guard_clean_rate)
        sl_dominates_without_follow_through = no_follow_through and sl_rate >= float(self.config.adaptive_setup_guard_sl_rate)
        negative_expectancy = (
            entries >= max(int(self.config.adaptive_setup_guard_min_expectancy_entries), 1)
            and avg_pnl_points <= float(self.config.adaptive_setup_guard_negative_expectancy_points)
        )
        blocked = clean_failure_dominates or sl_dominates_without_follow_through or negative_expectancy
        reason = ""
        if blocked:
            reason = (
                f"Adaptive guard blocked {setup_type}/{regime}/{direction}: "
                f"SL {sl_hits}/{entries}, clean invalidation {clean_invalidations}/{entries}, "
                f"T1 {t1_hits}, T2 {t2_hits}, expectancy {avg_pnl_points:.2f}."
            )
        return {
            "blocked": blocked,
            "reason": reason,
            "entries": entries,
            "sl_hits": sl_hits,
            "clean_invalidations": clean_invalidations,
            "t1_hits": t1_hits,
            "t2_hits": t2_hits,
            "sl_rate": round(sl_rate, 4),
            "clean_rate": round(clean_rate, 4),
            "expectancy_points": round(avg_pnl_points, 2),
        }

    def analytics(self, session_date: str | None = None) -> dict[str, Any]:
        where_clause = "WHERE entered_at IS NOT NULL AND substr(created_at, 1, 10) = ?" if session_date else "WHERE entered_at IS NOT NULL"
        trade_scope_where = "WHERE substr(created_at, 1, 10) = ?" if session_date else ""
        candidate_where_clause = "WHERE substr(created_at, 1, 10) = ?" if session_date else ""
        params: tuple[Any, ...] = (session_date,) if session_date else ()
        with self._lock, self._connect() as conn:
            trade_scope = conn.execute(
                f"""
                SELECT
                    COUNT(*) AS total_signals,
                    SUM(CASE WHEN entered_at IS NOT NULL THEN 1 ELSE 0 END) AS entered_signals,
                    SUM(CASE WHEN entered_at IS NULL THEN 1 ELSE 0 END) AS non_entered_signals,
                    SUM(CASE WHEN entered_at IS NULL AND state = 'CLOSED' AND result = 'EXPIRED' THEN 1 ELSE 0 END) AS expired_signals
                FROM paper_trades
                {trade_scope_where}
                """,
                params,
            ).fetchone()
            totals = conn.execute(
                f"""
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN state = 'OPEN' THEN 1 ELSE 0 END) AS open_count,
                    SUM(CASE WHEN state = 'CLOSED' THEN 1 ELSE 0 END) AS closed_count,
                    SUM(CASE WHEN result IN ('T2_HIT', 'TIME_EXIT_T1') THEN 1 ELSE 0 END) AS win_like_count,
                    SUM(CASE WHEN result = 'SL_HIT' THEN 1 ELSE 0 END) AS sl_count,
                    SUM(CASE WHEN result = 'TIME_EXIT' THEN 1 ELSE 0 END) AS time_exit_count,
                    SUM(CASE WHEN result = 'TIME_EXIT_T1' THEN 1 ELSE 0 END) AS time_exit_t1_count,
                    SUM(CASE WHEN result = 'EARLY_INVALIDATION' THEN 1 ELSE 0 END) AS early_invalid_count,
                    SUM(CASE WHEN result = 'MARKET_CLOSE_EXIT' THEN 1 ELSE 0 END) AS market_close_count,
                    SUM(CASE WHEN t1_hit = 1 THEN 1 ELSE 0 END) AS t1_hits,
                    SUM(CASE WHEN t2_hit = 1 THEN 1 ELSE 0 END) AS t2_hits,
                    SUM(CASE WHEN t1_hit = 1 AND t2_hit = 0 THEN 1 ELSE 0 END) AS t1_only_hits,
                    AVG(CASE WHEN state = 'CLOSED' THEN cost_points END) AS avg_cost,
                    AVG(CASE WHEN state = 'CLOSED' THEN pnl_points END) AS avg_pnl,
                    AVG(CASE WHEN state = 'CLOSED' THEN mfe_points END) AS avg_mfe,
                    AVG(CASE WHEN state = 'CLOSED' THEN mae_points END) AS avg_mae,
                    AVG((julianday(entered_at) - julianday(created_at)) * 86400.0) AS avg_time_to_trigger_sec,
                    AVG((julianday(COALESCE(exited_at, updated_at)) - julianday(entered_at)) * 86400.0) AS avg_hold_sec
                FROM paper_trades
                {where_clause}
                """,
                params,
            ).fetchone()
            candidate_totals = conn.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM paper_candidates
                {candidate_where_clause}
                """,
                params,
            ).fetchone()
            setups = conn.execute(
                f"""
                SELECT
                       setup_type,
                       regime,
                       direction,
                       COUNT(*) AS trades,
                       SUM(CASE WHEN entered_at IS NOT NULL THEN 1 ELSE 0 END) AS entries,
                       SUM(CASE WHEN state = 'OPEN' THEN 1 ELSE 0 END) AS open_trades,
                       SUM(CASE WHEN entered_at IS NULL AND state = 'CLOSED' AND result = 'EXPIRED' THEN 1 ELSE 0 END) AS expired,
                       SUM(CASE WHEN result = 'SL_HIT' THEN 1 ELSE 0 END) AS sl_hits,
                       SUM(CASE WHEN result = 'TIME_EXIT' THEN 1 ELSE 0 END) AS time_exits,
                       SUM(CASE WHEN result = 'TIME_EXIT_T1' THEN 1 ELSE 0 END) AS time_exit_after_t1,
                       SUM(CASE WHEN result = 'EARLY_INVALIDATION' THEN 1 ELSE 0 END) AS early_invalidations,
                       SUM(CASE WHEN result = 'MARKET_CLOSE_EXIT' THEN 1 ELSE 0 END) AS market_close_exits,
                       SUM(CASE WHEN t1_hit = 1 THEN 1 ELSE 0 END) AS t1_hits,
                       SUM(CASE WHEN t2_hit = 1 THEN 1 ELSE 0 END) AS t2_hits,
                       AVG(CASE WHEN entered_at IS NOT NULL AND state = 'CLOSED' THEN pnl_points END) AS avg_pnl_points,
                       AVG(CASE WHEN entered_at IS NOT NULL AND state = 'CLOSED' THEN mfe_points END) AS avg_mfe_points,
                       AVG(CASE WHEN entered_at IS NOT NULL AND state = 'CLOSED' THEN mae_points END) AS avg_mae_points
                FROM paper_trades
                {trade_scope_where}
                GROUP BY setup_type, regime, direction
                ORDER BY trades DESC, entries DESC, setup_type ASC, regime ASC, direction ASC
                LIMIT 12
                """,
                params,
            ).fetchall()
            sl_buckets = conn.execute(
                f"""
                SELECT COALESCE(sl_category, 'uncategorized') AS bucket, COUNT(*) AS hits
                FROM paper_trades
                {where_clause} AND result = 'SL_HIT'
                GROUP BY COALESCE(sl_category, 'uncategorized')
                ORDER BY hits DESC
                LIMIT 6
                """,
                params,
            ).fetchall()
            sl_context_rows = conn.execute(
                f"""
                SELECT
                    COALESCE(sl_category, 'uncategorized') AS bucket,
                    setup_type,
                    regime,
                    direction,
                    COUNT(*) AS hits
                FROM paper_trades
                {where_clause} AND result = 'SL_HIT'
                GROUP BY COALESCE(sl_category, 'uncategorized'), setup_type, regime, direction
                ORDER BY bucket ASC, hits DESC, setup_type ASC, regime ASC, direction ASC
                """,
                params,
            ).fetchall()
            history_total = conn.execute("SELECT COUNT(*) AS total FROM paper_trades WHERE entered_at IS NOT NULL").fetchone()
        total = int(totals["total"] or 0)
        closed = int(totals["closed_count"] or 0)
        t1_hits = int(totals["t1_hits"] or 0)
        t2_hits = int(totals["t2_hits"] or 0)
        stored_signals = int(trade_scope["total_signals"] or 0)
        entered_signals = int(trade_scope["entered_signals"] or 0)
        expired_signals = int(trade_scope["expired_signals"] or 0)
        pending_count = int(candidate_totals["total"] or 0)
        signal_count = stored_signals + pending_count
        active_signals = int(totals["open_count"] or 0) + pending_count
        sl_context_map: dict[str, list[dict[str, Any]]] = {}
        for row in sl_context_rows:
            bucket = str(row["bucket"])
            sl_context_map.setdefault(bucket, []).append(
                {
                    "setup_type": str(row["setup_type"] or ""),
                    "regime": str(row["regime"] or ""),
                    "direction": str(row["direction"] or ""),
                    "trigger_side": "BREAKOUT" if str(row["direction"] or "").upper() == "BULLISH" else "BREAKDOWN" if str(row["direction"] or "").upper() == "BEARISH" else "TRIGGER",
                    "hits": int(row["hits"] or 0),
                }
            )
        setup_breakdown = [
            {
                "setup_type": str(row["setup_type"]),
                "regime": str(row["regime"] or ""),
                "direction": str(row["direction"] or ""),
                "trigger_side": "BREAKOUT" if str(row["direction"] or "").upper() == "BULLISH" else "BREAKDOWN" if str(row["direction"] or "").upper() == "BEARISH" else "TRIGGER",
                "trades": int(row["trades"] or 0),
                "entries": int(row["entries"] or 0),
                "open_trades": int(row["open_trades"] or 0),
                "expired": int(row["expired"] or 0),
                "sl_hits": int(row["sl_hits"] or 0),
                "time_exits": int(row["time_exits"] or 0),
                "time_exit_after_t1": int(row["time_exit_after_t1"] or 0),
                "early_invalidations": int(row["early_invalidations"] or 0),
                "market_close_exits": int(row["market_close_exits"] or 0),
                "t1_hits": int(row["t1_hits"] or 0),
                "t2_hits": int(row["t2_hits"] or 0),
                "avg_pnl_points": round(float(row["avg_pnl_points"] or 0.0), 2),
                "avg_mfe_points": round(float(row["avg_mfe_points"] or 0.0), 2),
                "avg_mae_points": round(float(row["avg_mae_points"] or 0.0), 2),
                "expectancy_points": round(float(row["avg_pnl_points"] or 0.0), 2),
                "sl_hit_rate": int(round((int(row["sl_hits"] or 0) / int(row["entries"] or 1)) * 100)) if int(row["entries"] or 0) else 0,
                "time_exit_rate": int(round((((int(row["time_exits"] or 0)) + int(row["market_close_exits"] or 0) + int(row["early_invalidations"] or 0)) / int(row["entries"] or 1)) * 100)) if int(row["entries"] or 0) else 0,
                "t1_hit_rate": int(round((int(row["t1_hits"] or 0) / int(row["entries"] or 1)) * 100)) if int(row["entries"] or 0) else 0,
                "t2_hit_rate": int(round((int(row["t2_hits"] or 0) / int(row["entries"] or 1)) * 100)) if int(row["entries"] or 0) else 0,
            }
            for row in setups
        ]
        setup_learning_notes = self._setup_learning_notes(setup_breakdown)
        pretrade_archive = self.pretrade_archive_summary(session_date=session_date)
        return {
            "session_date": session_date or self.session_date(),
            "total_trades": total,
            "history_total_trades": int(history_total["total"] or 0),
            "open_trades": int(totals["open_count"] or 0),
            "closed_trades": closed,
            "pending_triggers": pending_count,
            "expired_trades": expired_signals,
            "sl_hits": int(totals["sl_count"] or 0),
            "t1_hit_rate": int(round((t1_hits / total) * 100)) if total else 0,
            "t2_hit_rate": int(round((t2_hits / total) * 100)) if total else 0,
            "win_like_rate": int(round((int(totals["win_like_count"] or 0) / closed) * 100)) if closed else 0,
            "avg_cost_points": round(float(totals["avg_cost"] or 0.0), 2),
            "avg_pnl_points": round(float(totals["avg_pnl"] or 0.0), 2),
            "avg_mfe_points": round(float(totals["avg_mfe"] or 0.0), 2),
            "avg_mae_points": round(float(totals["avg_mae"] or 0.0), 2),
            "avg_time_to_trigger_sec": round(float(totals["avg_time_to_trigger_sec"] or 0.0), 1),
            "avg_hold_sec": round(float(totals["avg_hold_sec"] or 0.0), 1),
            "funnel": {
                "signals": signal_count,
                "entered": entered_signals,
                "pending": pending_count,
                "expired": expired_signals,
                "entry_conversion_pct": int(round((entered_signals / signal_count) * 100)) if signal_count else 0,
                "active_pct": int(round((active_signals / signal_count) * 100)) if signal_count else 0,
            },
            "outcomes": {
                "sl_hit_pct": int(round((int(totals["sl_count"] or 0) / total) * 100)) if total else 0,
                "t1_hit_pct": int(round((t1_hits / total) * 100)) if total else 0,
                "t2_hit_pct": int(round((t2_hits / total) * 100)) if total else 0,
                "time_exit_pct": int(round((int(totals["time_exit_count"] or 0) / total) * 100)) if total else 0,
                "time_exit_t1_pct": int(round((int(totals["time_exit_t1_count"] or 0) / total) * 100)) if total else 0,
                "early_invalidation_pct": int(round((int(totals["early_invalid_count"] or 0) / total) * 100)) if total else 0,
                "market_close_exit_pct": int(round((int(totals["market_close_count"] or 0) / total) * 100)) if total else 0,
            },
            "progression": {
                "entered_to_t1_pct": int(round((t1_hits / entered_signals) * 100)) if entered_signals else 0,
                "entered_to_t2_pct": int(round((t2_hits / entered_signals) * 100)) if entered_signals else 0,
                "entered_to_sl_pct": int(round((int(totals["sl_count"] or 0) / entered_signals) * 100)) if entered_signals else 0,
                "entered_to_time_exit_pct": int(round((((int(totals["time_exit_count"] or 0)) + int(totals["time_exit_t1_count"] or 0)) / entered_signals) * 100)) if entered_signals else 0,
                "t1_to_t2_pct": int(round((t2_hits / t1_hits) * 100)) if t1_hits else 0,
                "t1_only_pct": int(round((int(totals["t1_only_hits"] or 0) / entered_signals) * 100)) if entered_signals else 0,
            },
            "execution": {
                "avg_cost_points": round(float(totals["avg_cost"] or 0.0), 2),
                "avg_pnl_points": round(float(totals["avg_pnl"] or 0.0), 2),
                "avg_mfe_points": round(float(totals["avg_mfe"] or 0.0), 2),
                "avg_mae_points": round(float(totals["avg_mae"] or 0.0), 2),
                "avg_time_to_trigger_sec": round(float(totals["avg_time_to_trigger_sec"] or 0.0), 1),
                "avg_hold_sec": round(float(totals["avg_hold_sec"] or 0.0), 1),
            },
            "setup_breakdown": setup_breakdown,
            "setup_learning_notes": setup_learning_notes,
            "pretrade_archive": pretrade_archive,
            "sl_breakdown": [
                {
                    "bucket": str(row["bucket"]),
                    "hits": int(row["hits"] or 0),
                    "pct": int(round((int(row["hits"] or 0) / max(int(totals["sl_count"] or 0), 1)) * 100)) if int(totals["sl_count"] or 0) else 0,
                    "contexts": sl_context_map.get(str(row["bucket"]), [])[:4],
                }
                for row in sl_buckets
            ],
        }

    @staticmethod
    def _setup_learning_notes(setups: list[dict[str, Any]]) -> list[dict[str, Any]]:
        notes: list[dict[str, Any]] = []
        for row in setups:
            entries = int(row.get("entries", 0) or 0)
            trades = int(row.get("trades", 0) or 0)
            if entries <= 0 and trades <= 0:
                continue
            setup = str(row.get("setup_type") or "UNKNOWN")
            regime = str(row.get("regime") or "")
            direction = str(row.get("direction") or "")
            label = f"{setup}/{regime}/{direction}".strip("/")
            sl_rate = int(row.get("sl_hit_rate", 0) or 0)
            t1_rate = int(row.get("t1_hit_rate", 0) or 0)
            expired = int(row.get("expired", 0) or 0)
            expectancy = float(row.get("expectancy_points", 0.0) or 0.0)
            if sl_rate >= 60:
                notes.append(
                    {
                        "setup": label,
                        "severity": "high",
                        "issue": "SL rate is high",
                        "note": f"{label}: SL hit rate {sl_rate}%. Require cleaner confirmation, lower trap risk, and tighter invalidation before promotion.",
                    }
                )
            elif t1_rate <= 25 and entries >= 2:
                notes.append(
                    {
                        "setup": label,
                        "severity": "medium",
                        "issue": "Weak T1 follow-through",
                        "note": f"{label}: T1 hit rate {t1_rate}%. Promote only when demand/supply and volume expansion are above threshold.",
                    }
                )
            if expired >= max(2, trades // 2) and trades >= 2:
                notes.append(
                    {
                        "setup": label,
                        "severity": "medium",
                        "issue": "Signals expire before entry",
                        "note": f"{label}: {expired} expired signals. Bring trigger closer or avoid far-from-trigger watchlist names.",
                    }
                )
            if expectancy < 0 and entries >= 2:
                notes.append(
                    {
                        "setup": label,
                        "severity": "high",
                        "issue": "Negative expectancy",
                        "note": f"{label}: expectancy {expectancy:.2f}. Reduce score until paper results improve.",
                    }
                )
        return notes[:10]

    def reset(self, *, session_date: str | None = None) -> dict[str, int | str]:
        with self._lock, self._connect() as conn:
            if session_date:
                trade_count = conn.execute(
                    "SELECT COUNT(*) AS total FROM paper_trades WHERE substr(created_at, 1, 10) = ?",
                    (session_date,),
                ).fetchone()
                candidate_count = conn.execute(
                    "SELECT COUNT(*) AS total FROM paper_candidates WHERE substr(created_at, 1, 10) = ?",
                    (session_date,),
                ).fetchone()
                archive_count = conn.execute(
                    "SELECT COUNT(*) AS total FROM pretrade_predictions WHERE substr(created_at, 1, 10) = ?",
                    (session_date,),
                ).fetchone()
                conn.execute("DELETE FROM paper_trades WHERE substr(created_at, 1, 10) = ?", (session_date,))
                conn.execute("DELETE FROM paper_candidates WHERE substr(created_at, 1, 10) = ?", (session_date,))
                conn.execute("DELETE FROM pretrade_predictions WHERE substr(created_at, 1, 10) = ?", (session_date,))
            else:
                trade_count = conn.execute("SELECT COUNT(*) AS total FROM paper_trades").fetchone()
                candidate_count = conn.execute("SELECT COUNT(*) AS total FROM paper_candidates").fetchone()
                archive_count = conn.execute("SELECT COUNT(*) AS total FROM pretrade_predictions").fetchone()
                conn.execute("DELETE FROM paper_trades")
                conn.execute("DELETE FROM paper_candidates")
                conn.execute("DELETE FROM pretrade_predictions")
        return {
            "status": "ok",
            "deleted": int(trade_count["total"] or 0) + int(candidate_count["total"] or 0) + int(archive_count["total"] or 0),
            "scope": session_date or "all",
        }

    def _apply_entry_slippage(self, *, direction: str, entry_price: float) -> float:
        slippage = entry_price * (self.config.paper_trade_slippage_bps / 10000.0)
        if direction == "BULLISH":
            return entry_price + slippage
        return max(entry_price - slippage, 0.01)

    def _apply_exit_slippage(self, *, direction: str, exit_price: float) -> float:
        slippage = exit_price * (self.config.paper_trade_slippage_bps / 10000.0)
        if direction == "BULLISH":
            return max(exit_price - slippage, 0.01)
        return exit_price + slippage

    def _execution_cost(self, price: float | None) -> float:
        if price is None or price <= 0:
            return 0.0
        spread_cost = price * (self.config.paper_trade_slippage_bps / 10000.0) * self.config.paper_trade_spread_capture_ratio
        return max(spread_cost + self.config.paper_trade_fixed_cost_points, 0.0)

    def _entry_confirmation_buffer(self, candidate: PendingTrigger) -> float:
        risk = max(abs(candidate.entry_trigger - candidate.stop_loss), 0.01)
        reward = max(abs(candidate.target1 - candidate.entry_trigger), risk)
        buffer = max(
            reward * self.config.paper_trade_entry_confirm_ratio,
            risk * 0.12,
            candidate.entry_trigger * 0.0008,
            0.08,
        )
        if str(candidate.regime or "").upper() == "CHOPPY":
            buffer *= float(self.config.paper_trade_choppy_confirm_multiplier)
        return buffer

    def _max_chase_buffer(self, candidate: PendingTrigger) -> float:
        risk = max(abs(candidate.entry_trigger - candidate.stop_loss), 0.01)
        reward = max(abs(candidate.target1 - candidate.entry_trigger), risk)
        buffer = max(
            reward * self.config.paper_trade_max_chase_ratio,
            risk * 0.45,
            candidate.entry_trigger * 0.0018,
            0.15,
        )
        if str(candidate.regime or "").upper() == "CHOPPY":
            buffer *= float(self.config.paper_trade_choppy_chase_multiplier)
        return buffer

    @staticmethod
    def _classify_sl_hit(*, trade: ActivePaperTrade, entry: float, timestamp: datetime, mfe_points: float) -> str:
        risk = max(abs(entry - trade.stop_loss), 0.01)
        hold_sec = max((timestamp - trade.created_at).total_seconds(), 0.0)
        if trade.t1_hit:
            return "gave_back_after_t1"
        if hold_sec <= 180 and mfe_points <= risk * 0.2:
            return "fast_failure"
        if mfe_points >= risk * 0.6:
            return "reversal_after_progress"
        return "clean_invalidation"
