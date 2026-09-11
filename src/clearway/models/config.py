"""Model selection, driven by environment.

Everything runs locally: Ollama serves the vision-language model, ColQwen2
does retrieval. Nothing here calls a paid API, and every weight named below
is Apache-2.0 — ColPali is deliberately not an option because its PaliGemma
backbone carries the Gemma licence.

Tiers survive the move off hosted inference, but they mean something
different now. There is no per-token price to trade against; the tradeoff is
memory and wall-clock. FAST is a smaller model that answers quickly, DEEP is
the larger one worth the reload when FAST wasn't confident.
"""

import os
from dataclasses import dataclass
from enum import StrEnum

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_FAST = "qwen2.5vl:3b"
DEFAULT_DEEP = "qwen2.5vl:7b"
DEFAULT_RETRIEVER = "vidore/colqwen2-v1.0"


class Tier(StrEnum):
    FAST = "fast"
    DEEP = "deep"


@dataclass(frozen=True)
class ModelConfig:
    host: str = DEFAULT_HOST
    fast: str = DEFAULT_FAST
    deep: str = DEFAULT_DEEP
    retriever: str = DEFAULT_RETRIEVER

    @classmethod
    def from_env(cls) -> "ModelConfig":
        return cls(
            host=os.environ.get("OLLAMA_HOST", DEFAULT_HOST).rstrip("/"),
            fast=os.environ.get("CLEARWAY_MODEL_FAST", DEFAULT_FAST),
            deep=os.environ.get("CLEARWAY_MODEL_DEEP", DEFAULT_DEEP),
            retriever=os.environ.get("CLEARWAY_RETRIEVER", DEFAULT_RETRIEVER),
        )

    def model_for(self, tier: Tier) -> str:
        return self.deep if tier is Tier.DEEP else self.fast
