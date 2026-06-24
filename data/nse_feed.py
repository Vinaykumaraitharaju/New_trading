from __future__ import annotations

from io import StringIO

import pandas as pd
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

NSE_EQUITY_CSV = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
NIFTY_500_CSV = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.7, min=1, max=4), reraise=True)
def _get_csv(url: str) -> pd.DataFrame:
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*", "Referer": "https://www.nseindia.com/"}
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    return pd.read_csv(StringIO(response.text))


def fetch_nse_equity_master() -> pd.DataFrame:
    df = _get_csv(NSE_EQUITY_CSV)
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    if "symbol" not in df:
        return pd.DataFrame(columns=["symbol", "name", "series"])
    name_col = "name_of_company" if "name_of_company" in df else "company_name"
    out = pd.DataFrame({"symbol": df["symbol"].astype(str).str.upper().str.strip(), "name": df.get(name_col, df["symbol"]).astype(str).str.strip(), "series": df.get("series", "EQ")})
    out = out[out["series"].astype(str).str.upper().eq("EQ")]
    return out.drop_duplicates("symbol").reset_index(drop=True)


def fetch_nifty500_master() -> pd.DataFrame:
    df = _get_csv(NIFTY_500_CSV)
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    symbol_col = "symbol" if "symbol" in df else df.columns[0]
    company_col = "company_name" if "company_name" in df else symbol_col
    industry_col = "industry" if "industry" in df else None
    out = pd.DataFrame({"symbol": df[symbol_col].astype(str).str.upper().str.strip(), "name": df[company_col].astype(str).str.strip(), "sector": df[industry_col].astype(str).str.strip() if industry_col else "Unknown"})
    return out.drop_duplicates("symbol").reset_index(drop=True)
