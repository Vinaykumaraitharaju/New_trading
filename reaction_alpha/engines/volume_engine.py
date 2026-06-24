from __future__ import annotations

from ..metrics import mean
from ..models import ComponentScore
from ..state import SymbolState


class VolumeEngine:
    def evaluate(self, state: SymbolState) -> ComponentScore:
        candles = list(state.candles_1m)
        second_bars = list(state.candles_1s)
        if len(candles) < 3:
            ticks = list(state.ticks)
            if len(ticks) < 10:
                return ComponentScore(name="volume", score=0, reasons=["Volume history still building"])
            deltas = []
            for previous, current in zip(ticks[-12:-1], ticks[-11:]):
                deltas.append(max(current.volume - previous.volume, 0.0))
            latest_delta = deltas[-1] if deltas else 0.0
            baseline = mean(deltas[:-1]) if len(deltas) > 1 else latest_delta
            score = 4 if baseline > 0 and latest_delta >= baseline * 1.8 else 0
            reasons = ["Tick-volume burst detected"] if score else ["Volume participation is average"]
            return ComponentScore(
                name="volume",
                score=score,
                reasons=reasons,
                metadata={"avg_1m": round(baseline, 2), "avg_5m": round(baseline, 2), "latest_1m": round(latest_delta, 2)},
            )
        latest = candles[-1]
        previous_candles = candles[-21:-1]
        avg_1m = mean(c.volume for c in previous_candles) or latest.volume
        avg_5m = state.rolling_avg_volume(minutes=5, window=12) or avg_1m
        buildup = candles[-5:-1] if len(candles) >= 5 else candles[:-1]
        buildup_volumes = [c.volume for c in buildup]
        rising = len(buildup_volumes) >= 3 and all(b >= a * 0.92 for a, b in zip(buildup_volumes, buildup_volumes[1:]))
        latest_20s = sum(bar.volume for bar in second_bars[-20:])
        prior_windows = []
        if len(second_bars) >= 60:
            prior_windows = [
                sum(bar.volume for bar in second_bars[-40:-20]),
                sum(bar.volume for bar in second_bars[-60:-40]),
            ]
        elif len(second_bars) >= 40:
            prior_windows = [sum(bar.volume for bar in second_bars[-40:-20])]
        avg_20s = mean(prior_windows) if prior_windows else 0.0
        micro_expansion = avg_20s > 0 and latest_20s >= avg_20s * 1.6
        one_minute_expansion = avg_1m > 0 and latest.volume >= avg_1m * 1.6
        absolute_participation = avg_5m > 0 and latest.volume >= avg_5m * 0.9
        score = 0
        reasons: list[str] = []
        if one_minute_expansion or micro_expansion:
            score += 4
            reasons.append("Strong live volume expansion")
        if buildup_volumes and avg_5m > 0 and mean(buildup_volumes) >= avg_5m * 0.8 and rising and absolute_participation:
            score += 5
            reasons.append("Pre-breakout accumulation detected")
        return ComponentScore(
            name="volume",
            score=score,
            reasons=reasons or ["Volume participation is average"],
            metadata={
                "avg_1m": round(avg_1m, 2),
                "avg_5m": round(avg_5m, 2),
                "latest_1m": round(latest.volume, 2),
                "latest_20s": round(latest_20s, 2),
                "avg_20s": round(avg_20s, 2),
            },
        )
