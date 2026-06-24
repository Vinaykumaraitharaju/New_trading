from __future__ import annotations

from scanner_brain.core.enums import Bias
from scanner_brain.core.models import NewsAssessment, StockSnapshot


class NullNewsConfidenceEngine:
    """Version-1 no-op news layer. Replace with a provider without touching scoring."""

    def assess(self, snapshot: StockSnapshot) -> NewsAssessment:
        return NewsAssessment(
            bias=Bias.NEUTRAL,
            score_adjustment=0.0,
            confidence=0.0,
            reasons=["News layer not connected; treated as neutral"],
        )
