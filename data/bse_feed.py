from __future__ import annotations

import pandas as pd


def fetch_bse_master() -> pd.DataFrame:
    """Optional extension point for BSE code-to-symbol mapping."""
    return pd.DataFrame(columns=["symbol", "name", "sector", "exchange"])
