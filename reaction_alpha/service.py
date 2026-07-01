from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, time as dt_time, timedelta
import logging
import random
import threading
import time
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from auth import build_router
from data.kotak_neo_feed import KotakLiveTick
from scanner.universe import load_universe
from scanner_brain import ScannerBrainService
from scanner_brain.core.models import FinalAssessment, ScanResult, ScanStats

from .config import ReactionAlphaConfig, classify_setup_profile, setup_profile_min_score, setup_profile_score_adjustment
from .engines import (
    EventDetectionEngine,
    OrderFlowEngine,
    PatternEngine,
    ReactionEngine,
    RegimeEngine,
    SignalEngine,
    SupportResistanceEngine,
    UnifiedScoringEngine,
    MarketStructureEngine,
    VolumeEngine,
    VolatilityEngine,
    VwapEngine,
)
from .metrics import mean, safe_float
from .models import ComponentScore, TickData, TradeSignal
from .paper_trade import PaperTradeBook
from .probability import OutcomeTracker
from .state import InMemoryMarketStore, SymbolState
from .trade_levels import build_trade_levels, resolve_trade_state
from .engines.scoring_engine import UnifiedScore

log = logging.getLogger(__name__)

INDEX_DEFS = [
    {"label": "NIFTY", "symbol": "NIFTY", "instrument_token": "26000", "exchange_segment": "nse_cm", "is_index": True},
    {"label": "BANKNIFTY", "symbol": "BANKNIFTY", "instrument_token": "26009", "exchange_segment": "nse_cm", "is_index": True},
    {"label": "SENSEX", "symbol": "SENSEX", "instrument_token": "1", "exchange_segment": "bse_cm", "is_index": True},
]


class BroadcastHub:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queues: set[asyncio.Queue] = set()
        self._lock = threading.Lock()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=32)
        with self._lock:
            self._queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self._queues.discard(queue)

    def publish(self, payload: dict[str, Any]) -> None:
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._fanout, payload)

    def _fanout(self, payload: dict[str, Any]) -> None:
        for queue in list(self._queues):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(payload)


