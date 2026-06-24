from __future__ import annotations

import pandas as pd

from analysis.indicators import add_indicators
from data.source_router import SourceRouter

INDEX_SYMBOLS = {"NIFTY": "^NSEI", "BANKNIFTY": "^NSEBANK", "SENSEX": "^BSESN"}


def _index_snapshot(name: str, df: pd.DataFrame) -> dict:
    if df.empty or len(df) < 25:
        return {"name": name, "value": None, "change_pct": None, "trend": "Unknown", "interpretation": "Data unavailable", "available": False}
    ind = add_indicators(df).dropna(subset=["ema21", "vwap"])
    if ind.empty:
        return {"name": name, "value": None, "change_pct": None, "trend": "Unknown", "interpretation": "Data unavailable", "available": False}
    last = ind.iloc[-1]
    first = ind.iloc[0]
    change_pct = ((last["close"] - first["open"]) / first["open"]) * 100 if first["open"] else 0
    bullish = last["close"] > last["vwap"] and last["ema9"] > last["ema21"]
    bearish = last["close"] < last["vwap"] and last["ema9"] < last["ema21"]
    trend = "Bullish" if bullish else "Bearish" if bearish else "Neutral"
    return {"name": name, "value": float(last["close"]), "change_pct": float(change_pct), "trend": trend, "interpretation": "Supportive for longs" if bullish else "Supportive for shorts" if bearish else "Mixed tape", "available": True}


def fetch_market_context(router: SourceRouter, interval: str = "5m") -> dict:
    indices = {name: _index_snapshot(name, router.fetch_index(symbol, interval=interval)) for name, symbol in INDEX_SYMBOLS.items()}
    bullish_count = sum(1 for v in indices.values() if v["trend"] == "Bullish")
    bearish_count = sum(1 for v in indices.values() if v["trend"] == "Bearish")
    available_count = sum(1 for v in indices.values() if v.get("available"))
    bias = "Bullish" if bullish_count > bearish_count else "Bearish" if bearish_count > bullish_count else "Neutral"
    return {"indices": indices, "bias": bias, "available_count": available_count}


def breadth_from_shortlist(shortlist_df: pd.DataFrame) -> dict:
    if shortlist_df.empty:
        return {"advancing": 0, "declining": 0, "breadth_pct": 0.0, "label": "Unknown"}
    advancing = int((shortlist_df["near_high"] >= shortlist_df["near_low"]).sum())
    declining = int(len(shortlist_df) - advancing)
    pct = (advancing / max(len(shortlist_df), 1)) * 100
    label = "Positive" if pct >= 58 else "Negative" if pct <= 42 else "Mixed"
    return {"advancing": advancing, "declining": declining, "breadth_pct": pct, "label": label}
