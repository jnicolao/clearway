"""Model clients.

Everything that talks to a model lives behind this package so swapping a
provider or a tier is a config change, not a rewrite. Nothing here runs
locally — Clearway calls hosted inference, which is both what production
looks like and what lets anyone clone the repo and run it.
"""

from clearway.models.config import ModelConfig, Tier

__all__ = ["ModelConfig", "Tier"]
