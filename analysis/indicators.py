from __future__ import annotations

import numpy as np
import pandas as pd


def _series(df: pd.DataFrame, column: str) -> pd.Series:
    value = df[column]
    if isinstance(value, pd.DataFrame):
        value = value.iloc[:, 0]
    return pd.to_numeric(value, errors="coerce")


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(length).mean()
    loss = (-delta.clip(upper=0)).rolling(length).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    line = ema(close, 12) - ema(close, 26)
    signal = ema(line, 9)
    return line, signal, line - signal


def atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([(df["high"] - df["low"]), (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()], axis=1).max(axis=1)
    return tr.rolling(length).mean()


def vwap(df: pd.DataFrame) -> pd.Series:
    typical = (df["high"] + df["low"] + df["close"]) / 3
    vol = df["volume"].replace(0, np.nan)
    return (typical * vol).cumsum() / vol.cumsum()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for column in ["open", "high", "low", "close", "volume"]:
        if column in out.columns:
            out[column] = _series(out, column)
    out["ema9"] = ema(out["close"], 9)
    out["ema21"] = ema(out["close"], 21)
    out["ema50"] = ema(out["close"], 50)
    out["vwap"] = vwap(out).ffill()
    out["rsi"] = rsi(out["close"])
    out["macd"], out["macd_signal"], out["macd_hist"] = macd(out["close"])
    out["atr"] = atr(out)
    out["vol_avg20"] = out["volume"].rolling(20).mean()
    out["rvol"] = out["volume"] / out["vol_avg20"].replace(0, np.nan)
    out["candle_range"] = out["high"] - out["low"]
    out["range_avg20"] = out["candle_range"].rolling(20).mean()
    return out


def opening_range(df: pd.DataFrame, candles: int = 3) -> tuple[float, float]:
    window = df.head(candles)
    return float(window["high"].max()), float(window["low"].min())


def swing_levels(df: pd.DataFrame, lookback: int = 20) -> tuple[float, float]:
    recent = df.tail(lookback)
    return float(recent["high"].max()), float(recent["low"].min())
