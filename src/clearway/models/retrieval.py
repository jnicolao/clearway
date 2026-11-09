"""ColQwen2 — local multi-vector page retrieval.

This is what replaces both self-hosted ColPali and the hosted embedding API.
ColQwen2 is Apache-2.0 (Qwen2-VL-2B backbone); ColPali is not, because
PaliGemma ships under the Gemma licence, which is why it is absent here.

torch and colpali-engine are imported lazily inside `load()`. They are a
~2GB install and the rest of this package must stay importable without them
— that keeps CI fast and lets the request/response logic be tested on a
machine that will never run a model.

Install the extra when you actually need to index:

    uv sync --extra retrieval
"""

import logging
from dataclasses import dataclass
from typing import Any

from clearway.models.config import DEFAULT_RETRIEVER

log = logging.getLogger("clearway.retrieval")


def pick_device() -> str:
    """mps on Apple Silicon, cuda where present, cpu as the honest fallback."""
    import torch

    if torch.cuda.is_available():
        return "cuda:0"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def pick_dtype(device: str) -> Any:
    """bfloat16 on cuda, float16 on mps.

    MPS support for bfloat16 is uneven across torch releases and fails in
    ways that look like garbage output rather than an error, so float16 is
    the safe choice on Apple Silicon.
    """
    import torch

    return torch.bfloat16 if device.startswith("cuda") else torch.float16


@dataclass
class ColQwen2Retriever:
    """Thin wrapper over colpali-engine. Holds the model; call load() first."""

    model_id: str = DEFAULT_RETRIEVER
    device: str | None = None
    _model: Any = None
    _processor: Any = None

    def load(self) -> "ColQwen2Retriever":
        from colpali_engine.models import ColQwen2, ColQwen2Processor

        device = self.device or pick_device()
        log.info("loading %s on %s", self.model_id, device)
        self._model = ColQwen2.from_pretrained(
            self.model_id,
            torch_dtype=pick_dtype(device),
            device_map=device,
        ).eval()
        self._processor = ColQwen2Processor.from_pretrained(self.model_id)
        self.device = device
        return self

    def _require_loaded(self) -> None:
        if self._model is None or self._processor is None:
            raise RuntimeError("call load() before embedding")

    def embed_images(self, images: list[Any]) -> Any:
        """Multi-vector embeddings for page images (PIL Images)."""
        self._require_loaded()
        import torch

        batch = self._processor.process_images(images).to(self._model.device)
        with torch.no_grad():
            return self._model(**batch)

    def embed_queries(self, queries: list[str]) -> Any:
        self._require_loaded()
        import torch

        batch = self._processor.process_queries(queries).to(self._model.device)
        with torch.no_grad():
            return self._model(**batch)

    def score(self, query_embeddings: Any, page_embeddings: Any) -> Any:
        """Late-interaction (MaxSim) scores — the whole point of multi-vector."""
        self._require_loaded()
        return self._processor.score_multi_vector(query_embeddings, page_embeddings)
