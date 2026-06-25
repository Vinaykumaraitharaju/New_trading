from __future__ import annotations

from dataclasses import dataclass

from scanner_brain.config.scoring_profiles import adaptive_signal_components, reaction_profile_for_stock

from ..models import ComponentScore, ReactionResult, StructureResult


@dataclass(slots=True)
class UnifiedScore:
    total: int
    label: str
    reasons: list[str]
    components: dict[str, int]


class UnifiedScoringEngine:
    def __init__(self, elite_threshold: int, strong_threshold: int) -> None:
        self.elite_threshold = elite_threshold
        self.strong_threshold = strong_threshold

    def evaluate(
        self,
        *,
        reaction: ReactionResult,
        structure: StructureResult,
        sr: ComponentScore,
        pattern: ComponentScore,
        volume: ComponentScore,
        orderflow: ComponentScore,
        vwap: ComponentScore,
        volatility: ComponentScore,
        speed: ComponentScore,
        market_context: ComponentScore,
        buildup: ComponentScore,
        fake_move_penalty: ComponentScore,
        symbol: str = "",
        sector: str = "",
        raw: dict | None = None,
    ) -> UnifiedScore:
        components = {
            "reaction": reaction.score,
            "structure": structure.score,
            "sr": sr.score,
            "pattern": pattern.score,
            "volume": volume.score,
            "orderflow": orderflow.score,
            "vwap": vwap.score,
            "volatility": volatility.score,
            "speed": speed.score,
            "market": market_context.score,
            "buildup": buildup.score,
            "fake_move": fake_move_penalty.score,
        }
        profile = reaction_profile_for_stock(symbol, sector, raw)
        adjusted_components = adaptive_signal_components(components, profile)
        total_float = sum(adjusted_components.values())
        total = int(round(total_float))
        output_components = {name: int(round(value)) for name, value in adjusted_components.items()}
        if profile.name != "Balanced":
            output_components["adaptive_profile"] = int(round(total_float - sum(components.values())))
        label = "IGNORE"
        if total >= self.elite_threshold:
            label = "ELITE"
        elif total >= self.strong_threshold:
            label = "STRONG"
        reasons = (
            reaction.reasons
            + structure.reasons
            + sr.reasons
            + pattern.reasons
            + volume.reasons
            + orderflow.reasons
            + vwap.reasons
            + volatility.reasons
            + speed.reasons
            + market_context.reasons
            + buildup.reasons
            + fake_move_penalty.reasons
        )
        if profile.name != "Balanced":
            reasons = [f"Adaptive stock profile applied: {profile.name}"] + reasons
        return UnifiedScore(total=total, label=label, reasons=reasons, components=output_components)
