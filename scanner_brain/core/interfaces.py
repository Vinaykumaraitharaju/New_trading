from __future__ import annotations

from typing import Protocol

from scanner_brain.core.models import NewsAssessment, StockSnapshot


class NewsProvider(Protocol):
    def assess(self, snapshot: StockSnapshot) -> NewsAssessment:
        """Return an optional stock/event confidence adjustment."""
