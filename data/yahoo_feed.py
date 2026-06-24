from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

import pandas as pd
import yfinance as yf
from tenacity import retry, stop_after_attempt, wait_exponential


@dataclass
class FetchResult:
    data: dict[str, pd.DataFrame]
    failed: dict[str, str]
    source: str = "Yahoo Finance"


def yahoo_symbol(symbol: str) -> str:
    symbol = str(symbol).upper().strip()
    if symbol.startswith("^") or symbol.endswith(".NS") or symbol.endswith(".BO"):
        return symbol
    return f"{symbol}.NS"


def clean_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    frame = df.copy()
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = [c[0] if isinstance(c, tuple) else c for c in frame.columns]
    frame = frame.loc[:, ~pd.Index(frame.columns).duplicated(keep="first")]
    frame = frame.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Adj Close": "adj_close", "Volume": "volume"})
    keep = [c for c in ["open", "high", "low", "close", "adj_close", "volume"] if c in frame.columns]
    frame = frame[keep].dropna(subset=["open", "high", "low", "close"], how="any")
    for col in ["open", "high", "low", "close", "adj_close", "volume"]:
        if col in frame.columns and isinstance(frame[col], pd.DataFrame):
            frame[col] = frame[col].iloc[:, 0]
    if "volume" not in frame:
        frame["volume"] = 0
    for col in ["open", "high", "low", "close", "adj_close", "volume"]:
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame["volume"] = frame["volume"].fillna(0)
    frame.index = pd.to_datetime(frame.index)
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    return frame


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.7, min=1, max=4), reraise=True)
def fetch_history(symbol: str, period: str = "5d", interval: str = "5m") -> pd.DataFrame:
    df = yf.download(tickers=yahoo_symbol(symbol), period=period, interval=interval, progress=False, auto_adjust=False, prepost=False, threads=False)
    return clean_ohlcv(df)


def fetch_batch(symbols: Iterable[str], period: str = "5d", interval: str = "5m") -> FetchResult:
    symbols = list(dict.fromkeys([str(s).upper().strip() for s in symbols if str(s).strip()]))
    data: dict[str, pd.DataFrame] = {}
    failed: dict[str, str] = {}
    if not symbols:
        return FetchResult(data=data, failed=failed)
    yf_symbols = [yahoo_symbol(s) for s in symbols]
    reverse = dict(zip(yf_symbols, symbols))
    try:
        raw = yf.download(tickers=" ".join(yf_symbols), period=period, interval=interval, group_by="ticker", progress=False, auto_adjust=False, prepost=False, threads=True)
        if raw.empty:
            raise RuntimeError("empty batch response")
        if isinstance(raw.columns, pd.MultiIndex):
            for yf_symbol in yf_symbols:
                if yf_symbol in raw.columns.get_level_values(0):
                    cleaned = clean_ohlcv(raw[yf_symbol])
                    if cleaned.empty:
                        failed[reverse[yf_symbol]] = "empty candles"
                    else:
                        data[reverse[yf_symbol]] = cleaned
        else:
            cleaned = clean_ohlcv(raw)
            if len(symbols) == 1 and not cleaned.empty:
                data[symbols[0]] = cleaned
    except Exception as exc:
        failed["batch"] = str(exc)
    for symbol in [s for s in symbols if s not in data][:80]:
        try:
            df = fetch_history(symbol, period=period, interval=interval)
            if df.empty:
                failed[symbol] = "empty candles"
            else:
                data[symbol] = df
        except Exception as exc:
            failed[symbol] = str(exc)
    return FetchResult(data=data, failed=failed)


def fetch_quote(symbol: str) -> dict:
    ticker = yf.Ticker(yahoo_symbol(symbol))
    info = ticker.fast_info or {}
    return {
        "symbol": symbol,
        "ltp": float(info.get("last_price") or info.get("lastPrice") or 0),
        "previous_close": float(info.get("previous_close") or 0),
        "last_updated": datetime.now().isoformat(timespec="seconds"),
    }