class ReactionAlphaService:
    def __init__(self, config: ReactionAlphaConfig | None = None) -> None:
        self.config = config or ReactionAlphaConfig()
        self.store = InMemoryMarketStore(self.config.tick_buffer_size, self.config.candle_buffer_size)
        self.event_engine = EventDetectionEngine(self.config)
        self.reaction_engine = ReactionEngine(self.config)
        self.structure_engine = MarketStructureEngine()
        self.sr_engine = SupportResistanceEngine()
        self.pattern_engine = PatternEngine()
        self.volume_engine = VolumeEngine()
        self.orderflow_engine = OrderFlowEngine()
        self.vwap_engine = VwapEngine()
        self.volatility_engine = VolatilityEngine()
        self.regime_engine = RegimeEngine()
        self.scoring_engine = UnifiedScoringEngine(self.config.elite_threshold, self.config.strong_threshold)
        self.signal_engine = SignalEngine()
        self.outcome_tracker = OutcomeTracker()
        self.paper_trades = PaperTradeBook(self.config)
        self.hub = BroadcastHub()
        self._router = None if self.config.simulated else build_router()
        self._scanner = ScannerBrainService()
        self._pretrade_cache: dict[str, Any] | None = None
        self._pretrade_cache_ts = 0.0
        self._subscriptions: list[dict[str, str]] = []
        self._signals: dict[str, TradeSignal] = {}
        self._indices = [dict(item) for item in INDEX_DEFS]
        self._equity_symbols: list[str] = list(self.config.symbols)
        try:
            universe = load_universe(max_symbols=max(self.config.dynamic_scan_universe, 240))
            self._sector_map = {
                str(row.get("symbol") or "").upper().strip(): str(row.get("sector") or "Unknown").strip() or "Unknown"
                for row in universe.to_dict("records")
            }
        except Exception:
            self._sector_map = {}
        self._last_broadcast_ts = 0.0
        self._lock = threading.RLock()
        self._sim_thread: threading.Thread | None = None
        self._live_init_thread: threading.Thread | None = None
        self._selection_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._live_status = "idle"
        self._live_status_detail = "Waiting to initialize live feed"

    async def startup(self) -> None:
        self.hub.bind_loop(asyncio.get_running_loop())
        if self.config.simulated:
            self._live_status = "simulated"
            self._live_status_detail = "Simulation engine active"
            self._start_simulation()
        else:
            self._start_live_feed_async()

    async def shutdown(self) -> None:
        self._stop_event.set()
        if self._router is not None:
            try:
                self._router.stop_live_feed()
            except Exception:
                log.exception("Failed to stop live feed cleanly")

    def _start_live_feed(self) -> None:
        if self._router is None:
            return
        auth = self._router.validate_auth()
        if not auth.get("ok"):
            raise RuntimeError(f"Kotak auth failed: {auth.get('message')}")
        if self.config.dynamic_universe_enabled:
            self._equity_symbols = self._select_dynamic_symbols()
        else:
            self._equity_symbols = list(self.config.symbols)
        self._apply_live_subscriptions()
        if self.config.dynamic_universe_enabled:
            self._start_selection_refresh()

    def _start_live_feed_async(self) -> None:
        if self._router is None:
            self._live_status = "disabled"
            self._live_status_detail = "Live router unavailable"
            return
        if self._live_init_thread is not None and self._live_init_thread.is_alive():
            return

        def runner() -> None:
            self._live_status = "connecting"
            self._live_status_detail = "Connecting to Kotak live feed"
            try:
                self._start_live_feed()
            except Exception as exc:
                self._live_status = "error"
                self._live_status_detail = str(exc)
                log.exception("Live feed initialization failed")
                return
            self._live_status = "live"
            tracked = len(self._subscriptions) if self._subscriptions else len(self._equity_symbols)
            self._live_status_detail = f"Live feed active for {tracked} instruments"

        self._live_init_thread = threading.Thread(target=runner, name="reaction-alpha-live-init", daemon=True)
        self._live_init_thread.start()

    def pretrade_scan(self, *, force: bool = False) -> dict[str, Any]:
        now = time.time()
        if (
            not force
            and self._pretrade_cache is not None
            and now - self._pretrade_cache_ts <= max(self.config.pretrade_cache_sec, 1.0)
        ):
            return self._pretrade_cache

        if self.config.simulated or self._router is None:
            payload = self._pretrade_scan_from_store()
        else:
            payload = self._pretrade_scan_from_router()

        self._pretrade_cache = payload
        self._pretrade_cache_ts = now
        return payload

    def _pretrade_scan_from_router(self) -> dict[str, Any]:
        assert self._router is not None
        universe = load_universe(max_symbols=max(self.config.pretrade_scan_universe, len(self.config.symbols)))
        symbols = universe["symbol"].astype(str).str.upper().head(self.config.pretrade_scan_universe).tolist()
        quotes = self._router.fetch_quote_snapshot(symbols, batch_size=50)
        quotes = self._enrich_pretrade_quotes(quotes, universe)
        market_frame = self._market_frame_from_router()
        return self._build_pretrade_payload(quotes=quotes, universe=universe, market_frame=market_frame, source="Kotak Neo snapshot")

    def _pretrade_scan_from_store(self) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        for state in self.store.states():
            price = state.latest_price()
            if price <= 0:
                continue
            open_price = state.candles_1m[0].open if state.candles_1m else state.previous_close or price
            vwap = state.ticks[-1].vwap if state.ticks and state.ticks[-1].vwap else state.volume_cluster_price()
            rows.append(
                {
                    "symbol": state.symbol,
                    "ltp": price,
                    "open": open_price,
                    "high": state.day_high or price,
                    "low": state.day_low or price,
                    "prev_close": state.previous_close or open_price or price,
                    "volume": state.cumulative_volume,
                    "raw": {"vwap": vwap, "candles": self._pretrade_candle_frame(state)},
                }
            )
        quotes = pd.DataFrame(rows)
        universe = load_universe(max_symbols=max(self.config.pretrade_scan_universe, len(rows), 20))
        quotes = self._enrich_pretrade_quotes(quotes, universe)
        market_frame = self._market_frame_from_store()
        return self._build_pretrade_payload(quotes=quotes, universe=universe, market_frame=market_frame, source="runtime store")

    def _pretrade_all_assessments(
        self,
        *,
        quotes: pd.DataFrame,
        universe: pd.DataFrame,
        market_frame: pd.DataFrame,
    ) -> tuple[list[FinalAssessment], list[dict[str, str]], Any, Any, Any, dict[str, Any]]:
        normalized = self._scanner._normalize_quotes(quotes, universe)
        market = self._scanner.market_engine.evaluate(market_frame.copy() if market_frame is not None else pd.DataFrame(), normalized)
        sectors = self._scanner.sector_engine.evaluate(normalized, universe)
        market_context = self._scanner.market_context_engine.evaluate(market_frame.copy() if market_frame is not None else pd.DataFrame(), normalized, sectors)
        shortlist, rejected = self._scanner.filter_engine.shortlist(normalized)
        snapshots = {snapshot.symbol: snapshot for snapshot in self._scanner._snapshots(shortlist, universe)}
        assessments: list[Any] = []
        for snapshot in snapshots.values():
            technical = self._scanner.technical_engine.evaluate(snapshot)
            sector = sectors.get(snapshot.sector)
            pattern = self._scanner.pattern_engine.evaluate(snapshot, technical, market, sector)
            news = self._scanner.news_provider.assess(snapshot)
            prediction = self._scanner.prediction_engine.evaluate(snapshot, market_context, sector, technical, pattern)
            final = self._scanner.scoring_engine.grade(snapshot, market, sector, technical, pattern, news)
            execution = self._scanner.execution_engine.evaluate(
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
            adjusted_score = self._scanner._confidence_score(final.final_score, prediction, technical, sector)
            adjusted_grade = self._scanner._grade_from_confidence(adjusted_score, prediction)
            adjusted_decision = self._scanner._decision_from_confidence(adjusted_score, adjusted_grade, prediction, execution)
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
            final = self._scanner.weighted_scoring_engine.apply(
                stock=snapshot,
                final=FinalAssessment(**final_payload),
                market=market_context,
                sector=sector,
                technical=technical,
                pattern=pattern,
                news=news,
                prediction=prediction,
                execution=execution,
            )
            assessments.append(final)
        return assessments, rejected, market, sectors, market_context, snapshots

    def _market_frame_from_router(self) -> pd.DataFrame:
        if self._router is None:
            return pd.DataFrame()
        try:
            snapshot = self._router.kotak.quote_token_snapshot(
                {
                    item["symbol"]: {
                        "instrument_token": str(item["instrument_token"]),
                        "exchange_segment": str(item["exchange_segment"]),
                    }
                    for item in self._indices
                }
            )
        except Exception:
            log.exception("Unable to fetch pre-trade index context")
            snapshot = {}
        rows = []
        for item in self._indices:
            symbol = str(item["symbol"]).upper()
            row = dict(snapshot.get(symbol, {}))
            if row:
                row["symbol"] = symbol
                row["label"] = symbol
                row["is_index"] = True
                rows.append(row)
        return pd.DataFrame(rows)

    def _market_frame_from_store(self) -> pd.DataFrame:
        rows = []
        for item in self._indices:
            symbol = str(item["symbol"]).upper()
            state = self.store.get(symbol)
            price = state.latest_price()
            if price <= 0:
                continue
            open_price = state.candles_1m[0].open if state.candles_1m else state.previous_close or price
            vwap = state.ticks[-1].vwap if state.ticks and state.ticks[-1].vwap else state.volume_cluster_price()
            rows.append(
                {
                    "symbol": symbol,
                    "label": symbol,
                    "is_index": True,
                    "ltp": price,
                    "open": open_price,
                    "high": state.day_high or price,
                    "low": state.day_low or price,
                    "prev_close": state.previous_close or open_price or price,
                    "volume": state.cumulative_volume,
                    "raw": {"vwap": vwap, "candles": self._pretrade_candle_frame(state)},
                }
            )
        return pd.DataFrame(rows)

    def _enrich_pretrade_quotes(self, quotes: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
        if quotes is None or quotes.empty:
            return pd.DataFrame()
        df = quotes.copy()
        df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
        for col in ["ltp", "open", "high", "low", "prev_close", "volume"]:
            if col not in df:
                df[col] = 0.0
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        if "change_pct" not in df:
            df["change_pct"] = ((df["ltp"] - df["prev_close"]) / df["prev_close"].clip(lower=0.01)) * 100.0
        meta = universe[[col for col in ["symbol", "name", "sector"] if col in universe]].copy()
        if not meta.empty:
            meta["symbol"] = meta["symbol"].astype(str).str.upper().str.strip()
            df = df.merge(meta.drop_duplicates("symbol"), on="symbol", how="left", suffixes=("", "_meta"))
        df["name"] = df.get("name", df["symbol"]).fillna(df["symbol"]).astype(str)
        df["sector"] = df.get("sector", "Unknown").fillna("Unknown").astype(str)
        return df.drop_duplicates("symbol")

    @staticmethod
    def _pretrade_candle_frame(state: SymbolState) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "datetime": candle.timestamp,
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                    "vwap": candle.vwap,
                }
                for candle in state.candles_1m
            ]
        )

    def _build_pretrade_payload(
        self,
        *,
        quotes: pd.DataFrame,
        universe: pd.DataFrame,
        market_frame: pd.DataFrame,
        source: str,
    ) -> dict[str, Any]:
        if quotes is None or quotes.empty:
            return {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "source": source,
                "status": "empty",
                "message": "No quote data available for pre-trade scanning.",
                "market": {},
                "setups": [],
                "watchlist": [],
                "rejected": [],
                "stats": {"scanned": 0, "selected": 0, "elapsed_ms": 0.0},
            }
        started = time.perf_counter()
        assessments, rejected, market, sectors, market_context, snapshots = self._pretrade_all_assessments(
            quotes=quotes,
            universe=universe,
            market_frame=market_frame,
        )
        scored_assessments = [
            self._scanner.final_selector_engine._score_assessment(
                item,
                market_context=market_context,
                sector=sectors.get(item.sector),
            )
            for item in assessments
        ]
        ordered = sorted(scored_assessments, key=self._scanner.final_selector_engine._ranking_key, reverse=True)
        ranked_assessments = self._scanner.final_selector_engine._differentiate_ranked_list(ordered[: self.config.top_n])
        synthetic_result = ScanResult(
            setups=ranked_assessments,
            rejected=rejected,
            stats=ScanStats(
                scanned=int(len(quotes.index)),
                shortlisted=int(len(snapshots)),
                validated=int(len(assessments)),
                selected=int(len(ranked_assessments)),
                elapsed_ms=round((time.perf_counter() - started) * 1000.0, 1),
            ),
            market=market,
            sectors=sectors,
            market_context=market_context,
        )
        ranked = self._scanner.output_engine.to_dataframe(synthetic_result, snapshots)
        setups = ranked.head(8).to_dict("records") if not ranked.empty else []
        for setup in setups:
            self._enrich_pretrade_opportunity(setup)
            setup["scanner_band"] = self._pretrade_band(setup)
            setup["scanner_label"] = self._pretrade_label(setup)
        band_priority = {
            "trade-ready": 0,
            "near-trigger": 1,
            "high-edge watch": 2,
            "watchlist": 3,
            "avoid": 4,
        }
        setups.sort(
            key=lambda item: (
                band_priority.get(str(item.get("scanner_band") or "").lower(), 9),
                -safe_float(item.get("relative_opportunity_score") or item.get("final_selector_score") or item.get("confidence") or 0.0),
                str(item.get("symbol") or ""),
            )
        )
        band_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for setup in setups:
            band_rows[str(setup.get("scanner_band") or "watchlist").lower()].append(setup)
        rejected_rows = rejected[:20] if rejected else []
        sector_rows = sorted(
            [
                {
                    "sector": sector,
                    "score": round(item.score, 1),
                    "bias": item.bias.value,
                    "rank": item.rank,
                    "reasons": item.reasons[:3],
                }
                for sector, item in synthetic_result.sectors.items()
            ],
            key=lambda item: item["rank"],
        )[:8]
        market = synthetic_result.market_context
        market_payload = {
            "bias": market.market_bias if market else synthetic_result.market.bias.value,
            "strength": round(market.market_strength, 1) if market else round(synthetic_result.market.score, 1),
            "risk_state": market.risk_state if market else synthetic_result.market.risk_mood,
            "regime": synthetic_result.market.label,
            "day_type": synthetic_result.market.day_type,
            "volatility": synthetic_result.market.volatility_regime,
            "explanation": market.explanation if market else synthetic_result.market.explanation,
            "reasons": (market.reasons if market else synthetic_result.market.reasons)[:6],
        }
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source": source,
            "status": "ok",
            "message": (
                f"Scanned {synthetic_result.stats.scanned} symbols and surfaced "
                f"{len(band_rows.get('trade-ready', []))} trade-ready, "
                f"{len(band_rows.get('near-trigger', []))} near-trigger, and "
                f"{len(band_rows.get('high-edge watch', []))} high-edge watch setups."
            ),
            "market": market_payload,
            "sectors": sector_rows,
            "setups": setups,
            "watchlist": [
                item
                for item in setups
                if str(item.get("scanner_band") or "").lower() in {"trade-ready", "near-trigger", "high-edge watch"}
            ],
            "bands": {
                "trade_ready": band_rows.get("trade-ready", []),
                "near_trigger": band_rows.get("near-trigger", []),
                "high_edge_watch": band_rows.get("high-edge watch", []),
                "watchlist": band_rows.get("watchlist", []),
                "avoid": band_rows.get("avoid", []),
            },
            "band_counts": {
                "trade_ready": len(band_rows.get("trade-ready", [])),
                "near_trigger": len(band_rows.get("near-trigger", [])),
                "high_edge_watch": len(band_rows.get("high-edge watch", [])),
                "watchlist": len(band_rows.get("watchlist", [])),
                "avoid": len(band_rows.get("avoid", [])),
            },
            "rejected": rejected_rows,
            "stats": {
                "scanned": synthetic_result.stats.scanned,
                "shortlisted": synthetic_result.stats.shortlisted,
                "validated": synthetic_result.stats.validated,
                "selected": synthetic_result.stats.selected,
                "elapsed_ms": round(synthetic_result.stats.elapsed_ms, 1),
            },
        }

    def _enrich_pretrade_opportunity(self, setup: dict[str, Any]) -> None:
        side = str(setup.get("side") or setup.get("direction") or "").upper()
        ltp = safe_float(setup.get("ltp"))
        entry = safe_float(setup.get("entry_high") if side == "LONG" else setup.get("entry_low"))
        target1 = safe_float(setup.get("target1"))
        stop = safe_float(setup.get("stop_loss"))
        if ltp <= 0:
            return

        direction = 1.0 if side != "SHORT" else -1.0
        trigger_gap = direction * (entry - ltp)
        target_gap = direction * (target1 - ltp)
        stop_gap = direction * (ltp - stop)
        trigger_pct = (trigger_gap / ltp) * 100.0 if entry > 0 else 99.0
        target_pct = (target_gap / ltp) * 100.0 if target1 > 0 else 0.0
        risk_pct = (stop_gap / ltp) * 100.0 if stop > 0 else 0.0

        missing: list[str] = []
        volume_state = str(setup.get("volume_state") or "").upper()
        trap_risk = str(setup.get("trap_risk") or "").upper()
        structure = str(setup.get("structure_state") or "").upper()
        if "WEAK" in volume_state:
            missing.append("Volume expansion before trigger")
        if trap_risk in {"MEDIUM", "HIGH"}:
            missing.append(f"Trap risk must reduce from {trap_risk.lower()}")
        if "CHOPPY" in structure:
            missing.append("Cleaner structure or acceptance near level")
        if trigger_pct > 0.8:
            missing.append("Price is still far from trigger")
        if target_pct <= 0:
            missing.append("Target has already been reached or crossed")

        phase = "WAIT"
        if target_pct <= 0:
            phase = "TARGET_PASSED"
        elif trigger_pct <= 0:
            phase = "TRIGGERED"
        elif trigger_pct <= 0.25 and target_pct >= risk_pct:
            phase = "PRE_TRIGGER_READY"
        elif trigger_pct <= 0.8:
            phase = "BUILDING_BEFORE_TARGET"

        setup["trigger_distance_pct"] = round(trigger_pct, 2)
        setup["target1_distance_pct"] = round(target_pct, 2)
        setup["risk_distance_pct"] = round(max(risk_pct, 0.0), 2)
        setup["opportunity_phase"] = phase
        intelligence = self._market_intelligence(setup, trigger_pct, target_pct, risk_pct)
        missing.extend(intelligence["missing"])
        setup.update({key: value for key, value in intelligence.items() if key != "missing"})
        setup["missing_confirmation"] = list(dict.fromkeys(missing))[:8]
        setup["target_ahead_note"] = (
            f"{phase}: trigger {trigger_pct:.2f}% away, T1 {target_pct:.2f}% away, risk {max(risk_pct, 0.0):.2f}%."
        )

    def _market_intelligence(self, setup: dict[str, Any], trigger_pct: float, target_pct: float, risk_pct: float) -> dict[str, Any]:
        pressure_state = str(setup.get("pressure_state") or "").upper()
        volume_state = str(setup.get("volume_state") or "").upper()
        vwap_state = str(setup.get("vwap_state") or "").upper()
        trap_risk = str(setup.get("trap_risk") or "").upper()
        structure = str(setup.get("structure_state") or "").upper()
        compression = str(setup.get("compression_state") or "").upper()
        sector = str(setup.get("sector") or "Unknown")
        market_bias = str(setup.get("market_bias") or "neutral").lower()
        direction = str(setup.get("side") or setup.get("direction") or "").upper()

        demand_supply = 50
        demand_supply += {"BUYER_PRESSURE": 18, "SELLER_PRESSURE": 18, "MOMENTUM": 22, "ABSORPTION": 16}.get(pressure_state, 0)
        demand_supply += {"CONFIRMED": 15, "VOLUME_CONFIRMED": 15, "EXPANDING": 11, "BUILDING": 8, "DRY_COMPRESSION": 5, "WEAK": -12, "WEAK_VOLUME": -12}.get(volume_state, 0)
        demand_supply += {"ABOVE_HOLD": 10, "BELOW_REJECT": 10, "VWAP_RECLAIMED": 8, "VWAP_CHOPPY": -8, "EXTENDED": -12}.get(vwap_state, 0)
        demand_supply = max(0, min(100, demand_supply))

        level_tests = int(safe_float(setup.get("level_tests")))
        prebreakout_memory = 35
        prebreakout_memory += min(level_tests, 4) * 10
        prebreakout_memory += 16 if str(setup.get("level_test_quality") or "").upper() == "TIGHT" else 5 if level_tests >= 2 else 0
        prebreakout_memory += {"TIGHT": 16, "MODERATE": 9}.get(compression, 0)
        prebreakout_memory += 8 if volume_state in {"BUILDING", "EXPANDING", "CONFIRMED", "VOLUME_CONFIRMED"} else -8 if "WEAK" in volume_state else 0
        prebreakout_memory = max(0, min(100, prebreakout_memory))

        confirmation_quality = "REAL_ACCUMULATION"
        missing: list[str] = []
        if trap_risk == "HIGH":
            confirmation_quality = "TRAP_SETUP"
        elif str(setup.get("entry_type") or "").upper() == "CHASING" or str(setup.get("exhaustion_state") or "").upper() in {"EXTENDED", "OVEREXTENDED", "CHASE_RISK_HIGH"}:
            confirmation_quality = "LATE_CHASING_MOVE"
        elif "WEAK" in volume_state:
            confirmation_quality = "LOW_VOLUME_BREAKOUT_RISK"
        elif "CHOPPY" in structure:
            confirmation_quality = "FAKE_BREAKOUT_RISK"
        elif demand_supply >= 72 and prebreakout_memory >= 65 and trap_risk == "LOW":
            confirmation_quality = "REAL_ACCUMULATION"

        if demand_supply < 65:
            missing.append("Demand/supply pressure must strengthen")
        if prebreakout_memory < 60:
            missing.append("More level memory or tighter repeated tests needed")
        if confirmation_quality != "REAL_ACCUMULATION":
            missing.append(f"Confirmation quality is {confirmation_quality.lower().replace('_', ' ')}")

        sector_score = 50
        if sector and sector != "Unknown":
            sector_score += 8
        if (direction == "LONG" and market_bias == "bullish") or (direction == "SHORT" and market_bias == "bearish"):
            sector_score += 12
        elif market_bias not in {"neutral", ""}:
            sector_score -= 10
        sector_score = max(0, min(100, sector_score))

        catalyst_confidence = self._catalyst_confidence(setup)
        target_probability = self._target_ahead_probability(
            setup,
            demand_supply=demand_supply,
            prebreakout_memory=prebreakout_memory,
            sector_score=sector_score,
            catalyst_confidence=catalyst_confidence,
            trigger_pct=trigger_pct,
            target_pct=target_pct,
            risk_pct=risk_pct,
        )
        relative_opportunity = self._relative_opportunity_score(
            setup,
            demand_supply=demand_supply,
            prebreakout_memory=prebreakout_memory,
            sector_score=sector_score,
            target_probability=target_probability,
            trigger_pct=trigger_pct,
            target_pct=target_pct,
            risk_pct=risk_pct,
        )

        learning = self._stock_learning_hint(setup)
        return {
            "demand_supply_score": round(demand_supply, 1),
            "prebreakout_memory_score": round(prebreakout_memory, 1),
            "confirmation_quality": confirmation_quality,
            "sector_market_score": round(sector_score, 1),
            "catalyst_confidence": round(catalyst_confidence, 1),
            "target_ahead_probability": round(target_probability, 1),
            "expected_time_to_t1": self._expected_time_to_t1(setup, target_pct),
            "relative_opportunity_score": round(relative_opportunity, 1),
            "learning_hint": learning,
            "market_intelligence": [
                f"Demand/supply {demand_supply:.0f}/100 from pressure {pressure_state}, volume {volume_state}, VWAP {vwap_state}.",
                f"Pre-breakout memory {prebreakout_memory:.0f}/100 from {level_tests} tests, {compression} compression.",
                f"Confirmation quality: {confirmation_quality.replace('_', ' ').title()}.",
                f"Target-ahead probability {target_probability:.0f}/100; relative opportunity {relative_opportunity:.0f}/100.",
                learning,
            ],
            "missing": missing,
        }

    @staticmethod
    def _catalyst_confidence(setup: dict[str, Any]) -> float:
        text = " ".join(str(item) for item in [
            setup.get("reaction_profile_note", ""),
            setup.get("remarks", ""),
            *(setup.get("news_context") or []),
            *(setup.get("reasons") or []),
        ]).lower()
        keywords = ("result", "earnings", "order", "approval", "management", "guidance", "regulatory", "deal", "policy", "commodity", "global", "news")
        score = 30.0 + sum(8.0 for key in keywords if key in text)
        if setup.get("reaction_profile") and setup.get("reaction_profile") != "Balanced":
            score += 12.0
        if setup.get("volume_state") in {"EXPANDING", "CONFIRMED", "VOLUME_CONFIRMED"}:
            score += 10.0
        return max(0.0, min(100.0, score))

    @staticmethod
    def _target_ahead_probability(
        setup: dict[str, Any],
        *,
        demand_supply: float,
        prebreakout_memory: float,
        sector_score: float,
        catalyst_confidence: float,
        trigger_pct: float,
        target_pct: float,
        risk_pct: float,
    ) -> float:
        score = (
            demand_supply * 0.30
            + prebreakout_memory * 0.24
            + safe_float(setup.get("final_selector_score")) * 0.16
            + sector_score * 0.12
            + catalyst_confidence * 0.08
            + max(0.0, min(100.0, 100.0 - max(trigger_pct, 0.0) * 80.0)) * 0.10
        )
        if target_pct <= 0:
            score -= 35.0
        if risk_pct > target_pct and target_pct > 0:
            score -= 15.0
        if str(setup.get("trap_risk") or "").upper() == "MEDIUM":
            score -= 8.0
        elif str(setup.get("trap_risk") or "").upper() == "HIGH":
            score -= 22.0
        return max(0.0, min(100.0, score))

    @staticmethod
    def _relative_opportunity_score(
        setup: dict[str, Any],
        *,
        demand_supply: float,
        prebreakout_memory: float,
        sector_score: float,
        target_probability: float,
        trigger_pct: float,
        target_pct: float,
        risk_pct: float,
    ) -> float:
        proximity = max(0.0, min(100.0, 100.0 - abs(trigger_pct) * 90.0))
        rr_quality = max(0.0, min(100.0, (target_pct / max(risk_pct, 0.05)) * 45.0)) if target_pct > 0 else 0.0
        clean_invalidation = 85.0 if setup.get("invalidation_note") else 40.0
        trap_score = {"LOW": 90.0, "MEDIUM": 55.0, "HIGH": 10.0}.get(str(setup.get("trap_risk") or "").upper(), 45.0)
        return (
            target_probability * 0.26
            + demand_supply * 0.20
            + prebreakout_memory * 0.16
            + proximity * 0.14
            + rr_quality * 0.10
            + trap_score * 0.08
            + sector_score * 0.04
            + clean_invalidation * 0.02
        )

    @staticmethod
    def _expected_time_to_t1(setup: dict[str, Any], target_pct: float) -> str:
        volume = str(setup.get("volume_state") or "").upper()
        pressure = str(setup.get("pressure_state") or "").upper()
        if target_pct <= 0:
            return "Target already reached"
        if target_pct <= 0.35 and volume in {"EXPANDING", "CONFIRMED", "VOLUME_CONFIRMED"}:
            return "Fast if trigger confirms"
        if pressure in {"MOMENTUM", "BUYER_PRESSURE", "SELLER_PRESSURE"} and target_pct <= 0.9:
            return "Intraday watch"
        return "Needs more buildup"

    def _stock_learning_hint(self, setup: dict[str, Any]) -> str:
        try:
            guard = self.paper_trades.setup_risk_guard(
                setup_type=str(setup.get("setup_type") or ""),
                regime=str(setup.get("regime") or setup.get("market_bias") or ""),
                direction=str(setup.get("trade_direction") or setup.get("direction") or ""),
                session_date=self.paper_trades.session_date(),
            )
        except Exception:
            guard = {}
        entries = int(guard.get("entries", 0) or 0)
        if entries <= 0:
            return "Learning: no completed local history for this setup yet."
        return (
            "Learning: "
            f"{entries} entries, SL rate {float(guard.get('sl_rate', 0.0) or 0.0):.0%}, "
            f"expectancy {float(guard.get('expectancy_points', 0.0) or 0.0):.2f}."
        )

    @staticmethod
    def _pretrade_label(setup: dict[str, Any]) -> str:
        status = str(setup.get("trade_status") or "").upper()
        grade = str(setup.get("prediction_grade") or "").upper()
        trap = str(setup.get("trap_risk") or "").upper()
        entry_type = str(setup.get("entry_type") or "").upper()
        band = str(setup.get("scanner_band") or "").lower()
        if band == "trade-ready":
            return "TRADE READY"
        if band == "near-trigger":
            return "NEAR TRIGGER"
        if band == "high-edge watch":
            return "HIGH-EDGE WATCH"
        if band == "avoid":
            return "AVOID"
        if entry_type == "CHASING" or trap == "HIGH":
            return "TOO LATE / FAKEOUT RISK"
        if status == "TRADE" and grade in {"A+", "A"}:
            return "TRADE READY"
        if status == "WAIT":
            return "WATCH FOR TRIGGER"
        if status == "AVOID":
            return "AVOID"
        return "WATCHLIST"

    @staticmethod
    def _pretrade_band(setup: dict[str, Any]) -> str:
        status = str(setup.get("trade_status") or "").upper()
        bucket = str(setup.get("selection_bucket") or "").upper()
        grade = str(setup.get("prediction_grade") or "").upper()
        trap = str(setup.get("trap_risk") or "").upper()
        entry_type = str(setup.get("entry_type") or "").upper()
        breakout = str(setup.get("pre_breakout_status") or "").upper()
        score = safe_float(setup.get("final_selector_score") or setup.get("confidence") or 0.0)

        if status == "AVOID" or trap == "HIGH" or entry_type == "CHASING":
            return "avoid"
        if bucket == "TRADE_READY" and status == "TRADE" and grade in {"A+", "A"} and score >= 78:
            return "trade-ready"
        if bucket == "NEAR_TRIGGER" or (status == "WAIT" and breakout == "NEAR_BREAKOUT" and score >= 68):
            return "near-trigger"
        if bucket == "EARLY_WATCH" or (score >= 58 and breakout in {"BUILDING", "NEAR_BREAKOUT"}):
            return "high-edge watch"
        if status == "TRADE":
            return "trade-ready" if score >= 72 else "near-trigger"
        if status == "WAIT":
            return "watchlist"
        return "watchlist"

    def submit_kotak_totp(self, totp_code: str) -> dict[str, Any]:
        code = str(totp_code or "").strip()
        if not (code.isdigit() and len(code) == 6):
            return {"ok": False, "message": "Enter the current 6-digit Kotak TOTP code."}
        if self.config.simulated:
            return {
                "ok": False,
                "message": "Live Kotak login is disabled while REACTION_ALPHA_SIMULATED=true. Set it to false in Render, redeploy, then submit the TOTP code.",
            }
        if self._router is None:
            self._router = build_router()
        self._live_status = "connecting"
        self._live_status_detail = "Submitting Kotak TOTP and starting live feed"
        auth = self._router.submit_totp_code(code)
        if not auth.get("ok"):
            self._live_status = "error"
            self._live_status_detail = str(auth.get("message") or "Kotak authentication failed")
            return auth
        try:
            if self.config.dynamic_universe_enabled:
                self._equity_symbols = self._select_dynamic_symbols()
            else:
                self._equity_symbols = list(self.config.symbols)
            self._apply_live_subscriptions()
        except Exception as exc:
            self._live_status = "error"
            self._live_status_detail = str(exc)
            log.exception("Live feed start failed after TOTP submission")
            return {"ok": False, "message": str(exc)}
        self._live_status = "live"
        tracked = len(self._subscriptions) if self._subscriptions else len(self._equity_symbols)
        self._live_status_detail = f"Live feed active for {tracked} instruments"
        return {"ok": True, "message": self._live_status_detail}

    def _apply_live_subscriptions(self) -> None:
        if self._router is None:
            return
        tokens = self._router.kotak.resolve_tokens(self._equity_symbols, exchange_segment=self.config.exchange_segment)
        equity_subscriptions = [
            {"instrument_token": token, "exchange_segment": self.config.exchange_segment, "symbol": symbol}
            for symbol, token in tokens.items()
            if token
        ]
        self._subscriptions = equity_subscriptions + [
            {
                "instrument_token": str(item["instrument_token"]),
                "exchange_segment": str(item["exchange_segment"]),
                "symbol": str(item["symbol"]),
                "is_index": True,
            }
            for item in self._indices
        ]
        snapshot = self._router.fetch_quote_snapshot(self._equity_symbols, batch_size=50)
        if not snapshot.empty:
            for _, row in snapshot.iterrows():
                self.store.register_previous_levels(
                    str(row.get("symbol")),
                    safe_float(row.get("prev_close")),
                    safe_float(row.get("high")),
                    safe_float(row.get("low")),
                )
        try:
            token_snapshot = self._router.kotak.quote_token_snapshot(
                {
                    item["symbol"]: {
                        "instrument_token": item["instrument_token"],
                        "exchange_segment": item["exchange_segment"],
                    }
                    for item in self._indices
                }
            )
            for symbol, row in token_snapshot.items():
                self.store.register_previous_levels(
                    symbol,
                    safe_float(row.get("prev_close")),
                    safe_float(row.get("high")),
                    safe_float(row.get("low")),
                )
        except Exception:
            log.exception("Unable to preload index reference levels")
        try:
            self._router.stop_live_feed()
        except Exception:
            pass
        self._router.start_live_feed(
            instruments=self._subscriptions,
            on_tick=self._on_live_tick,
            on_close=lambda message: log.warning("Kotak websocket closed: %s", message),
            on_error=lambda message: log.error("Kotak websocket error: %s", message),
            reconnect=True,
            reconnect_delay=3.0,
        )

    def _select_dynamic_symbols(self) -> list[str]:
        if self._router is None:
            return list(self.config.symbols)
        universe = load_universe(max_symbols=self.config.dynamic_scan_universe)
        if universe.empty:
            return list(self.config.symbols)
        rows = universe.to_dict("records")
        symbols = [str(row.get("symbol") or "").upper().strip() for row in rows if str(row.get("symbol") or "").strip()]
        snapshot = self._router.fetch_quote_snapshot(symbols, batch_size=50)
        if snapshot.empty:
            return list(self.config.symbols)
        sector_by_symbol = {
            str(row.get("symbol") or "").upper().strip(): str(row.get("sector") or "Unknown").strip() or "Unknown"
            for row in rows
        }
        snapshot_rows: list[dict[str, Any]] = []
        volumes: list[float] = []
        range_pcts: list[float] = []
        change_pcts: list[float] = []

        for _, row in snapshot.iterrows():
            symbol = str(row.get("symbol") or "").upper().strip()
            ltp = safe_float(row.get("ltp"))
            prev_close = safe_float(row.get("prev_close"))
            open_price = safe_float(row.get("open"), prev_close)
            high = safe_float(row.get("high"), max(ltp, open_price, prev_close))
            low = safe_float(row.get("low"), min(value for value in [ltp, open_price, prev_close] if value > 0)) if any(value > 0 for value in [ltp, open_price, prev_close]) else 0.0
            volume = safe_float(row.get("volume"))
            if not symbol or ltp <= 0 or prev_close <= 0 or high <= 0 or low <= 0:
                continue
            change_pct = ((ltp - prev_close) / prev_close) * 100.0
            range_pct = ((high - low) / prev_close) * 100.0 if prev_close else 0.0
            open_drive_pct = abs(((ltp - open_price) / open_price) * 100.0) if open_price > 0 else abs(change_pct)
            near_high = 1.0 - min(max((high - ltp) / max(high - low, 0.01), 0.0), 1.0)
            near_low = 1.0 - min(max((ltp - low) / max(high - low, 0.01), 0.0), 1.0)
            breakout_proximity = max(near_high, near_low)
            snapshot_rows.append(
                {
                    "symbol": symbol,
                    "sector": sector_by_symbol.get(symbol, "Unknown"),
                    "ltp": ltp,
                    "prev_close": prev_close,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "volume": volume,
                    "change_pct": change_pct,
                    "abs_change_pct": abs(change_pct),
                    "range_pct": range_pct,
                    "open_drive_pct": open_drive_pct,
                    "breakout_proximity": breakout_proximity,
                }
            )
            volumes.append(volume)
            range_pcts.append(range_pct)
            change_pcts.append(abs(change_pct))

        if not snapshot_rows:
            return list(self.config.symbols)

        avg_volume = max(sum(volumes) / len(volumes), 1.0)
        avg_range_pct = max(sum(range_pcts) / len(range_pcts), 0.01)
        avg_change_pct = max(sum(change_pcts) / len(change_pcts), 0.01)

        sector_stats: dict[str, dict[str, float]] = defaultdict(lambda: {"sum_change": 0.0, "count": 0.0, "participation": 0.0})
        for row in snapshot_rows:
            sector = row["sector"]
            sector_stats[sector]["sum_change"] += row["change_pct"]
            sector_stats[sector]["count"] += 1.0
            if row["abs_change_pct"] >= avg_change_pct * 0.8:
                sector_stats[sector]["participation"] += 1.0

        ranked_rows: list[tuple[float, str, str]] = []
        for row in snapshot_rows:
            sector = row["sector"]
            sector_count = max(sector_stats[sector]["count"], 1.0)
            sector_change = sector_stats[sector]["sum_change"] / sector_count
            sector_participation = sector_stats[sector]["participation"] / sector_count
            direction_aligned = (row["change_pct"] >= 0 and sector_change >= 0) or (row["change_pct"] < 0 and sector_change < 0)

            relative_volume = min(row["volume"] / avg_volume, 3.0)
            expansion = min(row["range_pct"] / avg_range_pct, 3.0)
            move_quality = min(row["abs_change_pct"] / avg_change_pct, 3.0)
            opening_drive = min(row["open_drive_pct"] / max(avg_change_pct, 0.15), 3.0)
            sector_strength = min(abs(sector_change) / max(avg_change_pct, 0.15), 3.0)
            alignment_bonus = 1.0 if direction_aligned else 0.35
            speed_proxy = min((opening_drive * 0.55) + (expansion * 0.45), 3.0)
            state = self.store.get(row["symbol"])
            speed_snapshot = self._speed_snapshot(state)
            live_speed_bonus = 0.0
            if speed_snapshot["bars"] >= 15:
                live_speed_bonus = min(speed_snapshot["velocity_15s_bps"] / max(self.config.speed_velocity_threshold_bps_15s, 1.0), 3.0)
                if speed_snapshot["velocity_30s_bps"] < (self.config.speed_velocity_threshold_bps_30s * 0.35):
                    live_speed_bonus -= 0.8

            composite = (
                move_quality * 24.0
                + relative_volume * 22.0
                + expansion * 18.0
                + row["breakout_proximity"] * 14.0
                + opening_drive * 10.0
                + sector_strength * 8.0
                + sector_participation * 4.0
                + speed_proxy * self.config.dynamic_speed_weight
                + live_speed_bonus * 8.0
            ) * alignment_bonus
            ranked_rows.append((composite, row["symbol"], sector))

        ranked_rows.sort(reverse=True)
        selected: list[str] = []
        sector_counts: dict[str, int] = defaultdict(int)
        for _, symbol, sector in ranked_rows:
            if sector_counts[sector] >= self.config.dynamic_max_per_sector:
                continue
            selected.append(symbol)
            sector_counts[sector] += 1
            if len(selected) >= self.config.dynamic_universe_size:
                break
        if len(selected) < self.config.dynamic_universe_size:
            for _, symbol, _ in ranked_rows:
                if symbol in selected:
                    continue
                selected.append(symbol)
                if len(selected) >= self.config.dynamic_universe_size:
                    break
        return selected or list(self.config.symbols)

    def _start_selection_refresh(self) -> None:
        if self._selection_thread and self._selection_thread.is_alive():
            return
        self._selection_thread = threading.Thread(target=self._selection_refresh_loop, daemon=True, name="reaction-alpha-universe-refresh")
        self._selection_thread.start()

    def _selection_refresh_loop(self) -> None:
        while not self._stop_event.is_set():
            time.sleep(max(self.config.dynamic_refresh_sec, 30.0))
            if self._stop_event.is_set() or self._router is None:
                break
            try:
                next_symbols = self._select_dynamic_symbols()
                if next_symbols and next_symbols != self._equity_symbols:
                    log.info("Refreshing dynamic universe: %s -> %s", self._equity_symbols, next_symbols)
                    self._equity_symbols = next_symbols
                    with self._lock:
                        self._apply_live_subscriptions()
                        self._broadcast_if_due()
            except Exception:
                log.exception("Dynamic universe refresh failed")

    def _start_simulation(self) -> None:
        if self._sim_thread and self._sim_thread.is_alive():
            return
        self._sim_thread = threading.Thread(target=self._simulate_loop, daemon=True, name="reaction-alpha-sim")
        self._sim_thread.start()

    def _simulate_loop(self) -> None:
        import math

        anchors = {symbol: 100.0 + (idx * 150.0) for idx, symbol in enumerate(self.config.symbols, start=1)}
        anchors.update({"NIFTY": 22450.0, "BANKNIFTY": 48200.0, "SENSEX": 73800.0})
        prices = dict(anchors)
        totals = defaultdict(float)
        phases = {symbol: random.uniform(0.0, math.tau) for symbol in anchors}
        self._seed_simulation_history(anchors, prices, totals, phases)
        while not self._stop_event.is_set():
            for symbol, price in list(prices.items()):
                anchor = anchors[symbol]
                phase = phases[symbol]
                is_index = symbol in {"NIFTY", "BANKNIFTY", "SENSEX"}
                wave_span = anchor * (0.0045 if is_index else 0.0085)
                noise_span = anchor * (0.0007 if is_index else 0.0012)
                mean_reversion = (anchor - price) * 0.08
                cyclic_push = math.sin(phase) * wave_span
                noise = random.uniform(-noise_span, noise_span)
                new_price = max(5.0, price + mean_reversion + (cyclic_push * 0.18) + noise)
                max_deviation = anchor * (0.018 if is_index else 0.028)
                new_price = max(anchor - max_deviation, min(anchor + max_deviation, new_price))
                prices[symbol] = new_price
                phases[symbol] = phase + random.uniform(0.08, 0.18)
                totals[symbol] += random.randint(1200, 16000)
                bid = new_price - random.uniform(0.02, 0.12)
                ask = new_price + random.uniform(0.02, 0.12)
                tick = TickData(
                    symbol=symbol,
                    instrument_token=f"SIM-{symbol}",
                    exchange_segment="bse_cm" if symbol == "SENSEX" else self.config.exchange_segment,
                    timestamp=datetime.now(),
                    price=round(new_price, 2),
                    volume=totals[symbol],
                    bid=round(bid, 2),
                    ask=round(ask, 2),
                    bid_size=random.randint(800, 5000),
                    ask_size=random.randint(800, 5000),
                    vwap=new_price,
                    raw={"simulated": True},
                )
                if not self.store.get(symbol).previous_close:
                    self.store.register_previous_levels(symbol, anchor, anchor * 1.01, anchor * 0.99)
                self.process_tick(tick)
            time.sleep(0.25)

    def _seed_simulation_history(
        self,
        anchors: dict[str, float],
        prices: dict[str, float],
        totals,
        phases: dict[str, float],
    ) -> None:
        now = datetime.now().replace(second=0, microsecond=0)
        for symbol, anchor in anchors.items():
            if not self.store.get(symbol).previous_close:
                self.store.register_previous_levels(symbol, anchor, anchor * 1.01, anchor * 0.99)
            blueprint = self._simulation_blueprint(symbol, anchor)
            total_volume = 0.0
            for idx, candle in enumerate(blueprint):
                minute_ts = now - timedelta(minutes=len(blueprint) - idx)
                prices_path = [
                    candle["open"],
                    candle["low"],
                    candle["high"],
                    candle["close"],
                ]
                for step, price in enumerate(prices_path):
                    total_volume += candle["volume"] / len(prices_path)
                    ts = minute_ts + timedelta(seconds=step * 15)
                    tick = TickData(
                        symbol=symbol,
                        instrument_token=f"SIM-{symbol}",
                        exchange_segment="bse_cm" if symbol == "SENSEX" else self.config.exchange_segment,
                        timestamp=ts,
                        price=round(price, 2),
                        volume=round(total_volume, 2),
                        bid=round(price - max(anchor * 0.00012, 0.02), 2),
                        ask=round(price + max(anchor * 0.00012, 0.02), 2),
                        bid_size=1800 + (idx * 40) + (step * 60),
                        ask_size=1600 + (idx * 35) + ((3 - step) * 55),
                        vwap=round((candle["open"] + candle["high"] + candle["low"] + candle["close"]) / 4.0, 2),
                        raw={"simulated": True, "seeded": True},
                    )
                    self.process_tick(tick)
            prices[symbol] = blueprint[-1]["close"]
            totals[symbol] = total_volume
            phases[symbol] = random.uniform(0.0, 6.28)

    def _simulation_blueprint(self, symbol: str, anchor: float) -> list[dict[str, float]]:
        unit = max(anchor * 0.0032, 0.9)
        volume_base = 8500.0 if symbol in {"NIFTY", "BANKNIFTY", "SENSEX"} else 4200.0

        def candle(open_p: float, high_p: float, low_p: float, close_p: float, volume_mult: float = 1.0) -> dict[str, float]:
            return {
                "open": round(open_p, 2),
                "high": round(high_p, 2),
                "low": round(low_p, 2),
                "close": round(close_p, 2),
                "volume": round(volume_base * volume_mult, 2),
            }

        bullish_breakout = [
            candle(anchor - 3.0 * unit, anchor - 2.2 * unit, anchor - 3.4 * unit, anchor - 2.6 * unit, 0.8),
            candle(anchor - 2.6 * unit, anchor - 1.8 * unit, anchor - 2.9 * unit, anchor - 1.9 * unit, 0.9),
            candle(anchor - 1.9 * unit, anchor - 1.0 * unit, anchor - 2.1 * unit, anchor - 1.2 * unit, 1.0),
            candle(anchor - 1.2 * unit, anchor - 0.3 * unit, anchor - 1.4 * unit, anchor - 0.5 * unit, 1.0),
            candle(anchor - 0.5 * unit, anchor + 0.2 * unit, anchor - 0.7 * unit, anchor + 0.1 * unit, 1.0),
            candle(anchor + 0.1 * unit, anchor + 0.5 * unit, anchor - 0.2 * unit, anchor + 0.3 * unit, 0.9),
            candle(anchor + 0.3 * unit, anchor + 0.7 * unit, anchor + 0.1 * unit, anchor + 0.4 * unit, 0.9),
            candle(anchor + 0.4 * unit, anchor + 0.8 * unit, anchor + 0.2 * unit, anchor + 0.55 * unit, 0.85),
            candle(anchor + 0.55 * unit, anchor + 0.9 * unit, anchor + 0.3 * unit, anchor + 0.6 * unit, 0.85),
            candle(anchor + 0.6 * unit, anchor + 0.95 * unit, anchor + 0.45 * unit, anchor + 0.65 * unit, 0.9),
            candle(anchor + 0.65 * unit, anchor + 1.0 * unit, anchor + 0.5 * unit, anchor + 0.7 * unit, 0.95),
            candle(anchor + 0.7 * unit, anchor + 2.6 * unit, anchor + 0.55 * unit, anchor + 2.2 * unit, 1.9),
        ]

        pullback_continuation = [
            candle(anchor - 3.4 * unit, anchor - 2.6 * unit, anchor - 3.7 * unit, anchor - 2.8 * unit, 0.9),
            candle(anchor - 2.8 * unit, anchor - 2.0 * unit, anchor - 3.0 * unit, anchor - 2.1 * unit, 0.95),
            candle(anchor - 2.1 * unit, anchor - 1.2 * unit, anchor - 2.3 * unit, anchor - 1.3 * unit, 1.0),
            candle(anchor - 1.3 * unit, anchor - 0.4 * unit, anchor - 1.5 * unit, anchor - 0.5 * unit, 1.05),
            candle(anchor - 0.5 * unit, anchor + 0.4 * unit, anchor - 0.7 * unit, anchor + 0.2 * unit, 1.05),
            candle(anchor + 0.2 * unit, anchor + 1.0 * unit, anchor - 0.05 * unit, anchor + 0.85 * unit, 1.1),
            candle(anchor + 0.85 * unit, anchor + 1.25 * unit, anchor + 0.55 * unit, anchor + 0.65 * unit, 0.95),
            candle(anchor + 0.65 * unit, anchor + 0.95 * unit, anchor + 0.35 * unit, anchor + 0.45 * unit, 0.9),
            candle(anchor + 0.45 * unit, anchor + 0.9 * unit, anchor + 0.25 * unit, anchor + 0.55 * unit, 0.9),
            candle(anchor + 0.55 * unit, anchor + 1.0 * unit, anchor + 0.35 * unit, anchor + 0.7 * unit, 0.95),
            candle(anchor + 0.7 * unit, anchor + 1.1 * unit, anchor + 0.4 * unit, anchor + 0.8 * unit, 1.0),
            candle(anchor + 0.8 * unit, anchor + 1.8 * unit, anchor + 0.55 * unit, anchor + 1.65 * unit, 1.45),
        ]

        failed_breakout = [
            candle(anchor + 2.2 * unit, anchor + 2.5 * unit, anchor + 1.8 * unit, anchor + 2.0 * unit, 0.85),
            candle(anchor + 2.0 * unit, anchor + 2.3 * unit, anchor + 1.6 * unit, anchor + 1.9 * unit, 0.9),
            candle(anchor + 1.9 * unit, anchor + 2.1 * unit, anchor + 1.4 * unit, anchor + 1.6 * unit, 0.95),
            candle(anchor + 1.6 * unit, anchor + 1.9 * unit, anchor + 1.1 * unit, anchor + 1.3 * unit, 0.95),
            candle(anchor + 1.3 * unit, anchor + 1.6 * unit, anchor + 0.8 * unit, anchor + 1.1 * unit, 1.0),
            candle(anchor + 1.1 * unit, anchor + 1.35 * unit, anchor + 0.7 * unit, anchor + 0.95 * unit, 0.9),
            candle(anchor + 0.95 * unit, anchor + 1.2 * unit, anchor + 0.55 * unit, anchor + 0.8 * unit, 0.9),
            candle(anchor + 0.8 * unit, anchor + 1.15 * unit, anchor + 0.4 * unit, anchor + 0.7 * unit, 0.92),
            candle(anchor + 0.7 * unit, anchor + 1.0 * unit, anchor + 0.25 * unit, anchor + 0.55 * unit, 0.94),
            candle(anchor + 0.55 * unit, anchor + 0.95 * unit, anchor + 0.1 * unit, anchor + 0.45 * unit, 0.96),
            candle(anchor + 0.45 * unit, anchor + 1.6 * unit, anchor + 0.2 * unit, anchor + 0.5 * unit, 1.15),
            candle(anchor + 0.5 * unit, anchor + 1.55 * unit, anchor + 0.15 * unit, anchor + 0.35 * unit, 1.55),
        ]

        inside_bar = [
            candle(anchor - 2.8 * unit, anchor - 2.1 * unit, anchor - 3.1 * unit, anchor - 2.3 * unit, 0.9),
            candle(anchor - 2.3 * unit, anchor - 1.5 * unit, anchor - 2.5 * unit, anchor - 1.7 * unit, 0.95),
            candle(anchor - 1.7 * unit, anchor - 0.8 * unit, anchor - 1.9 * unit, anchor - 1.0 * unit, 0.98),
            candle(anchor - 1.0 * unit, anchor - 0.2 * unit, anchor - 1.2 * unit, anchor - 0.35 * unit, 1.0),
            candle(anchor - 0.35 * unit, anchor + 0.45 * unit, anchor - 0.55 * unit, anchor + 0.25 * unit, 1.0),
            candle(anchor + 0.25 * unit, anchor + 1.2 * unit, anchor + 0.05 * unit, anchor + 0.9 * unit, 1.1),
            candle(anchor + 0.9 * unit, anchor + 1.5 * unit, anchor + 0.65 * unit, anchor + 1.35 * unit, 1.0),
            candle(anchor + 1.35 * unit, anchor + 1.95 * unit, anchor + 1.1 * unit, anchor + 1.7 * unit, 1.0),
            candle(anchor + 1.7 * unit, anchor + 2.1 * unit, anchor + 1.35 * unit, anchor + 1.6 * unit, 0.85),
            candle(anchor + 1.6 * unit, anchor + 1.85 * unit, anchor + 1.45 * unit, anchor + 1.7 * unit, 0.8),
            candle(anchor + 1.7 * unit, anchor + 1.82 * unit, anchor + 1.55 * unit, anchor + 1.65 * unit, 0.75),
            candle(anchor + 1.65 * unit, anchor + 2.45 * unit, anchor + 1.5 * unit, anchor + 2.3 * unit, 1.5),
        ]

        exhaustion = [
            candle(anchor - 3.0 * unit, anchor - 2.3 * unit, anchor - 3.2 * unit, anchor - 2.5 * unit, 0.9),
            candle(anchor - 2.5 * unit, anchor - 1.7 * unit, anchor - 2.7 * unit, anchor - 1.9 * unit, 0.95),
            candle(anchor - 1.9 * unit, anchor - 1.0 * unit, anchor - 2.1 * unit, anchor - 1.2 * unit, 1.0),
            candle(anchor - 1.2 * unit, anchor - 0.2 * unit, anchor - 1.4 * unit, anchor - 0.35 * unit, 1.02),
            candle(anchor - 0.35 * unit, anchor + 0.65 * unit, anchor - 0.5 * unit, anchor + 0.45 * unit, 1.05),
            candle(anchor + 0.45 * unit, anchor + 1.35 * unit, anchor + 0.2 * unit, anchor + 1.1 * unit, 1.08),
            candle(anchor + 1.1 * unit, anchor + 2.0 * unit, anchor + 0.8 * unit, anchor + 1.75 * unit, 1.1),
            candle(anchor + 1.75 * unit, anchor + 2.45 * unit, anchor + 1.4 * unit, anchor + 2.2 * unit, 1.12),
            candle(anchor + 2.2 * unit, anchor + 2.8 * unit, anchor + 1.9 * unit, anchor + 2.55 * unit, 1.15),
            candle(anchor + 2.55 * unit, anchor + 3.15 * unit, anchor + 2.25 * unit, anchor + 2.85 * unit, 1.18),
            candle(anchor + 2.85 * unit, anchor + 3.55 * unit, anchor + 2.5 * unit, anchor + 3.15 * unit, 1.2),
            candle(anchor + 3.15 * unit, anchor + 4.2 * unit, anchor + 2.85 * unit, anchor + 3.0 * unit, 1.65),
        ]

        blueprints = {
            "RELIANCE": bullish_breakout,
            "HDFCBANK": pullback_continuation,
            "ICICIBANK": failed_breakout,
            "INFY": inside_bar,
            "TCS": exhaustion,
            "NIFTY": bullish_breakout,
            "BANKNIFTY": failed_breakout,
            "SENSEX": inside_bar,
        }
        return blueprints.get(symbol, bullish_breakout)

    def _on_live_tick(self, tick: KotakLiveTick) -> None:
        parsed = self._parse_tick(tick)
        if parsed:
            self.process_tick(parsed)

    def _parse_tick(self, tick: KotakLiveTick) -> TickData | None:
        raw = tick.raw or {}
        symbol = str(tick.symbol or "").upper().strip()
        if not symbol:
            return None
        bid = safe_float(raw.get("bp") or raw.get("best_bid_price") or raw.get("bid") or raw.get("bPrice"), tick.ltp)
        ask = safe_float(raw.get("sp") or raw.get("best_ask_price") or raw.get("ask") or raw.get("sPrice"), tick.ltp)
        bid_size = safe_float(raw.get("bq") or raw.get("bid_qty") or raw.get("best_bid_qty") or raw.get("bQty"))
        ask_size = safe_float(raw.get("sq") or raw.get("ask_qty") or raw.get("best_ask_qty") or raw.get("sQty"))
        volume = safe_float(raw.get("volume") or raw.get("traded_volume") or raw.get("v") or raw.get("ttq"))
        vwap = safe_float(raw.get("vwap") or raw.get("ap"), tick.ltp)
        previous_close = safe_float(raw.get("prev_close") or raw.get("c") or raw.get("ic"))
        if previous_close > 0 and not self.store.get(symbol).previous_close:
            self.store.register_previous_levels(symbol, previous_close)
        return TickData(
            symbol=symbol,
            instrument_token=str(tick.instrument_token),
            exchange_segment=str(tick.exchange_segment or self.config.exchange_segment).lower(),
            timestamp=datetime.now(),
            price=safe_float(tick.ltp),
            volume=volume,
            bid=bid if bid > 0 else safe_float(tick.ltp),
            ask=ask if ask > 0 else safe_float(tick.ltp),
            bid_size=bid_size,
            ask_size=ask_size,
            vwap=vwap if vwap > 0 else safe_float(tick.ltp),
            raw=raw,
        )

    def process_tick(self, tick: TickData) -> TradeSignal | None:
        with self._lock:
            state = self.store.update_tick(tick)
            if not self.config.simulated_market_always_open:
                self.paper_trades.force_market_close_if_needed(tick.timestamp)
            self.outcome_tracker.update_from_state(state)
            self.paper_trades.update_symbol(symbol=state.symbol, price=state.latest_price(), timestamp=tick.timestamp)
            event = self.event_engine.detect(state)
            if event:
                state.add_event(event)
            active_event = state.latest_event()
            signal = self._evaluate_signal(state, active_event.event_type if active_event else "NO EVENT")
            if signal:
                self._signals[state.symbol] = signal
                state.latest_signal = signal
                trade_direction = self._trade_direction(signal)
                self.outcome_tracker.register_signal(signal, direction=trade_direction)
                self.paper_trades.register_signal(signal, direction=trade_direction)
                self.paper_trades.update_symbol(symbol=state.symbol, price=state.latest_price(), timestamp=tick.timestamp)
                self._maybe_alert(signal)
            elif state.symbol in self._signals:
                del self._signals[state.symbol]
                state.latest_signal = None
            else:
                state.latest_signal = None
            self._broadcast_if_due()
            return signal

    def _evaluate_signal(self, state: SymbolState, event_name: str) -> TradeSignal | None:
        active_event = state.latest_event()
        reaction = self.reaction_engine.evaluate(state, active_event)
        structure = self.structure_engine.evaluate(state)
        sr = self.sr_engine.evaluate(state)
        pattern = self.pattern_engine.evaluate(state)
        volume = self.volume_engine.evaluate(state)
        orderflow = self.orderflow_engine.evaluate(state)
        vwap = self.vwap_engine.evaluate(state)
        volatility = self.volatility_engine.evaluate(state)
        speed = self._speed_score(state, structure.trend)
        buildup = self._buildup_score(state)
        fake_move = self._fake_move_penalty(state, reaction, volume)
        regime = self.regime_engine.evaluate(state, structure)
        market_context = self._market_context_score(state, structure, regime)
        direction = self._resolve_directional_bias(
            reaction=reaction.classification,
            structure_trend=structure.trend,
            structure=structure,
            pattern=pattern,
            orderflow=orderflow,
            vwap=vwap,
            market_context=market_context,
            speed=speed,
        )
        score = self.scoring_engine.evaluate(
            reaction=reaction,
            structure=structure,
            sr=sr,
            pattern=pattern,
            volume=volume,
            orderflow=orderflow,
            vwap=vwap,
            volatility=volatility,
            speed=speed,
            market_context=market_context,
            buildup=buildup,
            fake_move_penalty=fake_move,
            symbol=state.symbol,
            sector=self._sector_map.get(state.symbol.upper(), "Unknown"),
        )
        if speed.score <= self.config.speed_ignore_threshold:
            return None
        setup_type = self._classify_setup(event_name, reaction.classification, structure, sr, pattern)
        regime_label = str(regime["label"])
        setup_profile = classify_setup_profile(setup_type, regime_label, direction)
        score = self._apply_setup_profile_score(score, setup_profile)
        if direction == "NEUTRAL":
            return None
        hard_blocks = self._hard_block_reasons(
            state=state,
            direction=direction,
            regime_label=regime_label,
            setup_type=setup_type,
            volume=volume,
            orderflow=orderflow,
            vwap=vwap,
            market_context=market_context,
        )
        if hard_blocks:
            self.paper_trades.remove_candidate(state.symbol)
            log.info("Signal blocked for %s: %s", state.symbol, "; ".join(hard_blocks))
            return None
        if setup_profile == "experimental" and (speed.score < 3 or score.total < setup_profile_min_score(self.config, setup_profile)):
            return None
        setup_guard = self.paper_trades.setup_risk_guard(
            setup_type=setup_type,
            regime=regime_label,
            direction=direction,
            session_date=self.paper_trades.session_date(),
        )
        if bool(setup_guard.get("blocked")):
            log.info("%s", setup_guard.get("reason") or "Adaptive setup guard blocked signal")
            self.paper_trades.remove_candidate(state.symbol)
            return None
        score = self._apply_setup_learning_score(score, setup_guard)
        probability = self.outcome_tracker.snapshot(
            setup_type=setup_type,
            regime=regime_label,
            score=score.total,
            direction=direction,
            components=score.components,
            regime_confidence=int(regime.get("confidence", 50) or 50),
            market_context=market_context.metadata,
        )
        signal = self.signal_engine.build(
            config=self.config,
            state=state,
            event_name=event_name,
            reaction=reaction,
            structure=structure,
            score=score,
            setup_type=setup_type,
            regime=regime_label,
            probability=probability,
            direction=direction,
            setup_profile=setup_profile,
        )
        if signal is not None:
            signal.reason = self._compose_trade_thesis(
                reaction=reaction,
                structure=structure,
                sr=sr,
                pattern=pattern,
                volume=volume,
                orderflow=orderflow,
                vwap=vwap,
                speed=speed,
                market_context=market_context,
            )
            signal.context = {
                "sector": self._sector_map.get(state.symbol, "Unknown"),
                "market": market_context.metadata,
                "pattern": pattern.metadata,
                "speed": speed.metadata,
                "regime_timeframes": regime.get("timeframes", {}),
                "regime_confidence": regime.get("confidence"),
                "setup_profile": setup_profile,
            }
        return signal

    def _buildup_score(self, state: SymbolState) -> ComponentScore:
        candles = list(state.candles_1m)
        ticks = list(state.ticks)
        if len(candles) < 6 or len(ticks) < 8:
            return ComponentScore(name="buildup", score=0, reasons=["Buildup history insufficient"])
        recent = candles[-5:]
        ranges = [c.high - c.low for c in recent]
        tight_range = max(ranges) <= (sum(ranges) / len(ranges)) * 1.2
        rising_lows = all(b.low >= a.low for a, b in zip(recent, recent[1:]))
        falling_highs = all(b.high <= a.high for a, b in zip(recent, recent[1:]))
        rising_volume = all(b.volume >= a.volume * 0.9 for a, b in zip(recent, recent[1:]))
        leaning_flow = abs(sum(t.imbalance for t in ticks[-8:]) / 8.0) >= 0.08
        if tight_range and rising_volume and leaning_flow and (rising_lows or falling_highs):
            return ComponentScore(name="buildup", score=5, reasons=["Buildup phase: tight range with leaning flow"])
        return ComponentScore(name="buildup", score=0, reasons=["No early buildup phase"])

    def _fake_move_penalty(self, state: SymbolState, reaction, volume: ComponentScore) -> ComponentScore:
        ticks = list(state.ticks)
        if len(ticks) < 12:
            return ComponentScore(name="fake_move", score=0, reasons=[])
        latest = ticks[-1]
        prices = [tick.price for tick in ticks[-8:]]
        displacement = max(prices) - min(prices)
        atr = state.atr(window=14)
        low_volume = volume.metadata.get("latest_1m", 0) < max(volume.metadata.get("avg_1m", 0), 1) * 1.1
        if reaction.classification == "REVERSAL" and displacement >= atr * 0.8:
            return ComponentScore(name="fake_move", score=-5, reasons=["Trap detected after failed expansion"])
        if low_volume and displacement >= atr * 0.7 and abs(latest.price - prices[-3]) <= atr * 0.2:
            return ComponentScore(name="fake_move", score=-4, reasons=["Low-volume breakout behaving like a fake move"])
        return ComponentScore(name="fake_move", score=0, reasons=[])

    def _maybe_alert(self, signal: TradeSignal) -> None:
        existing = self._signals.get(signal.stock)
        if existing and existing.score >= signal.score and existing.signal == signal.signal:
            return
        if not (self.config.telegram_bot_token and self.config.telegram_chat_id):
            return
        message = (
            f"{signal.signal}\n"
            f"{signal.stock} | score {signal.score} | entry {signal.entry} | sl {signal.sl}\n"
            f"T1 {signal.t1} | T2 {signal.t2}\n"
            f"Reason: {', '.join(signal.reason[:3])}"
        )
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.config.telegram_bot_token}/sendMessage",
                json={"chat_id": self.config.telegram_chat_id, "text": message},
                timeout=5,
            )
        except Exception:
            log.exception("Telegram alert failed")

    def _broadcast_if_due(self) -> None:
        now = time.time()
        if now - self._last_broadcast_ts < self.config.heartbeat_sec:
            return
        self._last_broadcast_ts = now
        self.hub.publish(self.snapshot())

    def _market_session(self) -> dict[str, str]:
        now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
        if self.config.simulated_market_always_open:
            return {
                "status": "OPEN",
                "detail": "Demo session live with simulated data",
                "timestamp_ist": now_ist.isoformat(timespec="seconds"),
            }
        open_time = dt_time(9, 15)
        close_time = dt_time(15, 30)
        is_weekday = now_ist.weekday() < 5
        is_open = is_weekday and open_time <= now_ist.time() <= close_time
        status = "OPEN" if is_open else "CLOSED"
        detail = "Market live" if is_open else "Market closed"
        return {
            "status": status,
            "detail": detail,
            "timestamp_ist": now_ist.isoformat(timespec="seconds"),
        }

    def _index_cards(self) -> list[dict[str, Any]]:
        cards: list[dict[str, Any]] = []
        for item in self._indices:
            symbol = str(item["symbol"]).upper()
            state = self.store.get(symbol)
            price = state.latest_price()
            prev_close = state.previous_close
            change = price - prev_close if price and prev_close else 0.0
            change_pct = ((change / prev_close) * 100.0) if prev_close else 0.0
            cards.append(
                {
                    "symbol": symbol,
                    "price": round(price, 2) if price else None,
                    "change": round(change, 2),
                    "change_pct": round(change_pct, 2),
                    "trend": "UP" if change > 0 else "DOWN" if change < 0 else "FLAT",
                }
            )
        return cards

    def snapshot(self) -> dict[str, Any]:
        if not self.config.simulated_market_always_open:
            self.paper_trades.force_market_close_if_needed()
        fresh_signals: list[TradeSignal] = []
        for symbol, signal in list(self._signals.items()):
            state = self.store.get(symbol)
            if self._signal_is_stale(state):
                self._signals.pop(symbol, None)
                if state.latest_signal is signal:
                    state.latest_signal = None
                continue
            fresh_signals.append(signal)
        signals = sorted(fresh_signals, key=lambda item: (item.score, item.raw_confidence), reverse=True)[: self.config.top_n]
        market_session = self._market_session()
        paper_analytics = self.paper_trades.analytics()
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "top_signals": [signal.to_dict() for signal in signals if signal.state in {"READY", "EXECUTE"}],
            "tracked_symbols": len(self.store.states()),
            "mode": "simulated" if self.config.simulated else "live",
            "feed_connection": {
                "status": self._live_status,
                "detail": self._live_status_detail,
            },
            "market_session": market_session,
            "indices": self._index_cards(),
            "tracked_equities": list(self._equity_symbols),
            "paper_trades": paper_analytics,
        }

    def get_signal(self, symbol: str) -> dict[str, Any] | None:
        key = str(symbol or "").upper()
        state = self.store.get(key)
        if self._signal_is_stale(state):
            self._signals.pop(key, None)
            state.latest_signal = None
            return None
        signal = self._signals.get(key)
        return signal.to_dict() if signal else None

    def paper_trade_journal(self, limit: int = 100) -> dict[str, Any]:
        session_date = self.paper_trades.session_date()
        trades = self.paper_trades.recent_trades(limit=limit, session_date=session_date)
        pending = self.paper_trades.pending_triggers(limit=limit, session_date=session_date)
        for trade in trades:
            symbol = str(trade.get("symbol") or "").upper()
            state = self.store.get(symbol)
            live_price = state.latest_price()
            trade["live_price"] = round(live_price, 2) if live_price > 0 else None
        for item in pending:
            symbol = str(item.get("symbol") or "").upper()
            state = self.store.get(symbol)
            live_price = state.latest_price()
            item["live_price"] = round(live_price, 2) if live_price > 0 else None
            status = self.paper_trades.candidate_status(
                direction=str(item.get("direction") or ""),
                entry_trigger=float(item.get("entry_trigger") or 0.0),
                stop_loss=float(item.get("stop_loss") or 0.0),
                target1=float(item.get("target1") or 0.0),
                live_price=item["live_price"],
                regime=str(item.get("regime") or ""),
            )
            item.update(status)
            created_at_raw = str(item.get("created_at") or "")
            created_at = datetime.fromisoformat(created_at_raw) if created_at_raw else datetime.now()
            age_sec = max((datetime.now() - created_at).total_seconds(), 0.0)
            item["age_sec"] = round(age_sec, 1)
            item["stable"] = age_sec >= float(self.config.paper_trade_pending_min_age_sec)
        pending = [item for item in pending if self._should_show_pending_candidate(item)]
        analytics = self.paper_trades.analytics(session_date=session_date)
        analytics["pending_triggers"] = len(pending)
        funnel = analytics.get("funnel", {})
        if isinstance(funnel, dict):
            funnel["pending"] = len(pending)
            visible_signal_count = int(funnel.get("entered", 0) or 0) + len(pending) + int(funnel.get("expired", 0) or 0)
            funnel["signals"] = visible_signal_count
            funnel["entry_conversion_pct"] = (
                int(round((int(funnel.get("entered", 0) or 0) / visible_signal_count) * 100))
                if visible_signal_count
                else 0
            )
            open_trades = int(analytics.get("open_trades", 0) or 0)
            funnel["active_pct"] = (
                int(round(((open_trades + len(pending)) / visible_signal_count) * 100))
                if visible_signal_count
                else 0
            )
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "analytics": analytics,
            "pending_triggers": pending,
            "trades": trades,
        }

    def reset_paper_trades(self, *, today_only: bool) -> dict[str, Any]:
        if today_only:
            return self.paper_trades.reset(session_date=self.paper_trades.session_date())
        return self.paper_trades.reset(session_date=None)

    def _should_show_pending_candidate(self, item: dict[str, Any]) -> bool:
        status = str(item.get("status") or "")
        if status in {"Entry confirmed", "At entry", "Testing trigger"}:
            return True
        if not bool(item.get("stable")):
            return False
        distance_pct = item.get("distance_pct")
        if distance_pct is None:
            return False
        distance_pct = abs(float(distance_pct))
        regime = str(item.get("regime") or "").upper()
        max_distance_pct = float(self.config.paper_trade_pending_max_distance_pct)
        if regime == "CHOPPY":
            max_distance_pct = min(max_distance_pct, float(self.config.paper_trade_pending_max_choppy_distance_pct))
        return distance_pct <= max_distance_pct

    def get_signal_detail(self, symbol: str) -> dict[str, Any]:
        key = str(symbol or "").upper()
        state = self.store.get(key)
        if self._signal_is_stale(state):
            self._signals.pop(key, None)
            state.latest_signal = None
            return {
                "stock": key,
                "state": "NOT_ACTIVE",
                "last_seen_at": state.last_tick_time.isoformat(timespec="seconds") if state.last_tick_time else None,
            }
        signal = self._signals.get(key)
        if signal is not None:
            payload = signal.to_dict()
            payload["price_action_1s"] = state.second_bars(limit=60)
            payload["chart_data"] = state.chart_bars()
            payload["last_price"] = round(state.latest_price(), 2)
            payload["tape_speed"] = len([tick for tick in list(state.ticks)[-60:] if tick.timestamp])  # last buffered micro view
            return payload

        price = state.latest_price()
        if price <= 0:
            return {"stock": key, "state": "NOT_TRACKING"}

        active_event = state.latest_event()
        reaction = self.reaction_engine.evaluate(state, active_event)
        structure = self.structure_engine.evaluate(state)
        sr = self.sr_engine.evaluate(state)
        pattern = self.pattern_engine.evaluate(state)
        volume = self.volume_engine.evaluate(state)
        orderflow = self.orderflow_engine.evaluate(state)
        vwap = self.vwap_engine.evaluate(state)
        volatility = self.volatility_engine.evaluate(state)
        speed = self._speed_score(state, structure.trend)
        buildup = self._buildup_score(state)
        fake_move = self._fake_move_penalty(state, reaction, volume)
        regime = self.regime_engine.evaluate(state, structure)
        market_context = self._market_context_score(state, structure, regime)
        plan_direction = self._resolve_directional_bias(
            reaction=reaction.classification,
            structure_trend=structure.trend,
            structure=structure,
            pattern=pattern,
            orderflow=orderflow,
            vwap=vwap,
            market_context=market_context,
            speed=speed,
        )
        score = self.scoring_engine.evaluate(
            reaction=reaction,
            structure=structure,
            sr=sr,
            pattern=pattern,
            volume=volume,
            orderflow=orderflow,
            vwap=vwap,
            volatility=volatility,
            speed=speed,
            market_context=market_context,
            buildup=buildup,
            fake_move_penalty=fake_move,
            symbol=state.symbol,
            sector=self._sector_map.get(state.symbol.upper(), "Unknown"),
        )
        setup_type = self._classify_setup(active_event.event_type if active_event else "MONITORING", reaction.classification, structure, sr, pattern)
        regime_label = str(regime["label"])
        setup_profile = classify_setup_profile(setup_type, regime_label, plan_direction)
        score = self._apply_setup_profile_score(score, setup_profile)
        probability = self.outcome_tracker.snapshot(
            setup_type=setup_type,
            regime=regime_label,
            score=score.total,
            direction=plan_direction,
            components=score.components,
            regime_confidence=int(regime.get("confidence", 50) or 50),
            market_context=market_context.metadata,
        )

        direction = "WATCH"
        if plan_direction == "BULLISH":
            direction = "BULLISH WATCH"
        elif plan_direction == "BEARISH":
            direction = "BEARISH WATCH"
        levels = build_trade_levels(
            config=self.config,
            state=state,
            reaction=reaction,
            structure=structure,
            direction=plan_direction,
            setup_type=setup_type,
            regime=regime_label,
            setup_profile=setup_profile,
        )
        watch_state = resolve_trade_state(
            price=price,
            entry=levels.entry,
            t1=levels.t1,
            score=score.total,
            strong_threshold=self.config.strong_threshold,
            direction=plan_direction,
            setup_profile=setup_profile,
        )
        if score.total < setup_profile_min_score(self.config, setup_profile) or levels.target1_points < self.config.minimum_profit_points:
            watch_state = "WATCH"
        watch_confidence = max(35, min(84, int(round((score.total * 2.4) + (float(probability.get("t1_hit_rate", 0)) * 0.55)))))

        return {
            "stock": key,
            "event": active_event.event_type if active_event else "MONITORING",
            "reaction": reaction.classification,
            "signal": direction,
            "setup_type": setup_type,
            "regime": regime_label,
            "trend": structure.structure_label,
            "score": score.total,
            "entry": levels.entry,
            "sl": levels.sl,
            "t1": levels.t1,
            "t2": levels.t2,
            "expected_move": levels.expected_move,
            "confidence": f"{watch_confidence}%",
            "reason": list(
                self._compose_trade_thesis(
                    reaction=reaction,
                    structure=structure,
                    sr=sr,
                    pattern=pattern,
                    volume=volume,
                    orderflow=orderflow,
                    vwap=vwap,
                    speed=speed,
                    market_context=market_context,
                )
            )[:6],
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "components": score.components,
            "probability": probability,
            "context": {
                "sector": self._sector_map.get(key, "Unknown"),
                "market": market_context.metadata,
                "pattern": pattern.metadata,
                "speed": speed.metadata,
                "regime_timeframes": regime.get("timeframes", {}),
                "regime_confidence": regime.get("confidence"),
                "setup_profile": setup_profile,
            },
            "raw_confidence": float(watch_confidence),
            "state": watch_state,
            "price_action_1s": state.second_bars(limit=60),
            "chart_data": state.chart_bars(),
            "last_price": round(price, 2),
            "tape_speed": len([tick for tick in list(state.ticks)[-60:] if tick.timestamp]),
        }

    def _signal_is_stale(self, state: SymbolState) -> bool:
        last_tick_time = state.last_tick_time
        if last_tick_time is None:
            return True
        return (datetime.now() - last_tick_time).total_seconds() > max(self.config.signal_stale_sec, 10)

    def _apply_setup_profile_score(self, score: UnifiedScore, setup_profile: str) -> UnifiedScore:
        adjustment = setup_profile_score_adjustment(self.config, setup_profile)
        if adjustment == 0:
            return score
        components = dict(score.components)
        components["setup_profile"] = adjustment
        total = score.total + adjustment
        label = "IGNORE"
        if total >= self.config.elite_threshold:
            label = "ELITE"
        elif total >= self.config.strong_threshold:
            label = "STRONG"
        reasons = list(score.reasons)
        if adjustment > 0:
            reasons.insert(0, "Preferred setup-regime profile boosted")
        else:
            reasons.insert(0, "Experimental setup-regime profile requires stronger proof")
        return UnifiedScore(total=total, label=label, reasons=reasons, components=components)

    def _apply_setup_learning_score(self, score: UnifiedScore, setup_guard: dict[str, Any]) -> UnifiedScore:
        entries = int(setup_guard.get("entries", 0) or 0)
        expectancy = float(setup_guard.get("expectancy_points", 0.0) or 0.0)
        sl_rate = float(setup_guard.get("sl_rate", 0.0) or 0.0)
        if entries <= 0:
            return score
        adjustment = 0
        reason = ""
        if entries >= int(self.config.adaptive_setup_guard_min_expectancy_entries):
            if expectancy > 0 and sl_rate <= 0.45:
                adjustment = 2
                reason = f"Setup learning positive: expectancy {expectancy:.2f}, SL rate {sl_rate:.0%}"
            elif expectancy < 0 or sl_rate >= 0.55:
                adjustment = -2
                reason = f"Setup learning cautious: expectancy {expectancy:.2f}, SL rate {sl_rate:.0%}"
        elif sl_rate >= 0.5:
            adjustment = -1
            reason = f"Early setup learning cautious: SL rate {sl_rate:.0%}"
        if adjustment == 0:
            return score
        components = dict(score.components)
        components["setup_learning"] = adjustment
        total = score.total + adjustment
        label = "IGNORE"
        if total >= self.config.elite_threshold:
            label = "ELITE"
        elif total >= self.config.strong_threshold:
            label = "STRONG"
        reasons = list(score.reasons)
        reasons.insert(0, reason)
        return UnifiedScore(total=total, label=label, reasons=reasons, components=components)

    def _hard_block_reasons(
        self,
        *,
        state: SymbolState,
        direction: str,
        regime_label: str,
        setup_type: str,
        volume: ComponentScore,
        orderflow: ComponentScore,
        vwap: ComponentScore,
        market_context: ComponentScore,
    ) -> list[str]:
        price = state.latest_price()
        latest_tick = state.ticks[-1] if state.ticks else None
        reasons: list[str] = []
        if latest_tick and price > 0:
            spread_bps = (latest_tick.spread / price) * 10000.0
            if spread_bps > float(self.config.hard_block_max_spread_bps):
                reasons.append(f"spread too wide ({spread_bps:.1f} bps)")
            vwap_price = float(vwap.metadata.get("vwap", 0.0) or latest_tick.vwap or 0.0)
            if vwap_price > 0:
                vwap_distance_pct = abs((price - vwap_price) / vwap_price) * 100.0
                max_vwap_distance = float(self.config.hard_block_max_vwap_distance_pct)
                if str(regime_label).upper() == "CHOPPY":
                    max_vwap_distance = min(max_vwap_distance, float(self.config.hard_block_choppy_max_vwap_distance_pct))
                if vwap_distance_pct > max_vwap_distance:
                    reasons.append(f"too extended from VWAP ({vwap_distance_pct:.2f}%)")
        market_breadth = float(market_context.metadata.get("market_breadth", 0.0) or 0.0)
        sector_strength = float(market_context.metadata.get("sector_strength", 0.0) or 0.0)
        against_context = float(self.config.hard_block_against_context_pct)
        if direction == "BULLISH" and (market_breadth <= -against_context or sector_strength <= -against_context):
            reasons.append("bullish setup is against market or sector participation")
        elif direction == "BEARISH" and (market_breadth >= against_context or sector_strength >= against_context):
            reasons.append("bearish setup is against market or sector participation")
        if str(regime_label).upper() == "CHOPPY" and "BREAKOUT" in str(setup_type).upper():
            if int(volume.score) < int(self.config.hard_block_choppy_min_volume_score):
                reasons.append("choppy breakout lacks volume expansion")
            if int(orderflow.score) < int(self.config.hard_block_choppy_min_orderflow_score):
                reasons.append("choppy breakout lacks order-flow confirmation")
        return reasons

    def _market_context_score(self, state: SymbolState, structure, regime: dict[str, object]) -> ComponentScore:
        symbol = state.symbol.upper()
        trade_bias = "NEUTRAL"
        if structure.trend == "Bullish":
            trade_bias = "BULLISH"
        elif structure.trend == "Bearish":
            trade_bias = "BEARISH"
        index_changes = []
        for item in self._indices:
            idx_state = self.store.get(str(item["symbol"]).upper())
            price = idx_state.latest_price()
            prev = idx_state.previous_close
            if price > 0 and prev > 0:
                index_changes.append((price - prev) / prev)
        market_score = mean(index_changes) if index_changes else 0.0
        sector = self._sector_map.get(symbol, "Unknown")
        sector_changes: list[float] = []
        for peer in self._equity_symbols:
            if peer == symbol or self._sector_map.get(peer, "Unknown") != sector:
                continue
            peer_state = self.store.get(peer)
            price = peer_state.latest_price()
            prev = peer_state.previous_close
            if price > 0 and prev > 0:
                sector_changes.append((price - prev) / prev)
        sector_score = mean(sector_changes) if sector_changes else 0.0
        tf_biases = regime.get("timeframes", {}) if isinstance(regime, dict) else {}
        aligned_timeframes = sum(1 for value in tf_biases.values() if value == structure.trend)
        score = 0
        reasons: list[str] = []
        if trade_bias == "BULLISH":
            if market_score >= 0.001:
                score += 2
                reasons.append("Index breadth is supporting bullish continuation")
            if sector_score >= 0.001:
                score += 2
                reasons.append(f"{sector} sector peers are participating on the upside")
        elif trade_bias == "BEARISH":
            if market_score <= -0.001:
                score += 2
                reasons.append("Index breadth is supporting bearish pressure")
            if sector_score <= -0.001:
                score += 2
                reasons.append(f"{sector} sector peers are leaning lower with the setup")
        if aligned_timeframes >= 2:
            score += 1
            reasons.append("Multiple timeframes are aligned with the current bias")
        elif aligned_timeframes == 0 and structure.trend in {"Bullish", "Bearish"}:
            score -= 1
            reasons.append("Higher-timeframe context is not confirming this structure yet")
        score = max(min(score, 5), -2)
        return ComponentScore(
            name="market",
            score=score,
            reasons=reasons or ["Market context mixed"],
            metadata={
                "sector": sector,
                "market_breadth": round(market_score * 100, 2),
                "sector_strength": round(sector_score * 100, 2),
                "aligned_timeframes": aligned_timeframes,
                "timeframes": tf_biases,
            },
        )

    def _speed_snapshot(self, state: SymbolState) -> dict[str, float]:
        bars = list(state.candles_1s)
        if len(bars) < 6:
            return {
                "bars": float(len(bars)),
                "velocity_5s_bps": 0.0,
                "velocity_15s_bps": 0.0,
                "velocity_30s_bps": 0.0,
                "efficiency": 0.0,
                "directional_ratio": 0.0,
                "pullback_ratio": 1.0,
            }

        closes = [bar.close for bar in bars]

        def move_bps(window: int) -> float:
            if len(closes) <= window:
                return 0.0
            start_price = max(closes[-window - 1], 0.01)
            return abs(((closes[-1] - closes[-window - 1]) / start_price) * 10000.0)

        recent = bars[-30:]
        bodies = [bar.close - bar.open for bar in recent]
        net_move = recent[-1].close - recent[0].open
        gross_move = sum(abs(body) for body in bodies)
        efficiency = abs(net_move) / gross_move if gross_move > 0 else 0.0
        sign = 1 if net_move >= 0 else -1
        aligned = sum(1 for body in bodies if (body > 0 and sign > 0) or (body < 0 and sign < 0))
        directional_ratio = aligned / max(len(bodies), 1)
        if sign > 0:
            extreme = max((bar.high for bar in recent), default=recent[-1].high)
        else:
            extreme = min((bar.low for bar in recent), default=recent[-1].low)
        end_price = recent[-1].close
        pullback_ratio = abs(extreme - end_price) / max(abs(net_move), max(end_price * 0.0005, 0.01)) if abs(net_move) > 0 else 1.0

        return {
            "bars": float(len(bars)),
            "velocity_5s_bps": round(move_bps(5), 2),
            "velocity_15s_bps": round(move_bps(15), 2),
            "velocity_30s_bps": round(move_bps(30), 2),
            "efficiency": round(efficiency, 3),
            "directional_ratio": round(directional_ratio, 3),
            "pullback_ratio": round(pullback_ratio, 3),
        }

    def _speed_score(self, state: SymbolState, trend: str) -> ComponentScore:
        metrics = self._speed_snapshot(state)
        bars = int(metrics["bars"])
        if bars < 10:
            return ComponentScore(name="speed", score=0, reasons=["Speed history still building"], metadata=metrics)

        velocity_15 = float(metrics["velocity_15s_bps"])
        velocity_30 = float(metrics["velocity_30s_bps"])
        efficiency = float(metrics["efficiency"])
        directional_ratio = float(metrics["directional_ratio"])
        pullback_ratio = float(metrics["pullback_ratio"])

        score = 0
        reasons: list[str] = []
        fast_threshold_15 = self.config.speed_velocity_threshold_bps_15s
        fast_threshold_30 = self.config.speed_velocity_threshold_bps_30s

        if velocity_15 >= fast_threshold_15 or velocity_30 >= fast_threshold_30:
            score += 3
            reasons.append("Fast displacement is active over the last 15-30 seconds")
        elif velocity_15 >= fast_threshold_15 * 0.75 or velocity_30 >= fast_threshold_30 * 0.75:
            score += 1
            reasons.append("Move speed is improving and close to fast-mover territory")
        else:
            score -= 3
            reasons.append("Slow mover: displacement is not strong enough yet")

        if efficiency >= 0.6 and directional_ratio >= 0.58:
            score += 2
            reasons.append("Move is directional rather than choppy")
        elif efficiency <= 0.35 or directional_ratio <= 0.45:
            score -= 1
            reasons.append("Tape is choppy and lacks clean directional follow-through")

        if pullback_ratio <= 0.35:
            score += 1
            reasons.append("Pullbacks are shallow relative to the impulse")
        elif pullback_ratio >= 0.85:
            score -= 1
            reasons.append("Impulse is fading too deeply to qualify as a fast move")

        if trend == "Bearish" and velocity_15 >= fast_threshold_15 * 0.9:
            reasons.append("Fast bearish pressure is confirmed")
        elif trend == "Bullish" and velocity_15 >= fast_threshold_15 * 0.9:
            reasons.append("Fast bullish pressure is confirmed")

        return ComponentScore(name="speed", score=max(min(score, 6), -4), reasons=reasons, metadata=metrics)

    @staticmethod
    def _trade_direction(signal: TradeSignal) -> str:
        if signal.direction in {"BULLISH", "BEARISH", "NEUTRAL"}:
            return signal.direction
        signal_label = signal.signal
        reaction = signal.reaction
        if "BULLISH" in signal_label:
            return "BULLISH"
        if "BEARISH" in signal_label or reaction == "REVERSAL":
            return "BEARISH"
        return "NEUTRAL"

    @staticmethod
    def _direction_from_reaction_structure(reaction: str, trend: str) -> str:
        if reaction == "REVERSAL":
            return "BEARISH" if trend != "Bullish" else "BULLISH"
        if trend == "Bearish":
            return "BEARISH"
        if trend == "Bullish" or reaction == "CONTINUATION":
            return "BULLISH"
        return "NEUTRAL"

    @staticmethod
    def _direction_from_watch(reaction: str, trend: str) -> str:
        if trend == "Bullish" or reaction == "CONTINUATION":
            return "BULLISH"
        if trend == "Bearish" or reaction == "REVERSAL":
            return "BEARISH"
        return "NEUTRAL"

    @staticmethod
    def _resolve_directional_bias(
        *,
        reaction: str,
        structure_trend: str,
        structure,
        pattern: ComponentScore,
        orderflow: ComponentScore,
        vwap: ComponentScore,
        market_context: ComponentScore,
        speed: ComponentScore,
    ) -> str:
        bullish = 0
        bearish = 0

        if reaction == "CONTINUATION":
            bullish += 4
        elif reaction == "REVERSAL":
            bearish += 4

        if structure_trend == "Bullish":
            bullish += 4
            if getattr(structure, "bos", False):
                bullish += 2
        elif structure_trend == "Bearish":
            bearish += 4
            if getattr(structure, "bos", False):
                bearish += 2

        pattern_bias = str(pattern.metadata.get("bias", "neutral"))
        if pattern_bias == "bullish":
            bullish += 3 if pattern.score >= 5 else 2
        elif pattern_bias == "bearish":
            bearish += 3 if pattern.score >= 5 else 2

        orderflow_bias = str(orderflow.metadata.get("bias", "neutral"))
        if orderflow_bias == "bullish":
            bullish += 2 + max(orderflow.score - 2, 0)
        elif orderflow_bias == "bearish":
            bearish += 2 + max(orderflow.score - 2, 0)

        vwap_alignment = str(vwap.metadata.get("alignment", "neutral"))
        if vwap_alignment == "bullish":
            bullish += 2
        elif vwap_alignment == "bearish":
            bearish += 2

        market_breadth = float(market_context.metadata.get("market_breadth", 0.0) or 0.0)
        sector_strength = float(market_context.metadata.get("sector_strength", 0.0) or 0.0)
        if market_breadth > 0.1:
            bullish += 1
        elif market_breadth < -0.1:
            bearish += 1
        if sector_strength > 0.1:
            bullish += 1
        elif sector_strength < -0.1:
            bearish += 1

        if speed.score >= 3:
            if reaction == "REVERSAL" or structure_trend == "Bearish":
                bearish += 1
            elif reaction == "CONTINUATION" or structure_trend == "Bullish":
                bullish += 1

        if abs(bullish - bearish) <= 1:
            return "NEUTRAL"
        return "BULLISH" if bullish > bearish else "BEARISH"

    @staticmethod
    def _classify_setup(event_name: str, reaction: str, structure, sr, pattern) -> str:
        pattern_name = str(pattern.metadata.get("pattern", "none"))
        if pattern_name == "shock_breakdown_continuation":
            return "SHOCK_BREAKDOWN_CONTINUATION"
        if pattern_name == "panic_bounce_failure":
            return "PANIC_BOUNCE_FAILURE"
        if pattern_name == "flush_exhaustion_reversal":
            return "FLUSH_EXHAUSTION_REVERSAL"
        if pattern_name in {"breakout_confirmation", "inside_bar_expansion"}:
            return "BREAKOUT_CONTINUATION"
        if pattern_name == "pullback_continuation":
            return "PULLBACK_CONTINUATION"
        if pattern_name in {"failed_breakout_rejection", "exhaustion_reversal"}:
            return "FAILED_BREAKOUT_REVERSAL"
        if pattern_name == "compression":
            return "STRUCTURE_COMPRESSION"
        if reaction == "CONTINUATION" and structure.bos:
            return "BREAKOUT_CONTINUATION"
        if reaction == "CONTINUATION":
            return "PULLBACK_CONTINUATION"
        if reaction == "REVERSAL":
            return "FAILED_BREAKOUT_REVERSAL"
        if reaction == "ABSORPTION":
            return "ABSORPTION_BUILDUP"
        if pattern.score >= 3 or sr.score >= 4:
            return "STRUCTURE_COMPRESSION"
        if event_name == "PRICE EXPANSION":
            return "EVENT_REACTION"
        return "EVENT_REACTION"

    @staticmethod
    def _compose_trade_thesis(
        *,
        reaction: ComponentScore | Any,
        structure: ComponentScore | Any,
        sr: ComponentScore,
        pattern: ComponentScore,
        volume: ComponentScore,
        orderflow: ComponentScore,
        vwap: ComponentScore,
        speed: ComponentScore,
        market_context: ComponentScore,
    ) -> list[str]:
        thesis: list[str] = []
        for items in (
            pattern.reasons,
            reaction.reasons,
            structure.reasons,
            sr.reasons,
            orderflow.reasons,
            vwap.reasons,
            volume.reasons,
            speed.reasons,
            market_context.reasons,
        ):
            for reason in items or []:
                if not reason:
                    continue
                lowered = reason.lower()
                if lowered in {
                    "no confirmed pattern",
                    "pattern still forming",
                    "market context mixed",
                    "buildup history insufficient",
                }:
                    continue
                if reason not in thesis:
                    thesis.append(reason)
                if len(thesis) >= 6:
                    return thesis
        return thesis or ["Setup is building but still needs cleaner confirmation"]
