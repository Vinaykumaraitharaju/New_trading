from __future__ import annotations

import pandas as pd

from scanner_brain.core.enums import Bias
from scanner_brain.core.models import MarketContext, MarketRegime, SectorAssessment
from scanner_brain.engines.market_regime_engine import MarketRegimeEngine


class MarketContextEngine:
    """Fast market read for deciding whether longs, shorts, or neither have support."""

    def __init__(self) -> None:
        self.regime_engine = MarketRegimeEngine()

    def evaluate(
        self,
        market_frame: pd.DataFrame,
        breadth_frame: pd.DataFrame,
        sectors: dict[str, SectorAssessment] | None = None,
    ) -> MarketContext:
        regime = self.regime_engine.evaluate(market_frame, breadth_frame)
        reasons = list(regime.reasons)
        risk_state = "risk-on" if regime.score >= 58 else "risk-off" if regime.score <= 42 else "neutral"
        sector_support_map = {
            sector: ("bullish" if item.bias == Bias.BULLISH else "bearish" if item.bias == Bias.BEARISH else "neutral")
            for sector, item in (sectors or {}).items()
        }
        explanation = self._explanation(regime, risk_state, sector_support_map)
        return MarketContext(
            market_bias="bullish" if regime.bias == Bias.BULLISH else "bearish" if regime.bias == Bias.BEARISH else "neutral",
            market_strength=round(regime.score, 1),
            sector_support_map=sector_support_map,
            risk_state=regime.risk_mood or risk_state,
            explanation=explanation,
            reasons=reasons,
            regime=regime,
        )

    @staticmethod
    def _explanation(regime: MarketRegime, risk_state: str, sector_support_map: dict[str, str]) -> str:
        if regime.bias == Bias.BULLISH:
            lead = "Market environment supports longs."
        elif regime.bias == Bias.BEARISH:
            lead = "Market environment supports shorts."
        else:
            lead = "Market environment is mixed; avoid forcing direction."
        strong_sectors = [sector for sector, bias in sector_support_map.items() if bias != "neutral"][:3]
        sector_note = f" Active sectors: {', '.join(strong_sectors)}." if strong_sectors else ""
        return (
            f"{lead} {regime.day_type}. Difficulty {regime.difficulty}. "
            f"Risk state is {regime.risk_mood or risk_state}. {regime.explanation}{sector_note}"
        ).strip()
