"""Model selection, driven by environment.

Two tiers exist so cost-per-document is a measurable number rather than a
fixed one: FAST handles the bulk, DEEP handles what FAST wasn't confident
about. The escalation policy itself belongs with the extraction agent — this
module only decides which model each tier names.
"""

import os
from dataclasses import dataclass
from enum import Enum

DEFAULT_FAST = "claude-haiku-4-5"
DEFAULT_DEEP = "claude-opus-5"
DEFAULT_EMBED = "jina-embeddings-v4"


class Tier(str, Enum):
    FAST = "fast"
    DEEP = "deep"


# USD per million tokens. Cached from Anthropic's published rates on
# 2026-09-11 — re-check before quoting any cost figure, and never publish an
# estimate from this table as if it were measured.
PRICES: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
}


@dataclass(frozen=True)
class ModelConfig:
    fast: str = DEFAULT_FAST
    deep: str = DEFAULT_DEEP
    embed: str = DEFAULT_EMBED

    @classmethod
    def from_env(cls) -> "ModelConfig":
        return cls(
            fast=os.environ.get("CLEARWAY_MODEL_FAST", DEFAULT_FAST),
            deep=os.environ.get("CLEARWAY_MODEL_DEEP", DEFAULT_DEEP),
            embed=os.environ.get("CLEARWAY_MODEL_EMBED", DEFAULT_EMBED),
        )

    def model_for(self, tier: Tier) -> str:
        return self.deep if tier is Tier.DEEP else self.fast


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Cost of one call, or None if the model isn't in the cached price table."""
    price = PRICES.get(model)
    if price is None:
        return None
    in_rate, out_rate = price
    return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000
