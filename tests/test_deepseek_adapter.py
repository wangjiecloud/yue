import base64
import json

import httpx
import pytest
from tests.conftest import make_settings

from yue_backend.adapters.deepseek import (
    PROMPT_VERSION,
    DeepSeekClient,
    ModelNotConfigured,
    ModelRequestError,
    ModelResponseError,
    _strip_code_fences,
)
from yue_backend.demo import build_ten_making_plan


def make_client(handler, tmp_path, **overrides) -> DeepSeekClient:
    settings = make_settings(
        tmp_path,
        deepseek_base_url="http://model.local/v1",
        deepseek_api_key="test-key",
        deepseek_model="deepseek-v4.1-flash",
        **overrides,
    )
    transport = httpx.MockTransport(handler)
    return DeepSeekClient(settings, transport=transport)


def ok_response(payload, status=200):
    content = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return httpx.Response(
        status,
        json={"choices": [{"message": {"content": content}}]},
    )


def test_analyze_image_returns_raw_plan(tmp_path):
    plan = build_ten_making_plan()
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        body = json.loads(request.content)
        captured["body"] = body
        return ok_response(plan.model_dump(mode="json"))

    client = make_client(handler, tmp_path)
    result = client.analyze_image(b"image-bytes", mime_type="image/png", grade=1, max_attempts=1)
    assert result.raw["planId"] == plan.planId
    assert captured["url"] == "http://model.local/v1/chat/completions"
    assert captured["auth"] == "Bearer test-key"
    assert captured["body"]["model"] == "deepseek-v4.1-flash"
    assert captured["body"]["response_format"] == {"type": "json_object"}
    user_content = captured["body"]["messages"][1]["content"]
    assert user_content[1]["type"] == "image_url"
    assert user_content[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert base64.b64decode(user_content[1]["image_url"]["url"].split(",", 1)[1]) == b"image-bytes"


def test_workspace_prefix_is_only_a_label(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "continue-proxy/deepseek-v4.1-flash"
        return ok_response(build_ten_making_plan().model_dump(mode="json"))

    client = make_client(handler, tmp_path, deepseek_workspace="continue-proxy")
    client.analyze_image(b"x", mime_type="image/png", max_attempts=1)


def test_code_fences_are_stripped(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        payload = (
            "```json\n" + json.dumps(build_ten_making_plan().model_dump(mode="json")) + "\n```"
        )
        return ok_response(payload)

    client = make_client(handler, tmp_path)
    result = client.analyze_image(b"x", mime_type="image/png", max_attempts=1)
    assert result.raw["schemaVersion"] == 1


def test_invalid_json_raises_response_error(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return ok_response("not json at all")

    client = make_client(handler, tmp_path)
    with pytest.raises(ModelResponseError):
        client.analyze_image(b"x", mime_type="image/png", max_attempts=1)


def test_auth_failure_is_not_retried(tmp_path):
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(401, json={"error": "bad key"})

    client = make_client(handler, tmp_path)
    with pytest.raises(ModelRequestError) as excinfo:
        client.analyze_image(b"x", mime_type="image/png", max_attempts=3)
    assert excinfo.value.status == 401
    assert not excinfo.value.retryable
    assert calls["count"] == 1


def test_server_error_is_retried(tmp_path):
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(503, json={"error": "busy"})
        return ok_response(build_ten_making_plan().model_dump(mode="json"))

    client = make_client(handler, tmp_path)
    result = client.analyze_image(b"x", mime_type="image/png", max_attempts=3)
    assert result.attempts == 2
    assert calls["count"] == 2


def test_response_format_fallback_on_bad_request(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if "response_format" in body:
            return httpx.Response(400, text="response_format is not supported")
        return ok_response(build_ten_making_plan().model_dump(mode="json"))

    client = make_client(handler, tmp_path)
    result = client.analyze_image(b"x", mime_type="image/png", max_attempts=1)
    assert result.raw["planId"]


def test_missing_configuration_raises(tmp_path):
    settings = make_settings(tmp_path)
    client = DeepSeekClient(settings)
    with pytest.raises(ModelNotConfigured):
        client.analyze_image(b"x", mime_type="image/png", max_attempts=1)


def test_system_prompt_includes_schema_and_safety_rules():
    from yue_backend.adapters.deepseek import SYSTEM_PROMPT

    assert "不可信数据" in SYSTEM_PROMPT
    assert "JSON Schema" in SYSTEM_PROMPT
    assert "{schema}" in SYSTEM_PROMPT
    assert PROMPT_VERSION == "p1-v1"


def test_strip_code_fences_variants():
    assert _strip_code_fences("```json\n{}\n```") == "{}"
    assert _strip_code_fences("```\n{}\n```") == "{}"
    assert _strip_code_fences("{}") == "{}"
