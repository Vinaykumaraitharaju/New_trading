from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class DetailLayer:
    title: str
    score: float | None = None
    bias: str = "neutral"
    summary: str = ""
    passed: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScoreBreakdown:
    market_score: float
    sector_score: float
    technical_score: float
    pattern_adjustment: float
    news_adjustment: float
    contradiction_penalty: float
    final_score: float
    final_grade: str


@dataclass(frozen=True)
class DetailViewModel:
    item_id: str
    item_type: str
    symbol: str
    name: str
    rank: int
    side: str
    action: str
    ltp: float
    change_pct: float
    confidence: float
    grade: str
    setup_type: str
    sector: str
    scan_time: str
    badges: list[str]
    analyst_explanation: str
    boosted_by: list[str]
    reduced_by: list[str]
    validations_missing: list[str]
    market: DetailLayer
    sector_layer: DetailLayer
    technical: DetailLayer
    pattern: DetailLayer
    news: DetailLayer
    score: ScoreBreakdown
    warnings: list[str]
    invalidation_rules: list[str]
    chart_data: pd.DataFrame
    chart_levels: dict[str, float]
    execution: dict[str, Any]
    prediction: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)
    trade_status: str = "WAIT"
    direction: str = "NEUTRAL"
    decision_headline: str = "WAIT -> NEUTRAL"
    trader_logic: list[str] = field(default_factory=list)
    entry_plan: dict[str, Any] = field(default_factory=dict)
    activation_rules: list[str] = field(default_factory=list)
    confluence: list[str] = field(default_factory=list)
    news_context: list[str] = field(default_factory=list)
    final_summary: str = "Wait for confirmation."
