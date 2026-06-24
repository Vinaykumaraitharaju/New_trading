from __future__ import annotations

from dataclasses import dataclass

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
        total = sum(components.values())
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
        return UnifiedScore(total=total, label=label, reasons=reasons, components=components)
