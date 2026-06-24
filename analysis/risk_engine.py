from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TradePlan:
    entry_low: float
    entry_high: float
    stop_loss: float
    target1: float
    target2: float
    rr: float
    trailing_note: str
    extended: bool


def build_trade_plan(direction: str, ltp: float, atr: float, trigger: float, support: float, resistance: float, vwap: float, ema21: float) -> TradePlan:
    atr = max(float(atr or 0), ltp * 0.004)
    buffer = max(atr * 0.12, ltp * 0.001)
    extended = abs(ltp - vwap) > atr * 1.8 if vwap else False
    if direction == "LONG":
        entry_low = min(ltp, trigger + buffer)
        entry_high = max(ltp, trigger + atr * 0.25)
        stop = min(support, ema21, trigger - atr * 0.55, entry_low - atr * 0.65)
        risk = max(entry_high - stop, atr * 0.35)
        target1 = max(resistance, entry_high + risk)
        target2 = max(target1 + risk, entry_high + risk * 2)
        trailing = "After T1, move SL near entry; trail below EMA21 or VWAP on 5m closes."
    else:
        entry_high = max(ltp, trigger - buffer)
        entry_low = min(ltp, trigger - atr * 0.25)
        stop = max(resistance, ema21, trigger + atr * 0.55, entry_high + atr * 0.65)
        risk = max(stop - entry_low, atr * 0.35)
        target1 = min(support, entry_low - risk)
        target2 = min(target1 - risk, entry_low - risk * 2)
        trailing = "After T1, move SL near entry; trail above EMA21 or VWAP on 5m closes."
    reward = abs(target2 - ((entry_low + entry_high) / 2))
    rr = reward / max(risk, 0.01)
    return TradePlan(round(float(entry_low), 2), round(float(entry_high), 2), round(float(stop), 2), round(float(target1), 2), round(float(target2), 2), round(float(rr), 2), trailing, extended)
