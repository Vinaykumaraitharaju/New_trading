from __future__ import annotations

import pandas as pd

from scanner_brain.core.enums import Bias, MarketStateLabel
from scanner_brain.core.models import MarketRegime


class MarketRegimeEngine:
    def evaluate(self, market_frame: pd.DataFrame, breadth_frame: pd.DataFrame) -> MarketRegime:
        reasons: list[str] = []
        index_rows = market_frame[market_frame["is_index"].astype(bool)] if "is_index" in market_frame else pd.DataFrame()
        changes = []
        opens = []
        ranges = []
        for _, row in index_rows.iterrows():
            label = str(row.get("label") or row.get("symbol") or "INDEX")
            change = float(row.get("change_pct", 0) or 0)
            changes.append(change)
            prev_close = float(row.get("prev_close", 0) or 0)
            open_price = float(row.get("open", prev_close) or prev_close)
            high = float(row.get("high", row.get("ltp", 0)) or row.get("ltp", 0) or 0)
            low = float(row.get("low", row.get("ltp", 0)) or row.get("ltp", 0) or 0)
            if prev_close > 0 and open_price > 0:
                opens.append((open_price - prev_close) / prev_close * 100.0)
            if prev_close > 0 and high > 0 and low > 0:
                ranges.append((high - low) / prev_close * 100.0)
            if abs(change) >= 0.15:
                reasons.append(f"{label} {change:+.2f}%")

        breadth_pct = 0.0
        if not breadth_frame.empty and "prev_close" in breadth_frame:
            if "is_index" in breadth_frame:
                stock_mask = ~breadth_frame["is_index"].astype(bool)
            else:
                stock_mask = True
            valid = breadth_frame[(breadth_frame["prev_close"] > 0) & stock_mask]
            if not valid.empty:
                breadth_pct = float((valid["ltp"] >= valid["prev_close"]).mean() * 100.0)
                reasons.append(f"Market breadth {breadth_pct:.0f}% advancing")

        avg_index = sum(changes) / len(changes) if changes else 0.0
        dispersion = max(changes) - min(changes) if len(changes) >= 2 else 0.0
        avg_gap = sum(opens) / len(opens) if opens else 0.0
        avg_range = sum(ranges) / len(ranges) if ranges else abs(avg_index)
        score = 50.0 + avg_index * 18.0 + (breadth_pct - 50.0) * 0.35
        score = max(0.0, min(100.0, score))
        volatility = "High" if avg_range >= 1.1 or dispersion >= 0.8 else "Low" if avg_range <= 0.35 else "Normal"
        gap_environment = "Gap Up" if avg_gap >= 0.35 else "Gap Down" if avg_gap <= -0.35 else "Flat"
        confidence = min(96.0, max(35.0, abs(score - 50.0) * 1.35 + 45.0 - dispersion * 10.0))
        difficulty = "Hard" if 43 <= score <= 57 or dispersion >= 0.9 or volatility == "High" else "Easy" if confidence >= 72 and volatility != "High" else "Medium"
        if volatility == "High" and abs(avg_index) >= 0.55:
            day_type = "News Driven Day"
        elif abs(avg_index) >= 0.7 and breadth_pct >= 60:
            day_type = "Trend Day"
        elif abs(avg_index) >= 0.45 and 43 <= breadth_pct <= 58:
            day_type = "Breakout Day"
        elif 42 <= breadth_pct <= 58 and abs(avg_index) <= 0.25:
            day_type = "Mean Reversion Day"
        else:
            day_type = "Neutral"

        def payload(state: MarketStateLabel, bias: Bias, label: str, fallback: str) -> MarketRegime:
            risk_mood = "risk-on" if bias == Bias.BULLISH else "risk-off" if bias == Bias.BEARISH else "neutral"
            explanation = (
                f"{label}: index average {avg_index:+.2f}%, breadth {breadth_pct:.0f}% advancing, "
                f"volatility {volatility.lower()}, {gap_environment.lower()} environment."
            )
            return MarketRegime(
                state,
                round(score, 1),
                bias,
                reasons or [fallback],
                label=label,
                confidence=round(confidence, 1),
                difficulty=difficulty,
                day_type=day_type,
                volatility_regime=volatility,
                gap_environment=gap_environment,
                risk_mood=risk_mood,
                explanation=explanation,
            )
        if score >= 72:
            return payload(MarketStateLabel.STRONG_BULL, Bias.BULLISH, "Bullish", "Market regime supportive")
        if score >= 58:
            return payload(MarketStateLabel.BULL, Bias.BULLISH, "Bullish", "Market mildly bullish")
        if score <= 28:
            return payload(MarketStateLabel.STRONG_BEAR, Bias.BEARISH, "Bearish", "Market regime weak")
        if score <= 42:
            return payload(MarketStateLabel.BEAR, Bias.BEARISH, "Bearish", "Market mildly bearish")
        label = "Choppy / Avoid" if difficulty == "Hard" else "Neutral"
        return payload(MarketStateLabel.NEUTRAL, Bias.NEUTRAL, label, "Market mixed")
