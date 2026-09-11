"""Vision-language calls against the Anthropic API.

Deliberately thin: one function that sends page images plus a prompt and
returns text and token usage. Usage is returned on every call because
cost-per-document is one of the numbers the eval harness has to report, and
a client that throws usage away makes that number unrecoverable.
"""

import base64
from dataclasses import dataclass
from typing import Any

import anthropic

from clearway.models.config import ModelConfig, Tier, cost_usd

DEFAULT_MAX_TOKENS = 4096


@dataclass(frozen=True)
class VlmResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    stop_reason: str | None

    @property
    def cost_usd(self) -> float | None:
        return cost_usd(self.model, self.input_tokens, self.output_tokens)


def image_block(data: bytes, media_type: str = "image/png") -> dict[str, Any]:
    """A page image as an Anthropic content block."""
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": base64.standard_b64encode(data).decode("utf-8"),
        },
    }


def _text_of(content: list[Any]) -> str:
    return "\n".join(b.text for b in content if getattr(b, "type", None) == "text")


def extract(
    images: list[bytes],
    prompt: str,
    *,
    tier: Tier = Tier.FAST,
    config: ModelConfig | None = None,
    client: Any | None = None,
    system: str | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    media_type: str = "image/png",
) -> VlmResult:
    """Send images plus a prompt to the tier's model.

    `client` is injectable so tests can run without a key or a network call.
    Thinking is left unset on purpose: Opus 5 runs adaptive thinking by
    default, and Haiku 4.5 does not take the adaptive form — omitting the
    parameter is correct for both, so there is no branch here.
    """
    config = config or ModelConfig.from_env()
    client = client or anthropic.Anthropic()
    model = config.model_for(tier)

    content: list[dict[str, Any]] = [image_block(img, media_type) for img in images]
    content.append({"type": "text", "text": prompt})

    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": content}],
    }
    if system is not None:
        kwargs["system"] = system

    response = client.messages.create(**kwargs)

    return VlmResult(
        text=_text_of(response.content),
        model=getattr(response, "model", model),
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        stop_reason=getattr(response, "stop_reason", None),
    )
