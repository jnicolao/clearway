"""Check the local Ollama is reachable and has the models Clearway expects.

    uv run python scripts/verify_ollama.py

Prints what is installed rather than assuming the defaults are right — a
wrong model tag should be obvious here, not a confusing failure in week six.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from clearway.models.config import ModelConfig  # noqa: E402
from clearway.models.vlm import OllamaError, installed_models  # noqa: E402


def main() -> int:
    config = ModelConfig.from_env()
    print(f"host      {config.host}")
    print(f"fast tier {config.fast}")
    print(f"deep tier {config.deep}")
    print(f"retriever {config.retriever}\n")

    try:
        available = installed_models(config)
    except Exception as exc:  # noqa: BLE001 — any transport failure means the same thing
        print(f"cannot reach Ollama at {config.host}: {exc}")
        print("start it with:  ollama serve")
        return 1

    if not available:
        print("Ollama is running but has no models pulled.")
    else:
        print("installed:")
        for name in available:
            print(f"  {name}")

    missing = [m for m in (config.fast, config.deep) if m not in available]
    if missing:
        print("\nmissing — pull them:")
        for name in missing:
            print(f"  ollama pull {name}")
        return 1

    print("\nboth tiers present.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OllamaError as exc:
        print(exc)
        raise SystemExit(1) from exc
