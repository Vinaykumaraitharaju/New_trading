from __future__ import annotations

from pathlib import Path

import pandas as pd

from data.nse_feed import fetch_nifty500_master, fetch_nse_equity_master
from storage.cache import cache_dataframe

SECTOR_FALLBACK = {
    "RELIANCE": "Energy",
    "TCS": "IT",
    "INFY": "IT",
    "HDFCBANK": "Banking",
    "ICICIBANK": "Banking",
    "SBIN": "Banking",
    "AXISBANK": "Banking",
    "KOTAKBANK": "Banking",
    "LT": "Infrastructure",
    "ITC": "FMCG",
    "HINDUNILVR": "FMCG",
    "BHARTIARTL": "Telecom",
    "TATAMOTORS": "Auto",
    "MARUTI": "Auto",
    "SUNPHARMA": "Pharma",
    "TATASTEEL": "Metals",
    "JSWSTEEL": "Metals",
}

CORE_SYMBOLS = [
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "SBIN", "BHARTIARTL", "LT",
    "ITC", "AXISBANK", "KOTAKBANK", "BAJFINANCE", "HINDUNILVR", "TATAMOTORS", "SUNPHARMA",
    "MARUTI", "TATASTEEL", "JSWSTEEL", "WIPRO", "ULTRACEMCO", "ONGC", "POWERGRID",
    "NTPC", "ADANIENT", "ADANIPORTS", "HCLTECH", "TECHM", "COALINDIA", "M&M", "ASIANPAINT",
    "BAJAJFINSV", "GRASIM", "NESTLEIND", "TITAN", "DIVISLAB", "DRREDDY", "CIPLA",
    "HINDALCO", "EICHERMOT", "HEROMOTOCO", "APOLLOHOSP", "BRITANNIA", "BPCL", "INDUSINDBK",
]


@cache_dataframe(ttl_seconds=24 * 60 * 60)
def load_universe(max_symbols: int = 180, prefer_nifty500: bool = True) -> pd.DataFrame:
    local = Path("storage") / "symbol_master.csv"
    if local.exists():
        df = pd.read_csv(local)
    else:
        try:
            df = fetch_nifty500_master() if prefer_nifty500 else fetch_nse_equity_master()
        except Exception:
            df = pd.DataFrame({"symbol": CORE_SYMBOLS, "name": CORE_SYMBOLS})
    if df.empty:
        df = pd.DataFrame({"symbol": CORE_SYMBOLS, "name": CORE_SYMBOLS})
    df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
    df["name"] = df.get("name", df["symbol"]).astype(str)
    if "sector" not in df.columns:
        df["sector"] = "Unknown"
    df["sector"] = df["sector"].fillna("Unknown").astype(str)
    unknown = df["sector"].eq("Unknown")
    df.loc[unknown, "sector"] = df.loc[unknown, "symbol"].map(SECTOR_FALLBACK).fillna("Unknown")
    df = df[df["symbol"].str.fullmatch(r"[A-Z0-9&-]+", na=False)]
    return df.drop_duplicates("symbol").head(max_symbols).reset_index(drop=True)
