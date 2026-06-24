from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .metrics import mean, safe_float
from .models import Candle, MarketEvent, TickData, TradeSignal


@dataclass(slots=True)
class SymbolState:
    symbol: str
    previous_close: float = 0.0
    previous_day_high: float = 0.0
    previous_day_low: float = 0.0
    ticks: deque[TickData] = field(default_factory=deque)
    candles_1s: deque[Candle] = field(default_factory=deque)
    candles_1m: deque[Candle] = field(default_factory=deque)
    candles_5m: deque[Candle] = field(default_factory=deque)
    recent_events: deque[MarketEvent] = field(default_factory=deque)
    latest_signal: TradeSignal | None = None
    day_high: float = 0.0
    day_low: float = 0.0
    cumulative_turnover: float = 0.0
    cumulative_volume: float = 0.0
    last_total_volume: float = 0.0
    last_tick_time: datetime | None = None

    def push_tick(self, tick: TickData, tick_limit: int, candle_limit: int) -> None:
        previous_price = self.ticks[-1].price if self.ticks else tick.price
        volume_delta = tick.volume - self.last_total_volume if tick.volume >= self.last_total_volume else tick.volume
        volume_delta = max(volume_delta, 0.0)
        self.last_total_volume = max(self.last_total_volume, tick.volume)
        self.cumulative_volume += volume_delta
        self.cumulative_turnover += tick.price * volume_delta
        if self.cumulative_volume > 0:
            tick.vwap = self.cumulative_turnover / self.cumulative_volume
        self.ticks.append(tick)
        while len(self.ticks) > tick_limit:
            self.ticks.popleft()

        self.day_high = max(self.day_high or tick.price, tick.price)
        self.day_low = min(self.day_low or tick.price, tick.price)
        self.last_tick_time = tick.timestamp

        self._update_second_candle(self.candles_1s, tick, limit=max(180, candle_limit * 3), previous_price=previous_price, volume_delta=volume_delta)
        self._update_candle(self.candles_1m, tick, minutes=1, limit=candle_limit, previous_price=previous_price, volume_delta=volume_delta)
        self._update_candle(self.candles_5m, tick, minutes=5, limit=max(60, candle_limit // 5), previous_price=previous_price, volume_delta=volume_delta)

    def _update_second_candle(
        self,
        store: deque[Candle],
        tick: TickData,
        *,
        limit: int,
        previous_price: float,
        volume_delta: float,
    ) -> None:
        bucket = tick.timestamp.replace(microsecond=0)
        if not store or store[-1].timestamp != bucket:
            open_price = previous_price if previous_price > 0 else tick.price
            store.append(
                Candle(
                    timestamp=bucket,
                    open=open_price,
                    high=max(open_price, tick.price),
                    low=min(open_price, tick.price),
                    close=tick.price,
                    volume=volume_delta,
                    vwap=tick.vwap,
                )
            )
        else:
            candle = store[-1]
            candle.high = max(candle.high, tick.price)
            candle.low = min(candle.low, tick.price)
            candle.close = tick.price
            candle.volume += volume_delta
            candle.vwap = tick.vwap
        while len(store) > limit:
            store.popleft()

    def _update_candle(
        self,
        store: deque[Candle],
        tick: TickData,
        *,
        minutes: int,
        limit: int,
        previous_price: float,
        volume_delta: float,
    ) -> None:
        bucket_minute = (tick.timestamp.minute // minutes) * minutes
        bucket = tick.timestamp.replace(second=0, microsecond=0, minute=bucket_minute)
        if not store or store[-1].timestamp != bucket:
            open_price = previous_price if previous_price > 0 else tick.price
            store.append(
                Candle(
                    timestamp=bucket,
                    open=open_price,
                    high=max(open_price, tick.price),
                    low=min(open_price, tick.price),
                    close=tick.price,
                    volume=volume_delta,
                    vwap=tick.vwap,
                )
            )
        else:
            candle = store[-1]
            candle.high = max(candle.high, tick.price)
            candle.low = min(candle.low, tick.price)
            candle.close = tick.price
            candle.volume += volume_delta
            candle.vwap = tick.vwap
        while len(store) > limit:
            store.popleft()

    def add_event(self, event: MarketEvent) -> None:
        self.recent_events.append(event)
        while len(self.recent_events) > 25:
            self.recent_events.popleft()

    def latest_event(self) -> MarketEvent | None:
        return self.recent_events[-1] if self.recent_events else None

    def latest_price(self) -> float:
        return self.ticks[-1].price if self.ticks else 0.0

    def atr(self, window: int = 14) -> float:
        candles = list(self.candles_1m)[-window - 1 :]
        if len(candles) < 2:
            price = self.latest_price()
            return max(price * 0.003, 0.2) if price > 0 else 0.2
        trs: list[float] = []
        previous_close = candles[0].close
        for candle in candles[1:]:
            tr = max(
                candle.high - candle.low,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            )
            trs.append(tr)
            previous_close = candle.close
        return mean(trs) if trs else max(candles[-1].close * 0.003, 0.2)

    def rolling_avg_volume(self, minutes: int = 1, window: int = 20) -> float:
        store = self.candles_1m if minutes == 1 else self.candles_5m
        candles = list(store)[-window:]
        return mean([c.volume for c in candles]) if candles else 0.0

    def volume_cluster_price(self) -> float:
        candles = list(self.candles_1m)[-30:]
        if not candles:
            return self.latest_price()
        cluster = max(candles, key=lambda item: item.volume)
        return safe_float(cluster.vwap or cluster.close, cluster.close)

    def second_bars(self, limit: int = 60) -> list[dict[str, Any]]:
        rows = list(self.candles_1s)[-limit:]
        return self._serialize_candles(rows)

    def chart_bars(self) -> dict[str, list[dict[str, Any]]]:
        candles_1m = list(self.candles_1m)
        candles_5m = list(self.candles_5m)
        return {
            "1m": self._serialize_candles(candles_1m[-240:]),
            "5m": self._serialize_candles(candles_5m[-120:]),
            "15m": self._serialize_candles(self._aggregate_candles(candles_1m, minutes=15)[-96:]),
            "1h": self._serialize_candles(self._aggregate_candles(candles_1m, minutes=60)[-64:]),
        }

    @staticmethod
    def _serialize_candles(rows: list[Candle]) -> list[dict[str, Any]]:
        return [
            {
                "timestamp": candle.timestamp.isoformat(timespec="seconds"),
                "open": round(candle.open, 2),
                "high": round(candle.high, 2),
                "low": round(candle.low, 2),
                "close": round(candle.close, 2),
                "volume": round(candle.volume, 2),
            }
            for candle in rows
        ]

    @staticmethod
    def _aggregate_candles(rows: list[Candle], *, minutes: int) -> list[Candle]:
        if not rows:
            return []
        aggregated: list[Candle] = []
        for candle in rows:
            bucket_minute = (candle.timestamp.minute // minutes) * minutes
            bucket = candle.timestamp.replace(second=0, microsecond=0, minute=bucket_minute)
            if minutes >= 60:
                bucket = bucket.replace(minute=0)
            if not aggregated or aggregated[-1].timestamp != bucket:
                aggregated.append(
                    Candle(
                        timestamp=bucket,
                        open=candle.open,
                        high=candle.high,
                        low=candle.low,
                        close=candle.close,
                        volume=candle.volume,
                        vwap=candle.vwap,
                    )
                )
                continue
            current = aggregated[-1]
            current.high = max(current.high, candle.high)
            current.low = min(current.low, candle.low)
            current.close = candle.close
            current.volume += candle.volume
            current.vwap = candle.vwap
        return aggregated


class InMemoryMarketStore:
    def __init__(self, tick_limit: int, candle_limit: int) -> None:
        self.tick_limit = tick_limit
        self.candle_limit = candle_limit
        self._states: dict[str, SymbolState] = {}

    def get(self, symbol: str) -> SymbolState:
        key = str(symbol or "").upper()
        if key not in self._states:
            self._states[key] = SymbolState(symbol=key)
        return self._states[key]

    def register_previous_levels(self, symbol: str, previous_close: float, previous_day_high: float = 0.0, previous_day_low: float = 0.0) -> None:
        state = self.get(symbol)
        if previous_close > 0:
            state.previous_close = previous_close
        if previous_day_high > 0:
            state.previous_day_high = previous_day_high
        if previous_day_low > 0:
            state.previous_day_low = previous_day_low

    def update_tick(self, tick: TickData) -> SymbolState:
        state = self.get(tick.symbol)
        state.push_tick(tick, self.tick_limit, self.candle_limit)
        return state

    def states(self) -> list[SymbolState]:
        return list(self._states.values())
