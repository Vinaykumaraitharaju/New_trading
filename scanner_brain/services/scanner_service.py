from __future__ import annotations

import time
from typing import Iterable

import pandas as pd

from scanner_brain.config.pattern_profiles import PatternProfile
from scanner_brain.config.scoring_profiles import ScoringProfile
from scanner_brain.core.enums import Decision, Grade
from scanner_brain.core.interfaces import NewsProvider
from scanner_brain.core.models import FinalAssessment, PredictionAssessment, ScanResult, ScanStats, SectorAssessment, StockSnapshot, TechnicalAssessment
from scanner_brain.engines.alignment_scoring_engine import AlignmentScoringEngine
from scanner_brain.engines.candidate_filter_engine import CandidateFilterEngine
from scanner_brain.engines.execution_decision_engine import ExecutionDecisionEngine
from scanner_brain.engines.final_selector_engine import FinalSelectorEngine
from scanner_brain.engines.market_context_engine import MarketContextEngine
from scanner_brain.engines.market_regime_engine import MarketRegimeEngine
from scanner_brain.engines.multi_layer_scoring_engine import MultiLayerScoringEngine
from scanner_brain.engines.news_confidence_engine import NullNewsConfidenceEngine
from scanner_brain.engines.pattern_recognition_engine import PatternRecognitionEngine
from scanner_brain.engines.prebreakout_prediction_engine import PreBreakoutPredictionEngine
from scanner_brain.engines.sector_strength_engine import SectorStrengthEngine
from scanner_brain.engines.technical_validation_engine import TechnicalValidationEngine
from scanner_brain.engines.trade_output_engine import TradeOutputEngine


