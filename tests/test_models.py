"""Model-layer tests. No network, no keys — the Anthropic client is injected.

The Jina tests cover request building and both plausible response shapes,
since the hosted endpoint's multi-vector shape is unconfirmed.
"""

from types import SimpleNamespace

import pytest

from clearway.models.config import ModelConfig, Tier, cost_usd
from clearway.models.embeddings import JinaError, build_request, parse_response
from clearway.models.vlm import extract, image_block


class FakeMessages:
    def __init__(self, outer):
        self.outer = outer

    def create(self, **kwargs):
        self.outer.seen = kwargs
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="{}")],
            model=kwargs["model"],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=1600, output_tokens=40),
        )


class FakeClient:
    def __init__(self):
        self.seen: dict = {}
        self.messages = FakeMessages(self)


def test_tier_selects_the_configured_model():
    cfg = ModelConfig(fast="fast-model", deep="deep-model")
    assert cfg.model_for(Tier.FAST) == "fast-model"
    assert cfg.model_for(Tier.DEEP) == "deep-model"


def test_cost_is_none_for_unpriced_models():
    assert cost_usd("some-future-model", 1000, 1000) is None


def test_cost_uses_the_cached_rates():
    # 1M input at $1 plus 1M output at $5 on the fast tier.
    assert cost_usd("claude-haiku-4-5", 1_000_000, 1_000_000) == pytest.approx(6.0)


def test_extract_sends_images_before_the_prompt():
    client = FakeClient()
    result = extract([b"\x89PNG"], "Extract the consignee.", client=client)
    content = client.seen["messages"][0]["content"]
    assert [b["type"] for b in content] == ["image", "text"]
    assert content[-1]["text"] == "Extract the consignee."
    assert result.input_tokens == 1600


def test_extract_omits_thinking_and_system_by_default():
    client = FakeClient()
    extract([b"x"], "go", client=client)
    assert "thinking" not in client.seen
    assert "system" not in client.seen


def test_extract_reports_cost_from_usage():
    client = FakeClient()
    result = extract([b"x"], "go", tier=Tier.FAST, client=client)
    # 1600 in at $1/M plus 40 out at $5/M
    assert result.cost_usd == pytest.approx((1600 * 1.0 + 40 * 5.0) / 1_000_000)


def test_image_block_is_base64():
    block = image_block(b"hello", "image/jpeg")
    assert block["source"]["media_type"] == "image/jpeg"
    assert block["source"]["data"] == "aGVsbG8="


def test_build_request_toggles_multivector():
    assert build_request([{"text": "x"}])["return_multivector"] is True
    assert "return_multivector" not in build_request([{"text": "x"}], multivector=False)


def test_parses_single_vector_response():
    out = parse_response({"data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]})
    assert len(out) == 1 and not out[0].is_multivector
    assert out[0].vectors == [[0.1, 0.2, 0.3]]


def test_parses_multi_vector_response():
    out = parse_response({"data": [{"index": 0, "embedding": [[0.1, 0.2], [0.3, 0.4]]}]})
    assert out[0].is_multivector and len(out[0].vectors) == 2


def test_rejects_a_response_it_cannot_read():
    with pytest.raises(JinaError):
        parse_response({"oops": 1})
    with pytest.raises(JinaError):
        parse_response({"data": [{"index": 0}]})
