"""Vision-language calls against a local Ollama server.

Ollama reports token counts and nanosecond timings on every response, so the
throughput numbers the eval harness needs come free. That is the local
equivalent of the cost-per-document metric a hosted API would have given us:
pages per hour on known hardware, rather than dollars per page.
"""

import base64
from dataclasses import dataclass
from typing import Any

import httpx2 as httpx

from clearway.models.config import ModelConfig, Tier

TIMEOUT = 600.0  # a cold 7B load on a laptop is slow; this is not a hang
NS_PER_S = 1_000_000_000


@dataclass(frozen=True)
class VlmResult:
    text: str
    model: str
    prompt_tokens: int
    output_tokens: int
    total_ns: int
    load_ns: int
    eval_ns: int

    @property
    def total_seconds(self) -> float:
        return self.total_ns / NS_PER_S

    @property
    def tokens_per_second(self) -> float | None:
        """Generation throughput, excluding model load and prompt eval."""
        if self.eval_ns <= 0 or self.output_tokens <= 0:
            return None
        return self.output_tokens / (self.eval_ns / NS_PER_S)


class OllamaError(RuntimeError):
    pass


def encode_image(data: bytes) -> str:
    """Ollama wants raw base64 on `images` — no data: URI prefix."""
    return base64.standard_b64encode(data).decode("utf-8")


def build_request(
    model: str,
    images: list[bytes],
    prompt: str,
    *,
    system: str | None = None,
    json_format: bool = False,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    messages: list[dict[str, Any]] = []
    if system is not None:
        messages.append({"role": "system", "content": system})
    messages.append(
        {
            "role": "user",
            "content": prompt,
            "images": [encode_image(img) for img in images],
        }
    )

    body: dict[str, Any] = {"model": model, "messages": messages, "stream": False}
    if json_format:
        body["format"] = "json"
    if options:
        body["options"] = options
    return body


def parse_response(payload: dict[str, Any], fallback_model: str) -> VlmResult:
    message = payload.get("message")
    if not isinstance(message, dict):
        raise OllamaError(f"no 'message' in response: {sorted(payload)}")
    return VlmResult(
        text=message.get("content", ""),
        model=payload.get("model", fallback_model),
        prompt_tokens=int(payload.get("prompt_eval_count", 0)),
        output_tokens=int(payload.get("eval_count", 0)),
        total_ns=int(payload.get("total_duration", 0)),
        load_ns=int(payload.get("load_duration", 0)),
        eval_ns=int(payload.get("eval_duration", 0)),
    )


def extract(
    images: list[bytes],
    prompt: str,
    *,
    tier: Tier = Tier.FAST,
    config: ModelConfig | None = None,
    post: Any | None = None,
    system: str | None = None,
    json_format: bool = False,
    options: dict[str, Any] | None = None,
) -> VlmResult:
    """Send page images plus a prompt to the tier's model.

    `post` is injectable so tests exercise request building and response
    parsing without a running Ollama.
    """
    config = config or ModelConfig.from_env()
    model = config.model_for(tier)
    body = build_request(
        model, images, prompt, system=system, json_format=json_format, options=options
    )

    post = post or httpx.post
    response = post(f"{config.host}/api/chat", json=body, timeout=TIMEOUT)
    if response.status_code >= 400:
        raise OllamaError(f"HTTP {response.status_code}: {response.text[:400]}")
    return parse_response(response.json(), model)


def installed_models(config: ModelConfig | None = None, get: Any | None = None) -> list[str]:
    """Model tags this Ollama actually has, so a wrong default is obvious."""
    config = config or ModelConfig.from_env()
    get = get or httpx.get
    response = get(f"{config.host}/api/tags", timeout=30.0)
    if response.status_code >= 400:
        raise OllamaError(f"HTTP {response.status_code}: {response.text[:200]}")
    return sorted(m.get("name", "") for m in response.json().get("models", []))