class ScannerBrainService:
    """High-speed validation orchestrator that keeps UI/data providers decoupled."""

    def __init__(
        self,
        profile: ScoringProfile | None = None,
        pattern_profile: PatternProfile | None = None,
        news_provider: NewsProvider | None = None,
    ) -> None:
        self.profile = profile or ScoringProfile()
        self.market_engine = MarketRegimeEngine()
        self.market_context_engine = MarketContextEngine()
        self.sector_engine = SectorStrengthEngine()
        self.filter_engine = CandidateFilterEngine(self.profile.fast_filter)
        self.technical_engine = TechnicalValidationEngine(self.profile)
        self.pattern_engine = PatternRecognitionEngine(pattern_profile or PatternProfile())
        self.prediction_engine = PreBreakoutPredictionEngine()
        self.news_provider = news_provider or NullNewsConfidenceEngine()
        self.scoring_engine = AlignmentScoringEngine(self.profile)
        self.weighted_scoring_engine = MultiLayerScoringEngine(self.profile)
        self.execution_engine = ExecutionDecisionEngine()
        self.final_selector_engine = FinalSelectorEngine(self.profile)
        self.output_engine = TradeOutputEngine()

    def scan(
        self,
        *,
        quotes: pd.DataFrame,
        universe: pd.DataFrame,
        market_frame: pd.DataFrame | None = None,
        side_filter: str = "Both",
        min_score: float | None = None,
    ) -> tuple[pd.DataFrame, pd.DataFrame, ScanResult]:
        started = time.perf_counter()
        if quotes is None or quotes.empty:
            empty_market = self.market_engine.evaluate(pd.DataFrame(), pd.DataFrame())
            result = ScanResult([], [], ScanStats(0, 0, 0, 0, 0.0), empty_market, {}, None)
            return pd.DataFrame(), pd.DataFrame(), result

        normalized = self._normalize_quotes(quotes, universe)
        market_source = market_frame if market_frame is not None else normalized
        market = self.market_engine.evaluate(market_source.copy(), normalized)
        sectors = self.sector_engine.evaluate(normalized, universe)
        market_context = self.market_context_engine.evaluate(market_source.copy(), normalized, sectors)
        shortlist, rejected = self.filter_engine.shortlist(normalized)

        snapshots = {snapshot.symbol: snapshot for snapshot in self._snapshots(shortlist, universe)}
        assessments: list[FinalAssessment] = []
        for snapshot in snapshots.values():
            technical = self.technical_engine.evaluate(snapshot)
            if side_filter == "Bullish only" and technical.side.value == "SHORT":
                rejected.append({"symbol": snapshot.symbol, "reason": "Filtered out by bullish-only side setting"})
                continue
            if side_filter == "Bearish only" and technical.side.value == "LONG":
                rejected.append({"symbol": snapshot.symbol, "reason": "Filtered out by bearish-only side setting"})
                continue
            sector = sectors.get(snapshot.sector)
            pattern = self.pattern_engine.evaluate(snapshot, technical, market, sector)
            news = self.news_provider.assess(snapshot)
            prediction = self.prediction_engine.evaluate(snapshot, market_context, sector, technical, pattern)
            final = self.scoring_engine.grade(snapshot, market, sector, technical, pattern, news)
            execution = self.execution_engine.evaluate(
                snapshot,
                market_context,
                prediction,
                technical,
                stop_loss=final.stop_loss,
                target1=final.target1,
                target2=final.target2,
                rr=final.rr,
            )
            final_payload = dict(final.__dict__)
            adjusted_score = self._confidence_score(final.final_score, prediction, technical, sector)
            adjusted_grade = self._grade_from_confidence(adjusted_score, prediction)
            adjusted_decision = self._decision_from_confidence(adjusted_score, adjusted_grade, prediction, execution)
            final_payload.update(
                final_score=adjusted_score,
                grade=adjusted_grade,
                decision=adjusted_decision,
                prediction_bias=prediction.bias,
                prediction_strength=prediction.strength,
                pre_breakout_status=prediction.status,
                prediction_grade=prediction.grade,
                breakout_probability=prediction.breakout_probability,
                trap_risk=prediction.trap_risk,
                structure_state=prediction.structure_state,
                compression_state=prediction.compression_state,
                pressure_state=prediction.pressure_state,
                vwap_state=prediction.vwap_state,
                volume_state=prediction.volume_state,
                exhaustion_state=prediction.exhaustion_state,
                level_tests=prediction.level_tests,
                level_test_quality=prediction.level_test_quality,
                time_quality=prediction.time_quality,
                prediction_explanation=prediction.explanation,
                key_level=prediction.key_level,
                pressure_side=prediction.pressure_side,
                ideal_scenario=prediction.ideal_scenario,
                invalid_scenario=prediction.invalid_scenario,
                preparation_signals=prediction.preparation_signals,
                prediction_warnings=prediction.warnings,
                execution_state=execution.state,
                execution_grade=execution.grade,
                execution_direction=execution.direction,
                execution_entry_quality=execution.entry_quality,
                avoid_reason=execution.avoid_reason,
                execution_explanation=execution.explanation,
                validation_factors=prediction.validation_factors,
                contradictions=prediction.contradictions,
                snapshot_mode=prediction.snapshot_mode,
                market_bias=market_context.market_bias,
                market_strength=market_context.market_strength,
                risk_state=market_context.risk_state,
                market_explanation=market_context.explanation,
                sector=snapshot.sector,
            )
            final = FinalAssessment(**final_payload)
            final = self.weighted_scoring_engine.apply(
                stock=snapshot,
                final=final,
                market=market_context,
                sector=sector,
                technical=technical,
                pattern=pattern,
                news=news,
                prediction=prediction,
                execution=execution,
            )
            assessments.append(final)

        threshold = self.profile.min_select_score if min_score is None else float(min_score)
        selected, selector_rejected = self.final_selector_engine.select(
            assessments,
            market_context=market_context,
            sectors=sectors,
            min_score=threshold,
        )
        rejected.extend(selector_rejected)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        result = ScanResult(
            setups=selected,
            rejected=rejected,
            stats=ScanStats(
                scanned=len(normalized),
                shortlisted=len(shortlist),
                validated=len(assessments),
                selected=len(selected),
                elapsed_ms=elapsed_ms,
            ),
            market=market,
            sectors=sectors,
            market_context=market_context,
        )
        ranked = self.output_engine.to_dataframe(result, snapshots)
        rejected_df = pd.DataFrame(rejected)
        return ranked, rejected_df, result

    @staticmethod
    def _confidence_score(
        base_score: float,
        prediction: PredictionAssessment,
        technical: TechnicalAssessment,
        sector: SectorAssessment | None,
    ) -> float:
        _ = technical, sector
        score = min(float(base_score), float(prediction.strength))

        clean_setup = (
            not prediction.snapshot_mode
            and prediction.trap_risk == "LOW"
            and prediction.exhaustion_state in {"FRESH", "ACCEPTABLE"}
            and prediction.structure_state in {"HH_HL_BUILDING", "LH_LL_BUILDING", "RANGE_COMPRESSION", "EXPANSION_UP", "EXPANSION_DOWN"}
            and prediction.volume_state in {"DRY_COMPRESSION", "BUILDING", "EXPANDING", "CONFIRMED"}
            and prediction.level_tests >= 2
        )
        if not clean_setup:
            score = min(score, 84.0)
        if prediction.trap_risk == "HIGH" or prediction.status == "EXHAUSTED":
            score = min(score, 54.0)
        elif prediction.exhaustion_state == "EXTENDED" or prediction.volume_state == "WEAK" or prediction.level_tests <= 1:
            score = min(score, 69.0)
        return round(max(0.0, min(100.0, score)), 1)

    @staticmethod
    def _grade_from_confidence(score: float, prediction: PredictionAssessment) -> Grade:
        if score >= 85 and prediction.trap_risk == "LOW" and prediction.status in {"BUILDING", "NEAR_BREAKOUT"}:
            return Grade.A_PLUS
        if score >= 70 and prediction.status in {"BUILDING", "NEAR_BREAKOUT"}:
            return Grade.A
        if score >= 55 and prediction.status in {"BUILDING", "NEAR_BREAKOUT"}:
            return Grade.B
        if score >= 45:
            return Grade.C
        return Grade.REJECT

    @staticmethod
    def _decision_from_confidence(score: float, grade: Grade, prediction: PredictionAssessment, execution) -> Decision:
        if score < 55 or grade == Grade.REJECT or prediction.status in {"NO_SETUP", "EXHAUSTED"}:
            return Decision.REJECTED
        if execution.state == "TRADE" and grade in {Grade.A_PLUS, Grade.A, Grade.B}:
            return Decision.SELECTED
        return Decision.WATCHLIST

    @staticmethod
    def _normalize_quotes(quotes: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
        df = quotes.copy()
        df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
        for col in ["ltp", "open", "high", "low", "prev_close", "volume", "change_pct"]:
            if col not in df:
                df[col] = 0.0
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        if "raw" not in df:
            df["raw"] = [{} for _ in range(len(df))]
        if "sector" not in df or "name" not in df:
            meta_cols = [col for col in ["symbol", "name", "sector"] if col in universe]
            meta = universe[meta_cols].copy() if meta_cols else pd.DataFrame(columns=["symbol", "name", "sector"])
            df = df.merge(meta, on="symbol", how="left", suffixes=("", "_meta"))
            if "name_meta" in df:
                df["name"] = df.get("name", df["symbol"]).fillna(df["name_meta"])
            if "sector_meta" in df:
                df["sector"] = df.get("sector", "Unknown").fillna(df["sector_meta"])
        df["name"] = df.get("name", df["symbol"]).fillna(df["symbol"]).astype(str)
        df["sector"] = df.get("sector", "Unknown").fillna("Unknown").astype(str)
        if "is_index" in df:
            df = df[(df["ltp"] > 0) & (~df["is_index"].astype(bool))]
        else:
            df = df[df["ltp"] > 0]
        return df.drop_duplicates("symbol")

    @staticmethod
    def _snapshots(quotes: pd.DataFrame, universe: pd.DataFrame) -> Iterable[StockSnapshot]:
        for _, row in quotes.iterrows():
            raw = row.get("raw")
            raw_payload = dict(raw) if isinstance(raw, dict) else {}
            liquidity_mode = row.get("liquidity_mode")
            if liquidity_mode:
                raw_payload["liquidity_mode"] = str(liquidity_mode)
            for source_col in ("vwap", "average_price", "avgPrice"):
                if source_col in row and row.get(source_col):
                    raw_payload[source_col] = row.get(source_col)
            yield StockSnapshot(
                symbol=str(row.get("symbol", "")).upper(),
                name=str(row.get("name") or row.get("symbol") or ""),
                sector=str(row.get("sector") or "Unknown"),
                ltp=float(row.get("ltp", 0) or 0),
                open=float(row.get("open", 0) or 0),
                high=float(row.get("high", 0) or 0),
                low=float(row.get("low", 0) or 0),
                prev_close=float(row.get("prev_close", 0) or 0),
                volume=float(row.get("volume", 0) or 0),
                change_pct=float(row.get("change_pct", 0) or 0),
                raw=raw_payload,
            )
