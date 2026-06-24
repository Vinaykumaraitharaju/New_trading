from __future__ import annotations

import pandas as pd

from scanner_brain.core.enums import Bias
from scanner_brain.core.models import SectorAssessment


class SectorStrengthEngine:
    def evaluate(self, quotes: pd.DataFrame, universe: pd.DataFrame) -> dict[str, SectorAssessment]:
        if quotes.empty:
            return {}
        if "sector" in quotes:
            df = quotes.copy()
        else:
            meta = universe[["symbol", "sector"]] if not universe.empty and "sector" in universe else pd.DataFrame(columns=["symbol", "sector"])
            df = quotes.merge(meta, on="symbol", how="left")
        df["sector"] = df.get("sector", "Unknown")
        df["sector"] = df["sector"].fillna("Unknown")
        df["change_pct"] = pd.to_numeric(df.get("change_pct", 0), errors="coerce").fillna(0.0)
        df["volume"] = pd.to_numeric(df.get("volume", 0), errors="coerce").fillna(0.0)
        grouped = df.groupby("sector").agg(
            avg_change=("change_pct", "mean"),
            breadth=("change_pct", lambda s: float((s >= 0).mean() * 100.0)),
            count=("symbol", "count"),
        )
        grouped["score"] = (50.0 + grouped["avg_change"] * 10.0 + (grouped["breadth"] - 50.0) * 0.35).clip(0, 100)
        grouped = grouped.sort_values("score", ascending=False)
        assessments: dict[str, SectorAssessment] = {}
        for rank, (sector, row) in enumerate(grouped.iterrows(), start=1):
            score = float(row["score"])
            bias = Bias.BULLISH if score >= 56 else Bias.BEARISH if score <= 44 else Bias.NEUTRAL
            reasons = [f"{sector} sector score {score:.0f}", f"{row['breadth']:.0f}% sector breadth"]
            assessments[str(sector)] = SectorAssessment(str(sector), score, bias, rank, reasons)
        return assessments
