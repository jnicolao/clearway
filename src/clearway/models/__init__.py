"""Model clients.

Everything that talks to a model lives behind this package, so swapping a
provider or a tier is a config change rather than a rewrite. Every model is
local and every weight is Apache-2.0: Ollama serves the vision-language
model, ColQwen2 does retrieval. Nothing here calls a paid API.
"""

from clearway.models.config import ModelConfig, Tier

__all__ = ["ModelConfig", "Tier"]
