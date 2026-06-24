from __future__ import annotations

import pandas as pd

from scanner_brain.config.scoring_profiles import FastFilterProfile


class CandidateFilterEngine:
    def __init__(self, profile: FastFilterProfile) -> None:
        self.profile = profile

    def shortlist(self, quotes: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, str]]]:
        if quotes.empty:
            return quotes, []
        df = quotes.copy()
        for col in ["ltp", "open", "high", "low", "prev_close", "volume", "change_pct"]:
            if col in df:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        rejected: list[dict[str, str]] = []
        tradable = df[(df["ltp"] >= self.profile.min_price) & (df["ltp"] <= self.profile.max_price)]
        for symbol in df.loc[~df.index.isin(tradable.index), "symbol"].astype(str).tolist():
            rejected.append({"symbol": symbol, "reason": "Outside price filter"})
        tradable = tradable[tradable["ltp"] >= self.profile.min_tradable_ltp].copy()
        if tradable.empty:
            return tradable, rejected

        day_range = (tradable["high"] - tradable["low"]).clip(lower=0)
        range_pct = (day_range / tradable["ltp"].clip(lower=0.01)) * 100.0
        low_movement = range_pct < self.profile.min_intraday_range_pct
        chaotic = range_pct > self.profile.max_chaos_range_pct
        open_wick_pct = ((tradable["open"] - tradable["prev_close"]).abs() / tradable["prev_close"].clip(lower=0.01)) * 100.0
        bad_wick = open_wick_pct > self.profile.max_open_wick_pct
        quality_block = low_movement | chaotic | bad_wick

        if "raw" in tradable:
            spreads = tradable["raw"].apply(self._spread_pct)
            wide_spread = spreads > self.profile.max_spread_pct
            quality_block = quality_block | wide_spread
            for symbol in tradable.loc[wide_spread, "symbol"].astype(str).tolist():
                rejected.append({"symbol": symbol, "reason": "Rejected by quality filter: spread too wide"})

        for symbol in tradable.loc[low_movement, "symbol"].astype(str).tolist():
            rejected.append({"symbol": symbol, "reason": "Rejected by quality filter: insufficient intraday movement"})
        for symbol in tradable.loc[chaotic, "symbol"].astype(str).tolist():
            rejected.append({"symbol": symbol, "reason": "Rejected by quality filter: chaotic oversized range"})
        for symbol in tradable.loc[bad_wick, "symbol"].astype(str).tolist():
            rejected.append({"symbol": symbol, "reason": "Rejected by quality filter: abnormal open/price behavior"})
        tradable = tradable.loc[~quality_block].copy()
        if tradable.empty:
            return tradable, rejected

        liquid = tradable[tradable["volume"] >= self.profile.min_volume]
        needs_snapshot_fallback = len(liquid) == 0 or (len(tradable) >= 20 and len(liquid) < 5)
        if not needs_snapshot_fallback:
            pool = liquid.copy()
            pool["liquidity_mode"] = "live_volume_confirmed"
            for symbol in tradable.loc[~tradable.index.isin(liquid.index), "symbol"].astype(str).tolist():
                rejected.append({"symbol": symbol, "reason": "Below volume filter"})
        else:
            pool = tradable.copy()
            pool["liquidity_mode"] = "snapshot_fallback"
            if not pool.empty:
                rejected.append(
                    {
                        "symbol": "SCAN",
                        "reason": "Live volume unavailable or too thin; using price-action snapshot fallback",
                    }
                )

        if pool.empty:
            return pool, rejected

        vwap_series = self._vwap_proxy(pool)
        day_range = (pool["high"] - pool["low"]).clip(lower=pool["ltp"] * 0.003)
        atr_proxy = (day_range * 0.45).clip(lower=pool["ltp"] * 0.0075)
        vwap_distance_pct = ((pool["ltp"] - vwap_series).abs() / vwap_series.clip(lower=0.01)) * 100.0
        vwap_distance_atr = (pool["ltp"] - vwap_series).abs() / atr_proxy.clip(lower=0.05)
        intraday_move_pct = ((pool["ltp"] - pool["open"]) / pool["open"].clip(lower=0.01)) * 100.0
        overextended_mask = (
            (
                (vwap_distance_pct >= self.profile.early_vwap_reject_pct)
                | (vwap_distance_atr >= self.profile.early_vwap_reject_atr)
            )
            & (intraday_move_pct.abs() >= self.profile.early_chasing_intraday_move_pct)
        )
        if overextended_mask.any():
            for symbol in pool.loc[overextended_mask, "symbol"].astype(str).tolist():
                rejected.append({"symbol": symbol, "reason": "Overextended from VWAP early filter -> chasing risk"})
            pool = pool.loc[~overextended_mask].copy()

        day_range = (pool["high"] - pool["low"]).clip(lower=pool["ltp"] * 0.003)
        pool = pool.assign(
            _fast_score=(pool["change_pct"].abs() * 14.0)
            + ((pool["ltp"] - pool["low"]) / day_range - 0.5).abs() * 20.0
            + (pool["volume"].clip(lower=1).pow(0.15) * 6.0)
            - vwap_distance_pct.loc[pool.index].clip(lower=0).mul(8.5)
        )
        return pool.sort_values("_fast_score", ascending=False).head(self.profile.max_candidates).drop(columns=["_fast_score"]), rejected

    @staticmethod
    def _vwap_proxy(df: pd.DataFrame) -> pd.Series:
        for column in ("vwap", "average_price", "avgPrice"):
            if column in df:
                values = pd.to_numeric(df[column], errors="coerce")
                if values.notna().any():
                    return values.fillna(pd.to_numeric(df.get("open", 0), errors="coerce")).clip(lower=0.01)
        return pd.to_numeric(df.get("open", 0), errors="coerce").fillna(pd.to_numeric(df.get("prev_close", 0), errors="coerce")).clip(lower=0.01)

    @staticmethod
    def _spread_pct(raw: object) -> float:
        if not isinstance(raw, dict):
            return 0.0
        bid = raw.get("bid") or raw.get("best_bid") or raw.get("bid_price")
        ask = raw.get("ask") or raw.get("best_ask") or raw.get("ask_price")
        try:
            bid_f = float(bid or 0)
            ask_f = float(ask or 0)
        except (TypeError, ValueError):
            return 0.0
        mid = (bid_f + ask_f) / 2.0
        if bid_f <= 0 or ask_f <= 0 or mid <= 0:
            return 0.0
        return abs(ask_f - bid_f) / mid * 100.0
