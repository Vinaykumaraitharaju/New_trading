from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import os
from typing import Iterable

import pandas as pd

from typing import Callable

from data.kotak_neo_feed import KotakNeoFeed, KotakQuote, KotakLiveTick

@dataclass
class SourceHealth:
    active_source: str = "Kotak Neo"
    quote_source: str = "Kotak Neo"
    ok: bool = True
    kotak_enabled: bool = False
    kotak_auth_status: str = "not_attempted"
    kotak_missing_fields: list[str] = field(default_factory=list)
    last_success: str | None = None
    warnings: list[str] = field(default_factory=list)


class SourceRouter:
    def __init__(self, kotak_consumer_key: str | None = None, kotak_access_token: str | None = None, kotak_totp_code: str | None = None) -> None:
        self.health = SourceHealth()
        consumer_key = kotak_consumer_key or os.getenv("KOTAK_CONSUMER_KEY") or os.getenv("KOTAK_NEO_CONSUMER_KEY")
        access_token = kotak_access_token or os.getenv("KOTAK_ACCESS_TOKEN") or os.getenv("KOTAK_NEO_ACCESS_TOKEN")
        environment = os.getenv("KOTAK_ENVIRONMENT", "prod")
        neo_fin_key = os.getenv("KOTAK_NEO_FIN_KEY")
        self.kotak = KotakNeoFeed(
            consumer_key=consumer_key,
            access_token=access_token,
            environment=environment,
            neo_fin_key=neo_fin_key,
            mobile_number=os.getenv("KOTAK_MOBILE_NUMBER"),
            ucc=os.getenv("KOTAK_UCC"),
            mpin=os.getenv("KOTAK_MPIN"),
            totp_secret=os.getenv("KOTAK_TOTP_SECRET"),
            totp_code=kotak_totp_code,
        )
        self.health.kotak_enabled = self.kotak.configured
        self.health.kotak_auth_status = self.kotak.auth_status
        self.health.kotak_missing_fields = [k for k, ok in self.kotak.required_login_fields().items() if not ok]
        if self.kotak.configured:
            self.health.active_source = "Kotak Neo"
            self.health.quote_source = "Kotak Neo"

    def fetch_live_quotes(self, symbols: Iterable[str]) -> dict[str, KotakQuote]:
        if not self.kotak.configured:
            return {}
        try:
            quotes = self.kotak.quote_ltp(symbols)
            if quotes:
                self.health.quote_source = "Kotak Neo"
                self.health.kotak_auth_status = self.kotak.auth_status
                self.health.last_success = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            else:
                self.health.kotak_auth_status = self.kotak.auth_status
                self.health.warnings.append("Kotak Neo returned no live quotes.")
            return quotes
        except Exception as exc:
            if self.kotak.is_probable_session_error(exc):
                try:
                    self.kotak.reauthenticate()
                    quotes = self.kotak.quote_ltp(symbols)
                    if quotes:
                        self.health.ok = True
                        self.health.quote_source = "Kotak Neo"
                        self.health.kotak_auth_status = self.kotak.auth_status
                        self.health.last_success = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        self.health.warnings.append("Saved Kotak session expired; re-authenticated successfully.")
                        return quotes
                except Exception as retry_exc:
                    exc = retry_exc
            self.health.active_source = "Kotak Neo auth failed"
            self.health.quote_source = "Unavailable"
            self.health.kotak_auth_status = self.kotak.auth_status
            auth_hint = f" [auth status: {self.kotak.auth_status}]" if self.kotak.auth_status else ""
            self.health.warnings.append(f"Kotak Neo quote error: {exc}{auth_hint}")
            return {}

    def validate_auth(self) -> dict:
        if not self.kotak.configured:
            self.health.ok = False
            self.health.kotak_auth_status = "missing_consumer_key"
            return {"ok": False, "message": "KOTAK_CONSUMER_KEY is missing."}
        try:
            self.kotak.ensure_authenticated()
            master = self.kotak.scrip_master("nse_cm")
            self.health.ok = True
            self.health.kotak_auth_status = self.kotak.auth_status
            self.health.last_success = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return {"ok": True, "message": f"Kotak authenticated. Loaded {len(master):,} NSE instruments."}
        except Exception as exc:
            if self.kotak.is_probable_session_error(exc):
                try:
                    self.kotak.reauthenticate()
                    master = self.kotak.scrip_master("nse_cm")
                    self.health.ok = True
                    self.health.kotak_auth_status = self.kotak.auth_status
                    self.health.last_success = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self.health.warnings.append("Saved Kotak session expired; re-authenticated successfully.")
                    return {"ok": True, "message": f"Kotak re-authenticated. Loaded {len(master):,} NSE instruments."}
                except Exception as retry_exc:
                    exc = retry_exc
            self.health.ok = False
            self.health.kotak_auth_status = self.kotak.auth_status
            self.health.warnings.append(f"Auth check failed: {exc}")
            return {"ok": False, "message": str(exc)}

    def submit_totp_code(self, totp_code: str) -> dict:
        self.kotak.totp_code = str(totp_code or "").strip()
        self.kotak.clear_session(purge_saved=True)
        self.health.kotak_missing_fields = [k for k, ok in self.kotak.required_login_fields().items() if not ok]
        return self.validate_auth()

    def fetch_quote_snapshot(self, symbols: Iterable[str], batch_size: int = 50) -> pd.DataFrame:
        try:
            df = self.kotak.quote_snapshot(symbols, batch_size=batch_size)
            self.health.ok = not df.empty
            self.health.kotak_auth_status = self.kotak.auth_status
            if not df.empty:
                self.health.active_source = "Kotak Neo"
                self.health.quote_source = "Kotak Neo"
                self.health.last_success = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            else:
                self.health.active_source = "Kotak Neo empty snapshot"
                self.health.quote_source = "Unavailable"
                self.health.warnings.append("Kotak quote snapshot returned no usable rows.")
            return df
        except Exception as exc:
            if self.kotak.is_probable_session_error(exc):
                try:
                    self.kotak.reauthenticate()
                    df = self.kotak.quote_snapshot(symbols, batch_size=batch_size)
                    self.health.ok = not df.empty
                    self.health.kotak_auth_status = self.kotak.auth_status
                    if not df.empty:
                        self.health.active_source = "Kotak Neo"
                        self.health.quote_source = "Kotak Neo"
                        self.health.last_success = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        self.health.active_source = "Kotak Neo empty snapshot"
                        self.health.quote_source = "Unavailable"
                    self.health.warnings.append("Saved Kotak session expired; re-authenticated successfully.")
                    return df
                except Exception as retry_exc:
                    exc = retry_exc
            self.health.ok = False
            self.health.active_source = "Kotak Neo auth failed"
            self.health.quote_source = "Unavailable"
            self.health.kotak_auth_status = self.kotak.auth_status
            self.health.warnings.append(f"Kotak snapshot error: {exc}")
            return pd.DataFrame()

    def fetch_live_quote_snapshot(self, symbols: Iterable[str], batch_size: int = 50, live_timeout: float = 6.0) -> pd.DataFrame:
        try:
            df = self.kotak.live_quote_snapshot(symbols, batch_size=batch_size, live_timeout=live_timeout)
            self.health.ok = not df.empty
            self.health.kotak_auth_status = self.kotak.auth_status
            if not df.empty:
                self.health.active_source = "Kotak Neo"
                self.health.quote_source = "Kotak Neo websocket"
                self.health.last_success = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            else:
                self.health.active_source = "Kotak Neo empty live snapshot"
                self.health.quote_source = "Unavailable"
                self.health.warnings.append("Kotak websocket live snapshot returned no usable rows.")
            return df
        except Exception as exc:
            if self.kotak.is_probable_session_error(exc):
                try:
                    self.kotak.reauthenticate()
                    df = self.kotak.live_quote_snapshot(symbols, batch_size=batch_size, live_timeout=live_timeout)
                    self.health.ok = not df.empty
                    self.health.kotak_auth_status = self.kotak.auth_status
                    if not df.empty:
                        self.health.active_source = "Kotak Neo"
                        self.health.quote_source = "Kotak Neo websocket"
                        self.health.last_success = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        self.health.active_source = "Kotak Neo empty live snapshot"
                        self.health.quote_source = "Unavailable"
                    self.health.warnings.append("Saved Kotak session expired; re-authenticated successfully.")
                    return df
                except Exception as retry_exc:
                    exc = retry_exc
            self.health.ok = False
            self.health.active_source = "Kotak Neo live auth failed"
            self.health.quote_source = "Unavailable"
            self.health.kotak_auth_status = self.kotak.auth_status
            self.health.warnings.append(f"Kotak live websocket error: {exc}")
            return pd.DataFrame()

    def start_live_feed(
        self,
        instruments: Iterable[dict[str, str]],
        on_tick: Callable[[KotakLiveTick], None] | None = None,
        on_close: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        reconnect: bool = True,
        reconnect_delay: float = 5.0,
        max_reconnect_attempts: int | None = None,
    ) -> None:
        self.kotak.start_live_feed(
            instruments=instruments,
            on_tick=on_tick,
            on_close=on_close,
            on_error=on_error,
            reconnect=reconnect,
            reconnect_delay=reconnect_delay,
            max_reconnect_attempts=max_reconnect_attempts,
        )
        self.health.ok = True
        self.health.active_source = "Kotak Neo"
        self.health.quote_source = "Kotak Neo websocket"
        self.health.kotak_auth_status = self.kotak.auth_status
        self.health.last_success = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def stop_live_feed(self) -> None:
        self.kotak.stop_live_feed()
