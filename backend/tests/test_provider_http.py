"""Exercise the OpenAI-compatible provider against a mocked HTTP transport (Groq/Gemini wire format)."""

import json

import httpx
import pytest

from app.services.ai.provider import AIClient, CallContext, OpenAICompatProvider, RetryableAIError, ToolSpec


def make_provider(handler, name="groq", stream_usage=True) -> OpenAICompatProvider:
    p = OpenAICompatProvider(name, "https://example.test/v1", "key", {"primary": "m-primary", "fast": "m-fast", "vision": "m-vision"}, stream_usage=stream_usage)
    p._client = httpx.Client(transport=httpx.MockTransport(handler))
    return p


def test_generate_sends_openai_shape_and_parses_tool_calls():
    seen = {}

    def handler(request: httpx.Request):
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={
            "model": "m-fast",
            "choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": None, "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "search_materials", "arguments": "{\"query\": \"calvin cycle\"}"}}]}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 18},
        })

    p = make_provider(handler)
    result = p.generate(tier="fast", system="sys", messages=[{"role": "user", "content": "hi"}], max_tokens=100, tools=[ToolSpec("search_materials", "d", {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]})])
    assert seen["auth"] == "Bearer key"
    assert seen["body"]["model"] == "m-fast"
    assert seen["body"]["messages"][0] == {"role": "system", "content": "sys"}
    assert seen["body"]["tools"][0]["type"] == "function" and seen["body"]["tool_choice"] == "auto"
    assert result.tool_uses[0].name == "search_materials" and result.tool_uses[0].input == {"query": "calvin cycle"}
    assert result.input_tokens == 120 and result.output_tokens == 18 and result.provider == "groq"


def test_json_mode_sets_response_format():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "```json\n{\"value\": 3}\n```"}}], "usage": {}})

    from pydantic import BaseModel

    class Out(BaseModel):
        value: int

    p = make_provider(handler)
    parsed, _ = AIClient([p]).generate_structured(CallContext(feature="t"), Out, system="s", messages=[{"role": "user", "content": "u"}])
    assert parsed.value == 3
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert "JSON schema" in seen["body"]["messages"][0]["content"]


def test_stream_parses_sse_and_usage():
    chunks = [
        {"model": "m-primary", "choices": [{"delta": {"content": "Hel"}, "finish_reason": None}]},
        {"choices": [{"delta": {"content": "lo"}, "finish_reason": "stop"}]},
        {"choices": [], "x_groq": {"usage": {"prompt_tokens": 10, "completion_tokens": 2}}},
    ]
    body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"

    def handler(request):
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200, content=body.encode(), headers={"content-type": "text/event-stream"})

    p = make_provider(handler)
    items = list(p.stream(tier="primary", system="s", messages=[{"role": "user", "content": "u"}], max_tokens=50))
    assert items[:2] == ["Hel", "lo"]
    final = items[-1]
    assert final.text == "Hello" and final.input_tokens == 10 and final.output_tokens == 2 and final.model == "m-primary"


def test_rate_limit_is_retryable_and_falls_back(fresh_db):
    def limited(request):
        return httpx.Response(429, json={"error": "slow down"})

    def ok(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "fine"}}], "usage": {"prompt_tokens": 1, "completion_tokens": 1}})

    with pytest.raises(RetryableAIError):
        make_provider(limited).generate(tier="primary", system="s", messages=[], max_tokens=10)
    result, req_id = AIClient([make_provider(limited, "groq"), make_provider(ok, "gemini")]).generate(CallContext(feature="t"), system="s", messages=[{"role": "user", "content": "u"}])
    assert result.text == "fine" and result.provider == "gemini"
    from app.core import db as dbm

    row = dbm.get(dbm.AI_REQUESTS, req_id)
    assert row["status"] == "fallback" and [a["provider"] for a in row["attempts"]] == ["groq", "gemini"]


def test_auth_error_is_not_retried_silently():
    from app.core.errors import AIUnavailableError

    def unauthorized(request):
        return httpx.Response(401, json={"error": "bad key"})

    with pytest.raises(AIUnavailableError) as exc:
        make_provider(unauthorized).generate(tier="primary", system="s", messages=[], max_tokens=10)
    assert exc.value.code == "ai_auth"


def test_unconfigured_provider_is_skipped():
    p = OpenAICompatProvider("groq", "https://x", "", {"primary": "m"})
    with pytest.raises(RetryableAIError):
        p.generate(tier="primary", system="s", messages=[], max_tokens=10)
