from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
import hmac
from io import StringIO
import json
import logging
import os
from pathlib import Path
import struct
import threading
import time
from datetime import datetime
from typing import Iterable, Any, Callable

import pandas as pd
import requests


@dataclass
class KotakQuote:
    symbol: str
    ltp: float
    instrument_token: str | None = None
    exchange_segment: str = "nse_cm"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class KotakLiveTick:
    symbol: str
    ltp: float
    instrument_token: str
    exchange_segment: str = "nse_cm"
    received_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    raw: dict[str, Any] = field(default_factory=dict)


class KotakNeoFeed:
    """Kotak Neo market-data adapter.

    Kotak Neo Trade API v2 supports scrip master, quotes, and websockets. Kotak's
    public support page currently says historical candle data is not available
    on Neo Trade API, so this adapter supplies live LTP and leaves candle history
    to the router fallback.
    """

    def __init__(
        self,
        consumer_key: str | None,
        access_token: str | None = None,
        environment: str = "prod",
        neo_fin_key: str | None = None,
        mobile_number: str | None = None,
        ucc: str | None = None,
        mpin: str | None = None,
        totp_secret: str | None = None,
        totp_code: str | None = None,
    ) -> None:
        self.consumer_key = (consumer_key or "").strip()
        self.access_token = (access_token or "").strip() or None
        self.environment = environment
        self.neo_fin_key = neo_fin_key
        self.mobile_number = self.normalize_mobile_number(mobile_number)
        self.ucc = (ucc or "").strip() or None
        self.mpin = (mpin or "").strip() or None
        self.totp_secret = (totp_secret or "").strip() or None
        self.totp_code = (totp_code or "").strip() or None
        self._client = None
        self._master_by_segment: dict[str, pd.DataFrame] = {}
        self._authenticated = False
        self.auth_status = "not_attempted"
        self.auth_error: str | None = None
        self.warnings: list[str] = []
        self.session_path = Path(__file__).resolve().parents[1] / "storage" / "kotak_session.json"
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._ws_ready = threading.Event()
        self._stop_live = threading.Event()
        self._ws_lock = threading.RLock()
        self._reconnect_thread: threading.Thread | None = None
        self._live_callback: Callable[[KotakLiveTick], None] | None = None
        self._close_callback: Callable[[str], None] | None = None
        self._error_callback: Callable[[str], None] | None = None
        self._subscriptions: list[dict[str, str]] = []
        self._subscriptions_are_index = False
        self._token_to_symbol: dict[str, str] = {}
        self._latest_ticks: dict[str, KotakLiveTick] = {}
        self._reconnect_enabled = True
        self._reconnect_delay = 5.0
        self._max_reconnect_attempts: int | None = None
        self._reconnect_attempts = 0

    @staticmethod
    def normalize_mobile_number(mobile_number: str | None) -> str | None:
        raw = str(mobile_number or "").strip()
        digits = "".join(ch for ch in raw if ch.isdigit())
        if not digits:
            return None
        if raw.startswith("+"):
            return f"+{digits}"
        if len(digits) == 10 and digits[0] in {"6", "7", "8", "9"}:
            country_code = "".join(ch for ch in os.getenv("KOTAK_COUNTRY_CODE", "91") if ch.isdigit()) or "91"
            return f"+{country_code}{digits}"
        if len(digits) == 12 and digits.startswith("91"):
            return f"+{digits}"
        return digits

    @property
    def configured(self) -> bool:
        return bool(self.consumer_key)

    def required_login_fields(self) -> dict[str, bool]:
        return {
            "KOTAK_CONSUMER_KEY": bool(self.consumer_key),
            "KOTAK_MOBILE_NUMBER": bool(self.mobile_number),
            "KOTAK_UCC": bool(self.ucc),
            "KOTAK_MPIN": bool(self.mpin),
            "KOTAK_TOTP_SECRET_OR_UI_TOTP": bool(self.totp_secret or self.totp_code),
        }

    def client(self):
        if not self.configured:
            raise RuntimeError("KOTAK_NEO_CONSUMER_KEY is not configured")
        if self._client is not None:
            return self._client
        self._configure_kotak_network()
        try:
            from neo_api_client import NeoAPI
        except Exception as exc:
            raise RuntimeError(
                "neo_api_client is not installed. Install Kotak Neo SDK to enable primary live quotes."
            ) from exc
        self._client = NeoAPI(
            environment=self.environment,
            access_token=self.access_token,
            neo_fin_key=self.neo_fin_key,
            consumer_key=self.consumer_key,
        )
        self._apply_persisted_session()
        return self._client

    def scrip_master(self, exchange_segment: str = "nse_cm") -> pd.DataFrame:
        self.ensure_authenticated()
        cache_key = str(exchange_segment).strip().lower()
        if cache_key in self._master_by_segment:
            return self._master_by_segment[cache_key].copy()
        raw = self.client().scrip_master(exchange_segment=exchange_segment)
        self._raise_on_error(raw)
        frame = self._coerce_master(raw)
        if frame.empty:
            raise RuntimeError("Kotak scrip master returned no rows")
        frame["symbol_norm"] = frame["trading_symbol"].astype(str).str.upper().str.replace("-EQ", "", regex=False).str.strip()
        self._master_by_segment[cache_key] = frame
        return frame.copy()

    def quote_ltp(self, symbols: Iterable[str], exchange_segment: str = "nse_cm") -> dict[str, KotakQuote]:
        self.ensure_authenticated()
        tokens = self.resolve_tokens(symbols, exchange_segment=exchange_segment)
        if not tokens:
            return {}
        request = [
            {"instrument_token": token, "exchange_segment": exchange_segment}
            for token in tokens.values()
            if token
        ]
        if not request:
            return {}
        raw = self.client().quotes(instrument_tokens=request, quote_type="ltp")
        self._raise_on_error(raw)
        quote_rows = self._coerce_quote_rows(raw)
        by_token: dict[str, dict] = {}
        for item in quote_rows:
            token = self._extract_token(item)
            if token:
                by_token[token] = item

        quotes: dict[str, KotakQuote] = {}
        for symbol, token in tokens.items():
            item = by_token.get(str(token), {})
            ltp = self._extract_ltp(item)
            if ltp and ltp > 0:
                quotes[symbol] = KotakQuote(symbol=symbol, ltp=ltp, instrument_token=str(token), exchange_segment=exchange_segment, raw=item)
        return quotes

    def quote_snapshot(self, symbols: Iterable[str], exchange_segment: str = "nse_cm", batch_size: int = 50) -> pd.DataFrame:
        self.ensure_authenticated()
        tokens = self.resolve_tokens(symbols, exchange_segment=exchange_segment)
        if not tokens:
            return pd.DataFrame()
        reverse = {str(token): symbol for symbol, token in tokens.items()}
        rows: list[dict] = []
        token_items = list(tokens.items())
        for i in range(0, len(token_items), max(batch_size, 1)):
            chunk = token_items[i:i + max(batch_size, 1)]
            request = [{"instrument_token": token, "exchange_segment": exchange_segment} for _, token in chunk if token]
            if not request:
                continue
            raw = self.client().quotes(instrument_tokens=request, quote_type="all")
            self._raise_on_error(raw)
            for item in self._coerce_quote_rows(raw):
                token = self._extract_token(item)
                symbol = reverse.get(token)
                if not symbol:
                    continue
                ltp = self._extract_number(item, ["ltp", "last_traded_price", "lastTradedPrice", "last_price", "lastPrice", "LTP"])
                if ltp <= 0:
                    continue
                ohlc = item.get("ohlc") if isinstance(item.get("ohlc"), dict) else {}
                rows.append(
                    {
                        "symbol": symbol,
                        "instrument_token": token,
                        "ltp": ltp,
                        "open": self._extract_number(item, ["open", "open_price", "openPrice", "openingPrice", "op", "o"], nested=ohlc, nested_keys=["open", "op", "openingPrice"]),
                        "high": self._extract_number(item, ["high", "high_price", "highPrice", "h"], nested=ohlc, nested_keys=["high", "h", "highPrice"]),
                        "low": self._extract_number(item, ["low", "low_price", "lowPrice", "lo", "l"], nested=ohlc, nested_keys=["low", "lo", "lowPrice"]),
                        "prev_close": self._extract_number(item, ["close", "prev_close", "previous_close", "previousClose", "prev_day_close", "c", "ic"], nested=ohlc, nested_keys=["close", "c"]),
                        "volume": self._extract_number(item, ["volume", "traded_volume", "tradedVolume", "ttq", "totalTradedVolume", "last_volume", "v"]),
                        "raw": item,
                    }
                )
        return pd.DataFrame(rows)

    def quote_token_snapshot(self, token_map: dict[str, dict[str, str]], quote_type: str = "all") -> dict[str, dict[str, Any]]:
        self.ensure_authenticated()
        request = []
        reverse: dict[str, str] = {}
        for label, meta in token_map.items():
            token = str(meta.get("instrument_token") or "").strip()
            segment = str(meta.get("exchange_segment") or "nse_cm").strip().lower()
            if not token:
                continue
            request.append({"instrument_token": token, "exchange_segment": segment})
            reverse[token] = str(label).upper()
        if not request:
            return {}
        raw = self.client().quotes(instrument_tokens=request, quote_type=quote_type)
        self._raise_on_error(raw)
        result: dict[str, dict[str, Any]] = {}
        for item in self._coerce_quote_rows(raw):
            token = self._extract_token(item)
            label = reverse.get(str(token))
            if not label:
                continue
            ohlc = item.get("ohlc") if isinstance(item.get("ohlc"), dict) else {}
            ltp = self._extract_number(item, ["iv", "ltp", "last_traded_price", "lastTradedPrice", "last_price", "lastPrice", "LTP"])
            if ltp <= 0:
                ltp = self._extract_ltp(item)
            if ltp <= 0:
                continue
            result[label] = {
                "symbol": label,
                "instrument_token": str(token),
                "exchange_segment": str(token_map.get(label, {}).get("exchange_segment") or "nse_cm").lower(),
                "ltp": ltp,
                "open": self._extract_number(item, ["open", "open_price", "openPrice", "openingPrice", "op", "o"], nested=ohlc, nested_keys=["open", "op", "openingPrice"]),
                "high": self._extract_number(item, ["high", "high_price", "highPrice", "h"], nested=ohlc, nested_keys=["high", "h", "highPrice"]),
                "low": self._extract_number(item, ["low", "low_price", "lowPrice", "lo", "l"], nested=ohlc, nested_keys=["low", "lo", "lowPrice"]),
                "prev_close": self._extract_number(item, ["ic", "close", "prev_close", "previous_close", "previousClose", "prev_day_close", "c"], nested=ohlc, nested_keys=["close", "c"]),
                "volume": self._extract_number(item, ["volume", "traded_volume", "tradedVolume", "ttq", "totalTradedVolume", "last_volume", "v"]),
                "raw": item,
            }
        return result

    def live_quote_snapshot(
        self,
        symbols: Iterable[str],
        exchange_segment: str = "nse_cm",
        batch_size: int = 50,
        live_timeout: float = 6.0,
        poll_interval: float = 0.2,
    ) -> pd.DataFrame:
        base = self.quote_snapshot(symbols, exchange_segment=exchange_segment, batch_size=batch_size)
        if base.empty:
            return base

        instruments = [
            {
                "instrument_token": str(row["instrument_token"]),
                "exchange_segment": exchange_segment,
                "symbol": str(row["symbol"]).upper(),
            }
            for _, row in base.iterrows()
            if str(row.get("instrument_token", "")).strip()
        ]
        if not instruments:
            return base

        target_tokens = {item["instrument_token"] for item in instruments}
        received_tokens: set[str] = set()

        def on_tick(tick: KotakLiveTick) -> None:
            received_tokens.add(tick.instrument_token)

        try:
            self.start_live_feed(
                instruments=instruments,
                on_tick=on_tick,
                reconnect=False,
                wait_timeout=max(live_timeout, 10.0),
            )
            started = time.time()
            while time.time() - started < live_timeout:
                if received_tokens >= target_tokens:
                    break
                time.sleep(poll_interval)
        finally:
            self.stop_live_feed()

        latest = self.get_latest_live_ticks()
        if not latest:
            return base

        enriched = base.copy()
        updated_rows = 0
        for idx, row in enriched.iterrows():
            token = str(row.get("instrument_token", "")).strip()
            tick = latest.get(token)
            if tick is None:
                continue
            enriched.at[idx, "ltp"] = tick.ltp
            raw = row.get("raw")
            merged_raw = dict(raw) if isinstance(raw, dict) else {}
            merged_raw["live_tick"] = tick.raw
            enriched.at[idx, "raw"] = merged_raw
            updated_rows += 1
        self.logger.info("Updated %d/%d symbols with websocket live ticks.", updated_rows, len(enriched))
        return enriched

    def resolve_tokens(self, symbols: Iterable[str], exchange_segment: str = "nse_cm") -> dict[str, str]:
        symbols = [str(s).upper().strip() for s in symbols if str(s).strip()]
        if not symbols:
            return {}
        master = self.scrip_master(exchange_segment=exchange_segment)
        token_col = self._first_existing(master, ["instrument_token", "pSymbol", "token", "scrip_token", "pSymbolName"])
        if token_col is None:
            raise RuntimeError("Kotak scrip master token column not found")
        mapping: dict[str, str] = {}
        indexed = master.drop_duplicates("symbol_norm").set_index("symbol_norm")
        for symbol in symbols:
            if symbol in indexed.index:
                mapping[symbol] = str(indexed.loc[symbol, token_col])
        return mapping

    def ensure_authenticated(self) -> None:
        if self._authenticated:
            return
        client = self.client()
        config = getattr(client, "configuration", None)
        if self._has_trade_session(config):
            self._authenticated = True
            self.auth_status = "restored_session"
            return
        if not all([self.mobile_number, self.ucc, self.mpin]) or not (self.totp_code or self.totp_secret):
            self.auth_status = "missing_credentials"
            self.auth_error = "Missing broker login fields. Set KOTAK_MOBILE_NUMBER, KOTAK_UCC, KOTAK_MPIN, and either KOTAK_TOTP_SECRET or provide a TOTP code in the UI."
            raise RuntimeError(self.auth_error)

        totp_value = self.resolve_totp_value()
        login_resp = client.totp_login(mobile_number=self.mobile_number, ucc=self.ucc, totp=totp_value)
        self._raise_on_error(login_resp)
        validate_resp = client.totp_validate(mpin=self.mpin)
        self._raise_on_error(validate_resp)

        config = getattr(client, "configuration", None)
        if not self._has_trade_session(config):
            self.auth_status = "validation_incomplete"
            self.auth_error = "Kotak login did not return a usable trade session."
            raise RuntimeError(self.auth_error)

        self._authenticated = True
        self.auth_status = "authenticated"
        self.auth_error = None
        self.persist_session()

    def reauthenticate(self) -> None:
        self.clear_session(purge_saved=True)
        self.ensure_authenticated()

    def clear_session(self, purge_saved: bool = False) -> None:
        self.stop_live_feed()
        self._authenticated = False
        self._master_by_segment = {}
        if self._client is not None:
            self._clear_client_session(self._client)
        if purge_saved:
            self._delete_persisted_session()

    def start_live_feed(
        self,
        instruments: Iterable[dict[str, str]],
        on_tick: Callable[[KotakLiveTick], None] | None = None,
        on_close: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        is_index: bool = False,
        reconnect: bool = True,
        reconnect_delay: float = 5.0,
        max_reconnect_attempts: int | None = None,
        wait_timeout: float = 15.0,
    ) -> None:
        normalized = self.normalize_instruments(instruments)
        if not normalized:
            raise RuntimeError("No valid instruments were provided for live subscription.")

        self.ensure_authenticated()
        self._subscriptions = normalized
        if is_index:
            for item in self._subscriptions:
                item["is_index"] = True
        self._token_to_symbol = {
            str(item["instrument_token"]): str(item.get("symbol") or item["instrument_token"])
            for item in normalized
        }
        self._live_callback = on_tick
        self._close_callback = on_close
        self._error_callback = on_error
        self._subscriptions_are_index = is_index
        self._reconnect_enabled = reconnect
        self._reconnect_delay = max(reconnect_delay, 1.0)
        self._max_reconnect_attempts = max_reconnect_attempts
        self._reconnect_attempts = 0
        self._stop_live.clear()
        self._subscribe_live(wait_timeout=wait_timeout)

    def stop_live_feed(self) -> None:
        self._stop_live.set()
        self._ws_ready.clear()
        client = self._client
        if client is None:
            return
        try:
            if self._subscriptions:
                payload = [
                    {
                        "instrument_token": item["instrument_token"],
                        "exchange_segment": item["exchange_segment"],
                    }
                    for item in self._subscriptions
                ]
                client.un_subscribe(payload, isIndex=getattr(self, "_subscriptions_are_index", False))
        except Exception:
            pass
        try:
            if getattr(client, "NeoWebSocket", None) is not None:
                socket_obj = client.NeoWebSocket
                if getattr(socket_obj, "hsWebsocket", None) is not None:
                    socket_obj.hsWebsocket.close()
                client.NeoWebSocket = None
        except Exception:
            pass

    def get_latest_live_ticks(self) -> dict[str, KotakLiveTick]:
        return dict(self._latest_ticks)

    def normalize_instruments(self, instruments: Iterable[dict[str, str]]) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        for item in instruments:
            if not isinstance(item, dict):
                continue
            token = str(item.get("instrument_token") or "").strip()
            segment = str(item.get("exchange_segment") or "nse_cm").strip().lower()
            symbol = str(item.get("symbol") or token).strip().upper()
            if not token or not segment:
                continue
            normalized.append(
                {
                    "instrument_token": token,
                    "exchange_segment": segment,
                    "symbol": symbol,
                    "is_index": bool(item.get("is_index", False)),
                }
            )
        return normalized

    def is_probable_session_error(self, exc: Exception | str) -> bool:
        message = str(exc).lower()
        hints = [
            "session",
            "token",
            "auth",
            "login",
            "invalid sid",
            "expired",
            "unauthorized",
            "forbidden",
        ]
        return any(hint in message for hint in hints)

    def resolve_totp_value(self) -> str:
        secret = (self.totp_secret or "").strip()
        code = (self.totp_code or "").strip()
        if secret:
            if secret.isdigit() and len(secret) == 6:
                if code.isdigit() and len(code) == 6:
                    return code
                raise RuntimeError(
                    "KOTAK_TOTP_SECRET must be the permanent authenticator setup key, not a current 6-digit TOTP code. "
                    "Enter a fresh code in /kotak-login or replace KOTAK_TOTP_SECRET with the setup key for automatic re-login."
                )
            return self.generate_totp(secret)
        if not code:
            raise RuntimeError("TOTP value is missing.")
        if code.isdigit() and len(code) == 6:
            return code
        return self.generate_totp(code)

    def generate_totp(self, secret: str, digits: int = 6, period: int = 30) -> str:
        normalized = secret.replace(" ", "").upper()
        padding = "=" * ((8 - len(normalized) % 8) % 8)
        key = base64.b32decode(normalized + padding, casefold=True)
        counter = int(time.time() // period)
        msg = struct.pack(">Q", counter)
        digest = hmac.new(key, msg, hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
        return str(code % (10 ** digits)).zfill(digits)

    def _raise_on_error(self, raw: Any) -> None:
        if isinstance(raw, dict):
            err = raw.get("Error Message") or raw.get("error") or raw.get("message")
            if isinstance(err, list) and err:
                first = err[0]
                if isinstance(first, dict):
                    err = first.get("message") or first.get("code") or json.dumps(first)
            if err:
                self.auth_error = str(err)
                raise RuntimeError(str(err))

    def _coerce_master(self, raw: Any) -> pd.DataFrame:
        if isinstance(raw, pd.DataFrame):
            df = raw.copy()
        elif isinstance(raw, str) and Path(raw).exists():
            df = pd.read_csv(raw)
        elif isinstance(raw, str) and raw.lower().startswith(("http://", "https://")):
            df = self._read_remote_master(raw)
        elif isinstance(raw, list):
            df = pd.DataFrame(raw)
        elif isinstance(raw, dict):
            payload = raw.get("data") or raw.get("result") or raw.get("scrips") or raw
            if isinstance(payload, str) and Path(payload).exists():
                df = pd.read_csv(payload)
            elif isinstance(payload, str) and payload.lower().startswith(("http://", "https://")):
                df = self._read_remote_master(payload)
            else:
                df = pd.DataFrame(payload if isinstance(payload, list) else [payload])
        else:
            df = pd.DataFrame()
        if df.empty:
            return df
        df.columns = [str(c).strip() for c in df.columns]
        trading_col = self._first_existing(df, ["trading_symbol", "pTrdSymbol", "symbol", "Symbol", "pSymbolName"])
        if trading_col is None:
            return pd.DataFrame()
        df = df.rename(columns={trading_col: "trading_symbol"})
        return df

    def _read_remote_master(self, url: str) -> pd.DataFrame:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        text = response.text
        try:
            return pd.read_csv(StringIO(text))
        except Exception:
            return pd.read_csv(StringIO(text), sep="|")

    def _coerce_quote_rows(self, raw: Any) -> list[dict]:
        if isinstance(raw, list):
            return [x for x in raw if isinstance(x, dict)]
        if not isinstance(raw, dict):
            return []
        payload = raw.get("data") or raw.get("result") or raw.get("quotes") or raw.get("message") or raw
        if isinstance(payload, list):
            return [x for x in payload if isinstance(x, dict)]
        if isinstance(payload, dict):
            nested = payload.get("data") or payload.get("ltp") or payload.get("quotes")
            if isinstance(nested, list):
                return [x for x in nested if isinstance(x, dict)]
            return list(payload.values()) if all(isinstance(v, dict) for v in payload.values()) else [payload]
        return []

    def _extract_ltp(self, item: dict) -> float:
        return self._extract_number(item, ["iv", "ltp", "last_traded_price", "lastTradedPrice", "last_price", "lastPrice", "LTP"])

    def _extract_token(self, item: dict) -> str:
        value = (
            item.get("instrument_token")
            or item.get("instrumentToken")
            or item.get("token")
            or item.get("exchange_token")
            or item.get("tk")
            or item.get("pSymbol")
            or item.get("scripToken")
            or ""
        )
        return str(value).strip()

    def _extract_number(self, item: dict, keys: list[str], nested: dict | None = None, nested_keys: list[str] | None = None) -> float:
        for key in keys:
            value = item.get(key)
            try:
                if value is not None and float(value) > 0:
                    return float(value)
            except (TypeError, ValueError):
                continue
        if nested and nested_keys:
            for key in nested_keys:
                value = nested.get(key)
                try:
                    if value is not None and float(value) > 0:
                        return float(value)
                except (TypeError, ValueError):
                    continue
        return 0.0

    def _first_existing(self, df: pd.DataFrame, candidates: list[str]) -> str | None:
        lowered = {str(c).lower(): c for c in df.columns}
        for candidate in candidates:
            if candidate in df.columns:
                return candidate
            if candidate.lower() in lowered:
                return lowered[candidate.lower()]
        return None

    def _has_trade_session(self, config: Any) -> bool:
        return bool(
            config
            and getattr(config, "edit_token", None)
            and getattr(config, "edit_sid", None)
            and getattr(config, "base_url", None)
        )

    def _persistable_session(self, config: Any) -> dict[str, Any]:
        return {
            "consumer_key": self.consumer_key,
            "environment": self.environment,
            "updated_at": int(time.time()),
            "view_token": getattr(config, "view_token", None),
            "sid": getattr(config, "sid", None),
            "edit_token": getattr(config, "edit_token", None),
            "edit_sid": getattr(config, "edit_sid", None),
            "edit_rid": getattr(config, "edit_rid", None),
            "serverId": getattr(config, "serverId", None),
            "data_center": getattr(config, "data_center", None),
            "base_url": getattr(config, "base_url", None),
        }

    def persist_session(self) -> None:
        client = self.client()
        config = getattr(client, "configuration", None)
        if not self._has_trade_session(config):
            return
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        self.session_path.write_text(json.dumps(self._persistable_session(config), indent=2), encoding="utf-8")

    def _load_persisted_session(self) -> dict[str, Any] | None:
        if not self.session_path.exists():
            return None
        try:
            payload = json.loads(self.session_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        if payload.get("consumer_key") != self.consumer_key or payload.get("environment") != self.environment:
            return None
        if not payload.get("edit_token") or not payload.get("edit_sid") or not payload.get("base_url"):
            return None
        return payload

    def _apply_persisted_session(self) -> None:
        client = self._client
        config = getattr(client, "configuration", None)
        if self._has_trade_session(config):
            return
        payload = self._load_persisted_session()
        if not payload or not config:
            return
        config.view_token = payload.get("view_token")
        config.sid = payload.get("sid")
        config.edit_token = payload.get("edit_token")
        config.edit_sid = payload.get("edit_sid")
        config.edit_rid = payload.get("edit_rid")
        config.serverId = payload.get("serverId")
        config.data_center = payload.get("data_center")
        config.base_url = payload.get("base_url")

    def _clear_client_session(self, client: Any) -> None:
        config = getattr(client, "configuration", None)
        if not config:
            return
        for key in [
            "view_token",
            "sid",
            "edit_token",
            "edit_sid",
            "edit_rid",
            "serverId",
            "data_center",
            "base_url",
        ]:
            setattr(config, key, None)

    def _delete_persisted_session(self) -> None:
        try:
            if self.session_path.exists():
                self.session_path.unlink()
        except Exception:
            pass

    def _configure_kotak_network(self) -> None:
        proxy_vars = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]
        broken_proxies = {"http://127.0.0.1:9", "https://127.0.0.1:9", "http://localhost:9", "https://localhost:9"}
        active = {name: (os.getenv(name) or "").strip() for name in proxy_vars}
        if not any(value in broken_proxies for value in active.values() if value):
            return
        no_proxy_values = [part.strip() for part in (os.getenv("NO_PROXY") or os.getenv("no_proxy") or "").split(",") if part.strip()]
        for host in ["kotaksecurities.com", ".kotaksecurities.com"]:
            if host not in no_proxy_values:
                no_proxy_values.append(host)
        joined = ",".join(no_proxy_values)
        os.environ["NO_PROXY"] = joined
        os.environ["no_proxy"] = joined
        for name, value in active.items():
            if value in broken_proxies:
                os.environ.pop(name, None)

    def _subscribe_live(self, wait_timeout: float) -> None:
        client = self.client()
        self._ws_ready.clear()
        with self._ws_lock:
            client.on_message = self._handle_ws_message
            client.on_open = self._handle_ws_open
            client.on_close = self._handle_ws_close
            client.on_error = self._handle_ws_error
            if getattr(client, "NeoWebSocket", None) is not None:
                try:
                    socket_obj = client.NeoWebSocket
                    if getattr(socket_obj, "hsWebsocket", None) is not None:
                        socket_obj.hsWebsocket.close()
                except Exception:
                    pass
                client.NeoWebSocket = None

            payload = [
                {
                    "instrument_token": item["instrument_token"],
                    "exchange_segment": item["exchange_segment"],
                }
                for item in self._subscriptions
            ]
            self.logger.info("Subscribing to %d instrument(s): %s", len(payload), payload)
            client.subscribe(instrument_tokens=payload, isIndex=getattr(self, "_subscriptions_are_index", False))

        if not self._ws_ready.wait(timeout=wait_timeout):
            raise RuntimeError(f"Timed out waiting for Kotak live websocket open after {wait_timeout:.0f}s.")

    def _handle_ws_open(self, message: Any) -> None:
        self._ws_ready.set()
        self._reconnect_attempts = 0
        self.logger.info("Kotak websocket opened: %s", message)

    def _handle_ws_close(self, message: Any) -> None:
        self._ws_ready.clear()
        text = str(message)
        self.logger.warning("Kotak websocket closed: %s", text)
        if self._close_callback:
            self._close_callback(text)
        self._schedule_reconnect("close")

    def _handle_ws_error(self, error: Any) -> None:
        self._ws_ready.clear()
        text = str(error)
        self.logger.error("Kotak websocket error: %s", text)
        if self._error_callback:
            self._error_callback(text)
        self._schedule_reconnect("error", error=text)

    def _handle_ws_message(self, message: Any) -> None:
        self.logger.debug("Kotak websocket message: %s", message)
        rows = self._extract_live_rows(message)
        if not rows:
            return
        for row in rows:
            token = self._extract_token(row)
            if not token:
                continue
            ltp = self._extract_ltp(row)
            if ltp <= 0:
                continue
            tick = KotakLiveTick(
                symbol=self._token_to_symbol.get(token, token),
                instrument_token=token,
                exchange_segment=str(row.get("e") or row.get("exchange_segment") or row.get("exchangeSegment") or "nse_cm").lower(),
                ltp=ltp,
                raw=row,
            )
            self._latest_ticks[token] = tick
            self.logger.info(
                "LIVE_TICK symbol=%s token=%s segment=%s ltp=%s",
                tick.symbol,
                tick.instrument_token,
                tick.exchange_segment,
                tick.ltp,
            )
            if self._live_callback:
                self._live_callback(tick)

    def _extract_live_rows(self, message: Any) -> list[dict[str, Any]]:
        if isinstance(message, dict):
            payload = message.get("data")
            if isinstance(payload, list):
                return [item for item in payload if isinstance(item, dict)]
            if isinstance(payload, dict):
                return [payload]
            return []
        if isinstance(message, list):
            return [item for item in message if isinstance(item, dict)]
        return []

    def _schedule_reconnect(self, reason: str, error: str | None = None) -> None:
        if self._stop_live.is_set() or not self._reconnect_enabled or not self._subscriptions:
            return
        if self._reconnect_thread is not None and self._reconnect_thread.is_alive():
            return
        self._reconnect_thread = threading.Thread(
            target=self._reconnect_loop,
            kwargs={"reason": reason, "error": error},
            daemon=True,
            name="kotak-live-reconnect",
        )
        self._reconnect_thread.start()

    def _reconnect_loop(self, reason: str, error: str | None = None) -> None:
        while not self._stop_live.is_set():
            self._reconnect_attempts += 1
            if self._max_reconnect_attempts is not None and self._reconnect_attempts > self._max_reconnect_attempts:
                self.logger.error("Kotak reconnect limit reached after %d attempts.", self._max_reconnect_attempts)
                return

            self.logger.warning(
                "Reconnect attempt %d reason=%s error=%s delay=%.1fs",
                self._reconnect_attempts,
                reason,
                error or "-",
                self._reconnect_delay,
            )
            time.sleep(self._reconnect_delay)
            try:
                if error and self.is_probable_session_error(error):
                    self.logger.info("Re-authenticating Kotak session before reconnect.")
                    self.clear_session(purge_saved=False)
                    try:
                        self.ensure_authenticated()
                    except Exception:
                        if self.totp_secret:
                            self.reauthenticate()
                        else:
                            self.auth_status = "totp_required"
                            self.auth_error = "Kotak session closed; enter a fresh TOTP to reconnect live feed."
                            self.logger.error(self.auth_error)
                            return
                else:
                    self.ensure_authenticated()
                self._subscribe_live(wait_timeout=max(self._reconnect_delay * 2, 10.0))
                self.logger.info("Kotak live subscription restored.")
                return
            except Exception as exc:
                self.logger.error("Reconnect attempt %d failed: %s", self._reconnect_attempts, exc)

    def live_index_snapshot(
        self,
        index_map: dict[str, dict[str, str]],
        live_timeout: float = 4.0,
        poll_interval: float = 0.2,
    ) -> dict[str, dict[str, Any]]:
        return self.live_token_snapshot(index_map, live_timeout=live_timeout, poll_interval=poll_interval, is_index=True)

    def live_token_snapshot(
        self,
        token_map: dict[str, dict[str, str]],
        live_timeout: float = 4.0,
        poll_interval: float = 0.2,
        is_index: bool = False,
    ) -> dict[str, dict[str, Any]]:
        instruments = []
        for label, meta in token_map.items():
            token = str(meta.get("instrument_token") or "").strip()
            segment = str(meta.get("exchange_segment") or "nse_cm").strip().lower()
            if token:
                instruments.append(
                    {
                        "instrument_token": token,
                        "exchange_segment": segment,
                        "symbol": label,
                        "is_index": is_index,
                    }
                )
        if not instruments:
            return {}

        received_tokens: set[str] = set()

        def on_tick(tick: KotakLiveTick) -> None:
            received_tokens.add(tick.instrument_token)

        try:
            self.start_live_feed(
                instruments=instruments,
                on_tick=on_tick,
                is_index=is_index,
                reconnect=False,
                wait_timeout=max(live_timeout, 10.0),
            )
            started = time.time()
            while time.time() - started < live_timeout:
                if len(received_tokens) >= len(instruments):
                    break
                time.sleep(poll_interval)
        finally:
            self.stop_live_feed()

        latest = self.get_latest_live_ticks()
        result: dict[str, dict[str, Any]] = {}
        for label, meta in token_map.items():
            token = str(meta.get("instrument_token") or "").strip()
            tick = latest.get(token)
            if tick is None:
                continue
            raw = tick.raw
            ltp = self._extract_number(raw, ["iv", "ltp", "last_traded_price", "lastPrice", "LTP"])
            prev_close = self._extract_number(raw, ["ic", "c", "prev_day_close", "prev_close", "close"])
            high = self._extract_number(raw, ["highPrice", "high", "high_price"])
            low = self._extract_number(raw, ["lowPrice", "low", "low_price"])
            open_price = self._extract_number(raw, ["openingPrice", "open", "open_price"])
            result[label] = {
                "instrument_token": token,
                "exchange_segment": meta.get("exchange_segment", "nse_cm"),
                "ltp": ltp or tick.ltp,
                "prev_close": prev_close,
                "high": high,
                "low": low,
                "open": open_price,
                "raw": raw,
            }
        return result
