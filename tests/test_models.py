"""Model-layer tests. No network, no Ollama, no torch.

The HTTP transport is injected and the ColQwen2 wrapper is only exercised
for the parts that do not need weights — that is what keeps CI a ~10 second
job instead of a 2GB torch install.
"""

import base64
import json
from types import SimpleNamespace

import pytest

from clearway.models.config import DEFAULT_RETRIEVER, ModelConfig, Tier
from clearway.models.retrieval import ColQwen2Retriever
from clearway.models.vlm import (
    OllamaError,
    build_request,
    encode_image,
    extract,
    installed_models,
    parse_response,
)

CHAT_RESPONSE = {
    "model": "qwen2.5vl:3b",
    "message": {"role": "assistant", "content": '{"consignee": "ACME LTD"}'},
    "done": True,
    "total_duration": 5_191_566_416,
    "load_duration": 2_154_458,
    "prompt_eval_count": 1600,
    "prompt_eval_duration": 383_809_000,
    "eval_count": 298,
    "eval_duration": 4_799_921_000,
}


def fake_post(captured: dict, payload=None, status: int = 200):
    def _post(url, json=None, timeout=None):
        captured["url"] = url
        captured["body"] = json
        return SimpleNamespace(
            status_code=status,
            json=lambda: payload if payload is not None else CHAT_RESPONSE,
            text="boom",
        )

    return _post


def test_tier_selects_the_configured_model():
    cfg = ModelConfig(fast="small", deep="large")
    assert cfg.model_for(Tier.FAST) == "small"
    assert cfg.model_for(Tier.DEEP) == "large"


def test_config_strips_trailing_slash_from_host(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://box:11434/")
    assert ModelConfig.from_env().host == "http://box:11434"


def test_images_are_raw_base64_without_a_data_uri_prefix():
    encoded = encode_image(b"hello")
    assert encoded == "aGVsbG8="
    assert not encoded.startswith("data:")
    assert base64.standard_b64decode(encoded) == b"hello"


def test_build_request_puts_images_on_the_user_message():
    body = build_request("m", [b"a", b"b"], "Extract the consignee.")
    assert body["stream"] is False
    (message,) = body["messages"]
    assert message["role"] == "user"
    assert message["content"] == "Extract the consignee."
    assert len(message["images"]) == 2


def test_build_request_prepends_system_as_its_own_message():
    body = build_request("m", [], "go", system="You are terse.")
    assert [m["role"] for m in body["messages"]] == ["system", "user"]


def test_build_request_omits_optional_keys_by_default():
    body = build_request("m", [], "go")
    assert "format" not in body
    assert "options" not in body


def test_build_request_sets_json_format_when_asked():
    body = build_request("m", [], "go", json_format=True, options={"temperature": 0})
    assert body["format"] == "json"
    assert body["options"] == {"temperature": 0}


def test_extract_posts_to_the_chat_endpoint():
    captured: dict = {}
    result = extract(
        [b"\x89PNG"],
        "Extract the consignee.",
        config=ModelConfig(host="http://localhost:11434", fast="qwen2.5vl:3b"),
        post=fake_post(captured),
    )
    assert captured["url"] == "http://localhost:11434/api/chat"
    assert captured["body"]["model"] == "qwen2.5vl:3b"
    assert json.loads(result.text) == {"consignee": "ACME LTD"}


def test_throughput_is_computed_from_generation_time_only():
    result = extract([b"x"], "go", config=ModelConfig(), post=fake_post({}))
    # 298 tokens over 4.799921 s of eval time
    assert result.tokens_per_second == pytest.approx(298 / 4.799921, rel=1e-6)
    assert result.total_seconds == pytest.approx(5.191566416, rel=1e-9)


def test_throughput_is_none_when_nothing_was_generated():
    payload = CHAT_RESPONSE | {"eval_count": 0, "eval_duration": 0}
    result = extract([b"x"], "go", config=ModelConfig(), post=fake_post({}, payload))
    assert result.tokens_per_second is None


def test_extract_raises_on_an_http_error():
    with pytest.raises(OllamaError, match="HTTP 500"):
        extract([b"x"], "go", config=ModelConfig(), post=fake_post({}, status=500))


def test_parse_rejects_a_response_without_a_message():
    with pytest.raises(OllamaError):
        parse_response({"done": True}, "m")


def test_parse_tolerates_missing_timing_fields():
    result = parse_response({"message": {"content": "hi"}}, "fallback-model")
    assert result.model == "fallback-model"
    assert result.output_tokens == 0
    assert result.tokens_per_second is None


def test_installed_models_lists_tags():
    def _get(url, timeout=None):
        assert url.endswith("/api/tags")
        return SimpleNamespace(
            status_code=200,
            json=lambda: {"models": [{"name": "qwen2.5vl:7b"}, {"name": "qwen2.5vl:3b"}]},
            text="",
        )

    assert installed_models(ModelConfig(), get=_get) == ["qwen2.5vl:3b", "qwen2.5vl:7b"]


def test_retriever_defaults_to_the_apache_licensed_model():
    # ColPali is deliberately not the default: PaliGemma carries the Gemma licence.
    assert DEFAULT_RETRIEVER == "vidore/colqwen2-v1.0"
    assert "colpali" not in ColQwen2Retriever().model_id.lower()


def test_retriever_refuses_to_embed_before_load():
    with pytest.raises(RuntimeError, match="load"):
        ColQwen2Retriever().embed_queries(["bill of lading"])


def test_importing_the_package_does_not_require_torch():
    import sys

    assert "torch" not in sys.modules
    assert "colpali_engine" not in sys.modules
