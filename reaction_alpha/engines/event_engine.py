from __future__ import annotations

from ..config import ReactionAlphaConfig
from ..metrics import mean, pct_change
from ..models import MarketEvent
from ..state import SymbolState


class EventDetectionEngine:
    def __init__(self, config: ReactionAlphaConfig) -> None:
        self.config = config

    def detect(self, state: SymbolState) -> MarketEvent | None:
        candles = list(state.candles_1m)
        ticks = list(state.ticks)
        if len(ticks) < 12:
            return None
        latest_tick = ticks[-1]
        if len(candles) >= 3:
            latest_candle = candles[-1]
            avg_volume = mean(c.volume for c in candles[-6:-1]) or latest_candle.volume
        else:
            volume_deltas = [max(curr.volume - prev.volume, 0.0) for prev, curr in zip(ticks[-12:-1], ticks[-11:])]
            latest_candle = None
            avg_volume = mean(volume_deltas[:-1]) if len(volume_deltas) > 1 else 0.0
            latest_volume = volume_deltas[-1] if volume_deltas else 0.0
        event_type = ""
        trigger_value = 0.0
        context: dict[str, float] = {}
        effective_volume = latest_candle.volume if latest_candle is not None else latest_volume
        if avg_volume > 0 and effective_volume >= avg_volume * self.config.volume_spike_multiplier:
            event_type = "VOLUME SPIKE"
            trigger_value = effective_volume / avg_volume
            context["avg_volume"] = avg_volume
        else:
            recent_prices = [tick.price for tick in ticks[-10:]]
            move = abs(pct_change(recent_prices[-1], recent_prices[0]))
            if move >= self.config.price_expansion_threshold:
                event_type = "PRICE EXPANSION"
                trigger_value = move
                context["move_pct"] = move * 100.0
            else:
                recent_imbalances = [tick.imbalance for tick in ticks[-10:]]
                older_imbalances = [tick.imbalance for tick in ticks[-20:-10]] or recent_imbalances
                shift = abs(mean(recent_imbalances) - mean(older_imbalances))
                if shift >= self.config.orderflow_shift_threshold:
                    event_type = "ORDER FLOW SHIFT"
                    trigger_value = shift
                    context["imbalance_shift"] = shift
        if not event_type:
            return None
        last_event = state.latest_event()
        if last_event and last_event.event_type == event_type and (latest_tick.timestamp - last_event.timestamp).total_seconds() <= 20:
            return None
        return MarketEvent(
            event_type=event_type,
            timestamp=latest_tick.timestamp,
            price=latest_tick.price,
            trigger_value=trigger_value,
            context=context,
        )
