from __future__ import annotations

import math

from scanner_brain.config.scoring_profiles import ScoringProfile
from scanner_brain.core.enums import EntryType, Side
from scanner_brain.core.models import StockSnapshot, TechnicalAssessment


class TechnicalValidationEngine:
    def __init__(self, profile: ScoringProfile) -> None:
        self.profile = profile

    def evaluate(self, stock: StockSnapshot) -> TechnicalAssessment:
        vwap = stock.vwap_proxy
        above_vwap = stock.ltp >= vwap
        near_high = stock.price_position >= 0.72
        near_low = stock.price_position <= 0.28
        long_score = max(stock.change_pct, 0) * 7 + max(stock.intraday_move_pct, 0) * 8 + stock.price_position * 32
        short_score = max(-stock.change_pct, 0) * 7 + max(-stock.intraday_move_pct, 0) * 8 + (1 - stock.price_position) * 32
        side = Side.LONG if long_score >= short_score else Side.SHORT

        passed: list[str] = []
        missing: list[str] = []
        failed: list[str] = []
        contradictions: list[str] = []
        reasons: list[str] = []
        atr_proxy = max(stock.day_range * 0.45, stock.ltp * 0.0075)
        vwap_distance = abs(stock.ltp - vwap)
        vwap_distance_pct = (vwap_distance / max(vwap, 0.01)) * 100.0
        vwap_distance_atr = vwap_distance / max(atr_proxy, 0.05)

        change_ok = stock.change_pct > 0 if side == Side.LONG else stock.change_pct < 0
        if change_ok:
            passed.append("stock momentum aligned")
            reasons.append(f"Price change {stock.change_pct:+.2f}% supports {side.value}")
        else:
            failed.append("stock momentum against setup")
            contradictions.append("price change opposes selected side")

        vwap_ok = above_vwap if side == Side.LONG else not above_vwap
        if vwap_ok:
            passed.append("VWAP/open proxy supportive")
            reasons.append("Price is on the right side of VWAP/open proxy")
        else:
            failed.append("VWAP/open proxy not supportive")
            contradictions.append("VWAP context conflicts")

        location_ok = near_high if side == Side.LONG else near_low
        if location_ok:
            passed.append("price located near breakout side")
        else:
            missing.append("breakout-side location not clean")

        gap = stock.gap_pct
        if abs(gap) >= self.profile.strong_gap_pct and ((gap > 0 and side == Side.LONG) or (gap < 0 and side == Side.SHORT)):
            passed.append("strong aligned gap")
            reasons.append(f"Opening gap {gap:+.2f}% is aligned")
        elif abs(gap) >= self.profile.meaningful_gap_pct:
            missing.append("gap context mixed")
        else:
            missing.append("no meaningful gap")

        estimated_rvol = self._volume_quality(stock.volume)
        volume_confirmed = False
        if stock.raw.get("liquidity_mode") == "snapshot_fallback":
            missing.append("live volume unavailable; snapshot-mode ranking")
            reasons.append("Snapshot fallback is using price action because live volume is unavailable")
        elif estimated_rvol >= self.profile.volume_spike_ratio:
            passed.append("volume confirmation present")
            reasons.append(f"Volume quality {estimated_rvol:.1f}x")
            volume_confirmed = True
        else:
            missing.append("volume confirmation modest")

        bullish_structure = stock.ltp > stock.open >= stock.prev_close or (stock.low > min(stock.open, stock.prev_close) and near_high)
        bearish_structure = stock.ltp < stock.open <= stock.prev_close or (stock.high < max(stock.open, stock.prev_close) and near_low)
        if (side == Side.LONG and bullish_structure) or (side == Side.SHORT and bearish_structure):
            passed.append("intraday structure valid")
        else:
            missing.append("structure not fully confirmed")

        resistance = stock.high
        support = stock.low
        buffer = stock.ltp * self.profile.breakout_buffer_pct / 100.0
        if side == Side.LONG:
            cleared = stock.ltp >= resistance - max(buffer, stock.day_range * 0.08)
            trigger = resistance
        else:
            cleared = stock.ltp <= support + max(buffer, stock.day_range * 0.08)
            trigger = support
        if cleared:
            passed.append("key level context favorable")
        else:
            missing.append("key level not fully cleared")

        reclaimed_vwap = (
            (stock.open <= vwap <= stock.ltp and side == Side.LONG)
            or (stock.open >= vwap >= stock.ltp and side == Side.SHORT)
        )
        vwap_support = (
            (
                side == Side.LONG
                and stock.low <= vwap * 1.002
                and stock.ltp >= vwap
                and vwap_distance_pct <= self.profile.acceptable_vwap_distance_pct
            )
            or (
                side == Side.SHORT
                and stock.high >= vwap * 0.998
                and stock.ltp <= vwap
                and vwap_distance_pct <= self.profile.acceptable_vwap_distance_pct
            )
        )
        breakout_near_vwap = abs(trigger - vwap) / max(vwap, 0.01) * 100.0 <= self.profile.breakout_near_vwap_pct

        entry_type, entry_reason = self._entry_quality(
            side=side,
            vwap_distance_pct=vwap_distance_pct,
            vwap_distance_atr=vwap_distance_atr,
            intraday_move_pct=stock.intraday_move_pct,
            vwap_ok=vwap_ok,
            breakout_near_vwap=breakout_near_vwap,
            reclaimed_vwap=reclaimed_vwap,
            vwap_support=vwap_support,
            volume_confirmed=volume_confirmed,
        )
        reasons.append(entry_reason)

        if entry_type == EntryType.IDEAL:
            passed.append("ideal entry near VWAP")
        elif entry_type == EntryType.ACCEPTABLE:
            passed.append("acceptable VWAP distance")
        elif entry_type == EntryType.RISKY:
            missing.append("entry risk elevated; price stretched from VWAP")
            contradictions.append("trade is not near ideal VWAP location")
        else:
            failed.append("chasing breakout far from VWAP")
            contradictions.append("price extended from VWAP/open proxy")

        if vwap_distance_pct >= self.profile.extended_from_vwap_pct or vwap_distance_atr >= self.profile.risky_vwap_distance_atr:
            contradictions.append("price extended from VWAP/open proxy")

        base_score = long_score if side == Side.LONG else short_score
        score = base_score + len(passed) * 6 - len(failed) * 8 - len(contradictions) * 5
        if entry_type == EntryType.IDEAL:
            score += 10.0
        elif entry_type == EntryType.ACCEPTABLE:
            score += 4.0
        elif entry_type == EntryType.RISKY:
            score -= 10.0
        else:
            score -= 26.0
        score = max(0.0, min(100.0, score))
        setup_type = self._setup_type(side, location_ok, abs(gap), vwap_ok, reclaimed_vwap, vwap_support)
        return TechnicalAssessment(
            side=side,
            setup_type=setup_type,
            score=score,
            entry_type=entry_type,
            entry_reason=entry_reason,
            passed=passed,
            missing=missing,
            failed=failed,
            contradictions=contradictions,
            reasons=reasons,
            support=support,
            resistance=resistance,
            trigger=trigger,
            atr_proxy=atr_proxy,
            vwap_distance_pct=round(vwap_distance_pct, 2),
            vwap_distance_atr=round(vwap_distance_atr, 2),
        )

    @staticmethod
    def _volume_quality(volume: float) -> float:
        if volume <= 0:
            return 0.0
        return max(0.5, min(2.2, math.log10(volume) / 4.3))

    @staticmethod
    def _setup_type(side: Side, location_ok: bool, gap_abs: float, vwap_ok: bool, reclaimed_vwap: bool, vwap_support: bool) -> str:
        if reclaimed_vwap:
            return "VWAP reclaim breakout" if side == Side.LONG else "VWAP rejection breakdown"
        if vwap_support and vwap_ok:
            return "VWAP pullback continuation"
        if location_ok and vwap_ok:
            return "Breakout continuation" if side == Side.LONG else "Breakdown continuation"
        if gap_abs >= 0.35 and vwap_ok:
            return "Gap continuation"
        return "Momentum watch"

    def _entry_quality(
        self,
        *,
        side: Side,
        vwap_distance_pct: float,
        vwap_distance_atr: float,
        intraday_move_pct: float,
        vwap_ok: bool,
        breakout_near_vwap: bool,
        reclaimed_vwap: bool,
        vwap_support: bool,
        volume_confirmed: bool,
    ) -> tuple[EntryType, str]:
        directional_move = intraday_move_pct if side == Side.LONG else -intraday_move_pct
        supportive_vwap_action = vwap_support or (reclaimed_vwap and vwap_distance_pct <= self.profile.acceptable_vwap_distance_pct)
        if not vwap_ok:
            return EntryType.CHASING, "Price is on the wrong side of VWAP, so this breakout should not be chased."

        if (
            (
                vwap_distance_pct >= self.profile.extended_from_vwap_pct
                or vwap_distance_atr >= self.profile.risky_vwap_distance_atr
            )
            and directional_move >= self.profile.chasing_move_pct
            and not supportive_vwap_action
        ):
            return EntryType.CHASING, "Price is far from VWAP and the move looks extended; avoid chasing this breakout."

        if (
            vwap_distance_pct <= self.profile.ideal_vwap_distance_pct
            and vwap_distance_atr <= self.profile.ideal_vwap_distance_atr
            and (breakout_near_vwap or supportive_vwap_action)
            and volume_confirmed
        ):
            return EntryType.IDEAL, "Breakout is happening near VWAP with support and volume confirmation."

        if (
            vwap_distance_pct <= self.profile.acceptable_vwap_distance_pct
            and vwap_distance_atr <= self.profile.acceptable_vwap_distance_atr
            and (breakout_near_vwap or supportive_vwap_action)
        ):
            return EntryType.ACCEPTABLE, "Price is still close enough to VWAP for a manageable entry."

        return EntryType.RISKY, "Price is tradable but stretched from VWAP; wait for a pullback before entry."
