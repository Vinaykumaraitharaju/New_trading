from __future__ import annotations

import pandas as pd


def compute_sector_strength(scored: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
    if scored.empty:
        return pd.DataFrame(columns=["sector", "sector_score", "sector_trend"])
    merged = scored.merge(universe[["symbol", "sector"]], on="symbol", how="left")
    merged["sector"] = merged["sector"].fillna("Unknown")
    sector = merged.groupby("sector").agg(avg_confidence=("confidence", "mean"), bullish=("direction", lambda s: (s == "LONG").mean()), count=("symbol", "count")).reset_index()
    sector["sector_score"] = sector["avg_confidence"] * 0.65 + sector["bullish"] * 35
    sector["sector_trend"] = sector["bullish"].apply(lambda x: "Bullish" if x >= 0.6 else "Bearish" if x <= 0.4 else "Mixed")
    return sector.sort_values("sector_score", ascending=False)


def sector_modifier(sector: str, direction: str, sector_table: pd.DataFrame) -> tuple[float, str]:
    if sector_table.empty or not sector:
        return 0.0, "Sector data limited"
    row = sector_table[sector_table["sector"].eq(sector)]
    if row.empty:
        return 0.0, "Sector data limited"
    trend = row.iloc[0]["sector_trend"]
    if direction == "LONG" and trend == "Bullish":
        return 5.0, f"{sector} sector supportive"
    if direction == "SHORT" and trend == "Bearish":
        return 5.0, f"{sector} sector supportive"
    if trend == "Mixed":
        return 1.0, f"{sector} sector mixed"
    return -4.0, f"{sector} sector not aligned"
