from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time

import pandas as pd

from scanner_brain.core.enums import Side
from scanner_brain.core.models import StockSnapshot


@dataclass(frozen=True)
class CandleSequenceAssessment:
    candles: pd.DataFrame
    snapshot_mode: bool
    structure_state: str
    compression_state: str
    level_test_count: int
    level_test_quality: str
    vwap_state: str
    pressure_state: str
    volume_state: str
    exhaustion_state: str
    time_context: str
    trap_flags: list[str]
    trap_risk: str
    breakout_probability: str
    key_level: float
    support: float
    resistance: float
    distance_from_vwap_pct: float
    distance_from_vwap_atr: float
    relative_volume: float


class CandleSequenceEngine:
    def analyze(
        self,
        stock: StockSnapshot,
        *,
        side: Side,
        reference_level: float | None = None,
        atr_proxy: float | None = None,
    ) -> CandleSequenceAssessment:
        candles = self.extract_candles(stock)
        if candles.empty:
            level = reference_level or (stock.high if side == Side.LONG else stock.low or stock.ltp)
            support = stock.low or stock.ltp
            resistance = stock.high or stock.ltp
            return CandleSequenceAssessment(
                candles=pd.DataFrame(),
                snapshot_mode=True,
                structure_state="CHOPPY",
                compression_state="NONE",
                level_test_count=0,
                level_test_quality="LOOSE",
                vwap_state="ABOVE_HOLD" if stock.ltp >= stock.vwap_proxy else "BELOW_REJECT",
                pressure_state="BUYER_PRESSURE" if side == Side.LONG and stock.ltp >= stock.open else "SELLER_PRESSURE" if side == Side.SHORT and stock.ltp <= stock.open else "ABSORPTION",
                volume_state="WEAK",
                exhaustion_state="ACCEPTABLE",
                time_context=self._time_context(None),
                trap_flags=["snapshot mode"],
                trap_risk="MEDIUM",
                breakout_probability="LOW",
                key_level=round(level, 2),
                support=round(support, 2),
                resistance=round(resistance, 2),
                distance_from_vwap_pct=round(abs(stock.ltp - stock.vwap_proxy) / max(stock.vwap_proxy, 0.01) * 100.0, 2),
                distance_from_vwap_atr=round(abs(stock.ltp - stock.vwap_proxy) / max(atr_proxy or stock.day_range * 0.45, 0.05), 2),
                relative_volume=0.0,
            )

        recent = candles.tail(min(len(candles), 20)).copy()
        atr = max(float(atr_proxy or self._atr_proxy(recent, stock)), 0.05)
        support = float(recent["low"].tail(10).min())
        resistance = float(recent["high"].tail(10).max())
        key_level = float(reference_level or (resistance if side == Side.LONG else support))
        compression_state = self._compression_state(recent, stock)
        structure_state = self._structure_state(recent, compression_state)
        level_test_count, level_test_quality = self._level_tests(recent.tail(12), key_level, side, atr, stock)
        vwap_state, distance_pct, distance_atr = self._vwap_state(recent, side, atr)
        pressure_state = self._pressure_state(recent, side, key_level, atr)
        volume_state, relative_volume = self._volume_state(recent, compression_state, level_test_count)
        exhaustion_state = self._exhaustion_state(recent, side, distance_pct, distance_atr, atr)
        time_context = self._time_context(recent.index[-1] if isinstance(recent.index, pd.DatetimeIndex) and len(recent.index) else None)
        trap_flags = self._trap_flags(
            recent=recent,
            side=side,
            key_level=key_level,
            atr=atr,
            compression_state=compression_state,
            level_test_count=level_test_count,
            level_test_quality=level_test_quality,
            vwap_state=vwap_state,
            pressure_state=pressure_state,
            volume_state=volume_state,
            exhaustion_state=exhaustion_state,
            time_context=time_context,
        )
        trap_risk = self._trap_risk(trap_flags)
        breakout_probability = self._breakout_probability(
            structure_state=structure_state,
            compression_state=compression_state,
            level_test_count=level_test_count,
            level_test_quality=level_test_quality,
            pressure_state=pressure_state,
            volume_state=volume_state,
            vwap_state=vwap_state,
            trap_risk=trap_risk,
        )
        return CandleSequenceAssessment(
            candles=recent,
            snapshot_mode=False,
            structure_state=structure_state,
            compression_state=compression_state,
            level_test_count=level_test_count,
            level_test_quality=level_test_quality,
            vwap_state=vwap_state,
            pressure_state=pressure_state,
            volume_state=volume_state,
            exhaustion_state=exhaustion_state,
            time_context=time_context,
            trap_flags=trap_flags,
            trap_risk=trap_risk,
            breakout_probability=breakout_probability,
            key_level=round(key_level, 2),
            support=round(support, 2),
            resistance=round(resistance, 2),
            distance_from_vwap_pct=round(distance_pct, 2),
            distance_from_vwap_atr=round(distance_atr, 2),
            relative_volume=round(relative_volume, 2),
        )

    @staticmethod
    def extract_candles(stock: StockSnapshot) -> pd.DataFrame:
        raw = stock.raw if isinstance(stock.raw, dict) else {}
        candidate = None
        for key in ("candles", "intraday", "intraday_candles", "history", "history_frame"):
            if key in raw and raw.get(key) is not None:
                candidate = raw.get(key)
                break
        if isinstance(candidate, pd.DataFrame):
            frame = candidate.copy()
        elif isinstance(candidate, list):
            frame = pd.DataFrame(candidate)
        else:
            return pd.DataFrame()

        frame = frame.rename(
            columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
                "Datetime": "datetime",
                "Date": "datetime",
            }
        )
        required = {"open", "high", "low", "close"}
        if not required.issubset(frame.columns):
            return pd.DataFrame()
        if "volume" not in frame:
            frame["volume"] = 0.0
        for col in ["open", "high", "low", "close", "volume", "vwap"]:
            if col in frame:
                frame[col] = pd.to_numeric(frame[col], errors="coerce")
        if "datetime" in frame.columns:
            frame["datetime"] = pd.to_datetime(frame["datetime"], errors="coerce")
            frame = frame.sort_values("datetime")
            frame = frame.set_index("datetime")
        frame = frame.dropna(subset=["open", "high", "low", "close"]).copy()
        if "vwap" not in frame:
            frame["vwap"] = float(raw.get("vwap") or raw.get("average_price") or raw.get("avgPrice") or stock.vwap_proxy)
        else:
            frame["vwap"] = frame["vwap"].fillna(method="ffill").fillna(float(stock.vwap_proxy))
        return frame

    @staticmethod
    def _atr_proxy(candles: pd.DataFrame, stock: StockSnapshot) -> float:
        ranges = (candles["high"] - candles["low"]).tail(10)
        if ranges.empty:
            return max(stock.day_range * 0.45, stock.ltp * 0.0075, 0.05)
        return max(float(ranges.mean()), stock.ltp * 0.0045, 0.05)

    @staticmethod
    def _compression_state(recent: pd.DataFrame, stock: StockSnapshot) -> str:
        current_ranges = (recent["high"] - recent["low"]).tail(5)
        baseline = (recent["high"] - recent["low"]).tail(15).head(10)
        if current_ranges.empty:
            return "NONE"
        current_avg = float(current_ranges.mean())
        baseline_avg = float(baseline.mean()) if not baseline.empty else current_avg
        body_ratio = float((recent["close"] - recent["open"]).abs().tail(5).mean() / max(current_avg, 0.01))
        price_factor = current_avg / max(stock.ltp * 0.01, 0.05)
        if current_avg <= baseline_avg * 0.62 and body_ratio <= 0.5 and price_factor <= 1.0:
            return "TIGHT"
        if current_avg <= baseline_avg * 0.82 and body_ratio <= 0.72 and price_factor <= 1.45:
            return "MODERATE"
        return "NONE"

    @staticmethod
    def _structure_state(recent: pd.DataFrame, compression_state: str) -> str:
        highs = recent["high"].tail(6).reset_index(drop=True)
        lows = recent["low"].tail(6).reset_index(drop=True)
        closes = recent["close"].tail(6).reset_index(drop=True)
        ranges = (recent["high"] - recent["low"]).tail(6)
        bodies = (recent["close"] - recent["open"]).tail(6)
        hh = int((highs.diff().fillna(0) > 0).sum())
        hl = int((lows.diff().fillna(0) > 0).sum())
        lh = int((highs.diff().fillna(0) < 0).sum())
        ll = int((lows.diff().fillna(0) < 0).sum())
        range_avg = float(ranges.mean()) if not ranges.empty else 0.0
        body_avg = float(bodies.abs().mean()) if not bodies.empty else 0.0
        last_range = float(ranges.iloc[-1]) if not ranges.empty else 0.0
        last_body = float(bodies.iloc[-1]) if not bodies.empty else 0.0
        if len(closes) >= 3 and closes.iloc[-1] > highs.iloc[:-1].max() and last_body > max(body_avg * 1.2, 0.01) and last_range > max(range_avg * 1.15, 0.01):
            return "EXPANSION_UP"
        if len(closes) >= 3 and closes.iloc[-1] < lows.iloc[:-1].min() and abs(last_body) > max(body_avg * 1.2, 0.01) and last_range > max(range_avg * 1.15, 0.01):
            return "EXPANSION_DOWN"
        if hh >= 3 and hl >= 3:
            return "HH_HL_BUILDING"
        if lh >= 3 and ll >= 3:
            return "LH_LL_BUILDING"
        if compression_state in {"TIGHT", "MODERATE"}:
            return "RANGE_COMPRESSION"
        return "CHOPPY"

    @staticmethod
    def _level_tests(recent: pd.DataFrame, key_level: float, side: Side, atr: float, stock: StockSnapshot) -> tuple[int, str]:
        tolerance = max(atr * 0.18, stock.ltp * 0.0018, 0.05)
        count = 0
        misses: list[float] = []
        for _, candle in recent.iterrows():
            touch = float(candle["high"]) if side == Side.LONG else float(candle["low"])
            close = float(candle["close"])
            miss = abs(touch - key_level)
            if miss <= tolerance:
                if side == Side.LONG and close <= key_level + tolerance:
                    count += 1
                    misses.append(miss)
                elif side == Side.SHORT and close >= key_level - tolerance:
                    count += 1
                    misses.append(miss)
        if not misses:
            return 0, "LOOSE"
        avg_miss = sum(misses) / len(misses)
        quality = "TIGHT" if avg_miss <= tolerance * 0.45 else "LOOSE"
        return count, quality

    @staticmethod
    def _vwap_state(recent: pd.DataFrame, side: Side, atr: float) -> tuple[str, float, float]:
        closes = recent["close"]
        vwaps = recent["vwap"]
        last_close = float(closes.iloc[-1])
        last_vwap = float(vwaps.iloc[-1])
        distance_pct = abs(last_close - last_vwap) / max(last_vwap, 0.01) * 100.0
        distance_atr = abs(last_close - last_vwap) / max(atr, 0.05)
        crosses = int((closes.gt(vwaps).astype(int).diff().abs().fillna(0) > 0).sum())
        last3 = recent.tail(3)
        above_hold = bool((last3["close"] >= last3["vwap"]).all() and (last3["low"] >= last3["vwap"] * 0.997).sum() >= 2)
        below_reject = bool((last3["close"] <= last3["vwap"]).all() and (last3["high"] <= last3["vwap"] * 1.003).sum() >= 2)
        reclaimed = bool(len(recent) >= 4 and closes.iloc[-2] < vwaps.iloc[-2] and last_close > last_vwap and recent["low"].tail(2).min() >= last_vwap * 0.995)
        if distance_pct >= 1.9 or distance_atr >= 1.7:
            return "EXTENDED", distance_pct, distance_atr
        if crosses >= 4:
            return "VWAP_CHOPPY", distance_pct, distance_atr
        if reclaimed and side == Side.LONG:
            return "VWAP_RECLAIMED", distance_pct, distance_atr
        if above_hold:
            return "ABOVE_HOLD", distance_pct, distance_atr
        if below_reject:
            return "BELOW_REJECT", distance_pct, distance_atr
        return ("ABOVE_HOLD" if last_close >= last_vwap else "BELOW_REJECT"), distance_pct, distance_atr

    @staticmethod
    def _pressure_state(recent: pd.DataFrame, side: Side, key_level: float, atr: float) -> str:
        last5 = recent.tail(5).copy()
        ranges = (last5["high"] - last5["low"]).replace(0, 0.01)
        body_ratio = ((last5["close"] - last5["open"]).abs() / ranges).mean()
        close_strength = ((last5["close"] - last5["low"]) / ranges).mean()
        sell_strength = ((last5["high"] - last5["close"]) / ranges).mean()
        upper_wick = ((last5["high"] - last5[["open", "close"]].max(axis=1)) / ranges).mean()
        lower_wick = ((last5[["open", "close"]].min(axis=1) - last5["low"]) / ranges).mean()
        closes = last5["close"].reset_index(drop=True)
        volumes = last5["volume"].fillna(0.0)
        price_stuck = abs(float(closes.iloc[-1]) - float(closes.iloc[0])) <= max(atr * 0.3, 0.06)
        volume_build = volumes.tail(3).mean() > max(volumes.head(2).mean(), 1.0) * 1.12
        if body_ratio >= 0.68 and close_strength >= 0.68 and closes.diff().fillna(0).gt(0).sum() >= 3:
            return "MOMENTUM" if side == Side.LONG else "REJECTION_HEAVY"
        if body_ratio >= 0.68 and sell_strength >= 0.68 and closes.diff().fillna(0).lt(0).sum() >= 3:
            return "MOMENTUM" if side == Side.SHORT else "REJECTION_HEAVY"
        if price_stuck and volume_build and abs(float(closes.iloc[-1]) - key_level) <= max(atr * 0.28, 0.08):
            return "ABSORPTION"
        if upper_wick >= 0.32 and side == Side.LONG:
            return "REJECTION_HEAVY"
        if lower_wick >= 0.32 and side == Side.SHORT:
            return "REJECTION_HEAVY"
        if close_strength >= 0.58:
            return "BUYER_PRESSURE"
        if sell_strength >= 0.58:
            return "SELLER_PRESSURE"
        return "ABSORPTION"

    @staticmethod
    def _volume_state(recent: pd.DataFrame, compression_state: str, level_test_count: int) -> tuple[str, float]:
        volume = recent["volume"].fillna(0.0)
        if volume.max() <= 0:
            return "WEAK", 0.0
        recent_avg = float(volume.tail(5).mean())
        baseline = float(volume.tail(15).head(10).mean()) if len(volume) >= 10 else recent_avg
        rvol = recent_avg / max(baseline, 1.0)
        rising = volume.tail(4).is_monotonic_increasing
        if compression_state in {"TIGHT", "MODERATE"} and rvol <= 0.82 and level_test_count >= 2:
            return "DRY_COMPRESSION", rvol
        if rvol >= 1.35 and rising:
            return "CONFIRMED", rvol
        if rvol >= 1.18:
            return "EXPANDING", rvol
        if rising or (0.95 <= rvol <= 1.18):
            return "BUILDING", rvol
        return "WEAK", rvol

    @staticmethod
    def _exhaustion_state(recent: pd.DataFrame, side: Side, distance_pct: float, distance_atr: float, atr: float) -> str:
        closes = recent["close"]
        move = float(closes.iloc[-1] - closes.iloc[-4]) if len(closes) >= 4 else 0.0
        directional_move = move if side == Side.LONG else -move
        if distance_pct >= 2.2 or distance_atr >= 1.95:
            return "CHASE_RISK_HIGH"
        if distance_pct >= 1.45 or distance_atr >= 1.3 or directional_move >= atr * 1.8:
            return "EXTENDED"
        if distance_pct <= 0.7 and directional_move <= atr * 1.1:
            return "FRESH"
        return "ACCEPTABLE"

    @staticmethod
    def _time_context(timestamp: pd.Timestamp | None) -> str:
        if timestamp is None or pd.isna(timestamp):
            current = datetime.now().time()
        else:
            current = timestamp.to_pydatetime().time()
        if current <= time(10, 15):
            return "OPENING"
        if current >= time(14, 15):
            return "LATE"
        return "MIDDAY"

    @staticmethod
    def _trap_flags(
        *,
        recent: pd.DataFrame,
        side: Side,
        key_level: float,
        atr: float,
        compression_state: str,
        level_test_count: int,
        level_test_quality: str,
        vwap_state: str,
        pressure_state: str,
        volume_state: str,
        exhaustion_state: str,
        time_context: str,
    ) -> list[str]:
        flags: list[str] = []
        last3 = recent.tail(3)
        tolerance = max(atr * 0.18, 0.05)
        if side == Side.LONG:
            false_break = ((last3["high"] > key_level + tolerance) & (last3["close"] < key_level)).sum()
        else:
            false_break = ((last3["low"] < key_level - tolerance) & (last3["close"] > key_level)).sum()
        if false_break:
            flags.append("false breakout risk")
        if volume_state == "WEAK":
            flags.append("weak volume")
        if level_test_count <= 1:
            flags.append("thin level memory")
        if level_test_quality == "LOOSE":
            flags.append("loose level tests")
        if vwap_state == "VWAP_CHOPPY":
            flags.append("vwap chop")
        if pressure_state == "REJECTION_HEAVY":
            flags.append("heavy rejection")
        if compression_state == "NONE" and pressure_state == "ABSORPTION":
            flags.append("no clean build")
        if exhaustion_state in {"EXTENDED", "CHASE_RISK_HIGH"}:
            flags.append("extended move")
        if time_context == "LATE":
            flags.append("late session")
        return list(dict.fromkeys(flags))

    @staticmethod
    def _trap_risk(flags: list[str]) -> str:
        if "false breakout risk" in flags and len(flags) >= 2:
            return "HIGH"
        if "extended move" in flags and len(flags) >= 2:
            return "HIGH"
        if len(flags) >= 4:
            return "HIGH"
        if len(flags) >= 2:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _breakout_probability(
        *,
        structure_state: str,
        compression_state: str,
        level_test_count: int,
        level_test_quality: str,
        pressure_state: str,
        volume_state: str,
        vwap_state: str,
        trap_risk: str,
    ) -> str:
        score = 0
        if structure_state in {"HH_HL_BUILDING", "LH_LL_BUILDING"}:
            score += 2
        if compression_state == "TIGHT":
            score += 2
        elif compression_state == "MODERATE":
            score += 1
        if level_test_count >= 3:
            score += 3
        elif level_test_count == 2:
            score += 2
        elif level_test_count == 1:
            score += 1
        if level_test_quality == "TIGHT":
            score += 1
        if pressure_state in {"BUYER_PRESSURE", "SELLER_PRESSURE", "MOMENTUM", "ABSORPTION"}:
            score += 1
        if volume_state in {"BUILDING", "EXPANDING", "CONFIRMED"}:
            score += 1
        if vwap_state in {"ABOVE_HOLD", "BELOW_REJECT", "VWAP_RECLAIMED"}:
            score += 1
        if trap_risk == "HIGH":
            score -= 3
        elif trap_risk == "MEDIUM":
            score -= 1
        if score >= 7:
            return "HIGH"
        if score >= 4:
            return "MEDIUM"
        return "LOW"
