"""Jina Embeddings v4 — hosted multi-vector page embeddings.

This is what replaces self-hosted ColPali. v4 exposes both a single-vector
mode and a multi-vector (late-interaction) mode, so the retrieval design
survives having no GPU.

UNVERIFIED, do not trust until confirmed against a live call:

  * `return_multivector` — documented for the local transformers path;
    whether the hosted endpoint accepts it is not confirmed by any source.
  * base64 images — the published example passes an image URL only.
  * the multi-vector response shape — not documented anywhere reachable.

`scripts/verify_jina.py` makes exactly one real call and prints what comes
back. Run it first, then delete whichever branch below turns out to be dead.
Parsing is deliberately tolerant of both shapes in the meantime.
"""

import os
from dataclasses import dataclass
from typing import Any

import httpx2 as httpx

API_URL = "https://api.jina.ai/v1/embeddings"
TIMEOUT = 120.0


@dataclass(frozen=True)
class PageEmbedding:
    index: int
    vectors: list[list[float]]  # one row for single-vector, many for multi-vector

    @property
    def is_multivector(self) -> bool:
        return len(self.vectors) > 1


class JinaError(RuntimeError):
    pass


def _api_key() -> str:
    key = os.environ.get("JINA_API_KEY", "").strip()
    if not key:
        raise JinaError("JINA_API_KEY is not set. Get a key at https://jina.ai/embeddings")
    return key


def build_request(
    inputs: list[dict[str, str]],
    *,
    model: str = "jina-embeddings-v4",
    task: str = "retrieval",
    multivector: bool = True,
) -> dict[str, Any]:
    """The request body. Each input is {"text": ...} or {"image": ...}."""
    body: dict[str, Any] = {"model": model, "task": task, "input": inputs}
    if multivector:
        body["return_multivector"] = True
    return body


def parse_response(payload: dict[str, Any]) -> list[PageEmbedding]:
    """Read embeddings out of a response, tolerating either vector shape.

    A single-vector response gives `embedding` as list[float]; a
    multi-vector one is expected to give list[list[float]]. Both are
    normalised to a list of rows.
    """
    data = payload.get("data")
    if not isinstance(data, list):
        raise JinaError(f"no 'data' array in response: {sorted(payload)}")

    out: list[PageEmbedding] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise JinaError(f"data[{i}] is not an object")
        vectors = item.get("embedding") or item.get("embeddings")
        if not isinstance(vectors, list) or not vectors:
            raise JinaError(f"data[{i}] has no usable embedding")
        rows = vectors if isinstance(vectors[0], list) else [vectors]
        out.append(PageEmbedding(index=item.get("index", i), vectors=rows))
    return out


def embed(
    inputs: list[dict[str, str]],
    *,
    model: str = "jina-embeddings-v4",
    task: str = "retrieval",
    multivector: bool = True,
) -> list[PageEmbedding]:
    response = httpx.post(
        API_URL,
        headers={"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"},
        json=build_request(inputs, model=model, task=task, multivector=multivector),
        timeout=TIMEOUT,
    )
    if response.status_code >= 400:
        raise JinaError(f"HTTP {response.status_code}: {response.text[:400]}")
    return parse_response(response.json())
