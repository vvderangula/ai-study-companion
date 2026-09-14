"""AI provider abstraction with fallback.

Every model call goes through ``AIClient``. It:
  * talks to providers through one OpenAI-compatible HTTP implementation
    (Groq first, Gemini as fallback, a deterministic fake for tests),
  * falls back to the next provider on rate limits, timeouts, 5xx, or invalid
    structured output,
  * records an ``ai_requests`` document with tokens, cost, latency, feature,
    prompt version, retrieval hits, tool calls and the per-provider attempt log,
  * validates structured output against a Pydantic schema before returning it.

Message format is the OpenAI chat format (role/content, tool_calls, tool role).
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core import db as dbm
from app.core.config import settings
from app.core.errors import AIUnavailableError
from app.core.logging import request_id_var

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# USD per million tokens (input, output). Approximate list prices; configurable by editing here.
PRICING: dict[str, tuple[float, float]] = {
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "llama-3.1-8b-instant": (0.05, 0.08),
    "meta-llama/llama-4-scout-17b-16e-instruct": (0.11, 0.34),
    "openai/gpt-oss-120b": (0.15, 0.75),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.0-flash": (0.10, 0.40),
    "fake-model": (0.0, 0.0),
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    inp, out = PRICING.get(model, (0.5, 1.0))
    return round((input_tokens * inp + output_tokens * out) / 1_000_000, 6)


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict


@dataclass
class ToolUse:
    id: str
    name: str
    input: dict


@dataclass
class AIResult:
    text: str
    tool_uses: list[ToolUse] = field(default_factory=list)
    stop_reason: str = "stop"
    provider: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    assistant_message: dict = field(default_factory=dict)  # raw assistant message to append for tool loops


@dataclass
class CallContext:
    feature: str
    user_id: str | None = None
    project_id: str | None = None
    prompt_name: str | None = None
    prompt_version: str | None = None
    retrieval: dict = field(default_factory=dict)


class RetryableAIError(AIUnavailableError):
    """Raised by a provider when the next provider should be tried."""


# --------------------------------------------------------------------------- providers


class Provider:
    name = "base"
    models: dict[str, str] = {}

    def model_for(self, tier: str) -> str:
        return self.models.get(tier) or self.models["primary"]

    def generate(self, *, tier: str, system: str, messages: list[dict], max_tokens: int, tools: list[ToolSpec] | None = None, json_mode: bool = False, temperature: float = 0.2) -> AIResult:
        raise NotImplementedError

    def stream(self, *, tier: str, system: str, messages: list[dict], max_tokens: int, temperature: float = 0.2) -> Iterator[str | AIResult]:
        raise NotImplementedError


class OpenAICompatProvider(Provider):
    """Groq and Gemini both expose OpenAI-compatible chat completions."""

    def __init__(self, name: str, base_url: str, api_key: str, models: dict[str, str], *, stream_usage: bool = True) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.models = models
        self.stream_usage = stream_usage
        self._client = httpx.Client(timeout=httpx.Timeout(settings.ai_timeout_seconds, connect=10.0))

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _body(self, tier, system, messages, max_tokens, tools, json_mode, temperature, stream=False) -> dict:
        body: dict[str, Any] = {
            "model": self.model_for(tier),
            "messages": [{"role": "system", "content": system}, *messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            body["tools"] = [{"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.input_schema}} for t in tools]
            body["tool_choice"] = "auto"
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if stream:
            body["stream"] = True
            if self.stream_usage:
                body["stream_options"] = {"include_usage": True}
        return body

    def _raise_for(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        detail = response.text[:300]
        if response.status_code in (401, 403):
            raise AIUnavailableError(f"{self.name}: credentials rejected.", code="ai_auth")
        if response.status_code == 429 or response.status_code >= 500:
            raise RetryableAIError(f"{self.name}: {response.status_code} {detail}", code="ai_rate_limited" if response.status_code == 429 else "ai_status_error")
        raise RetryableAIError(f"{self.name}: {response.status_code} {detail}", code="ai_bad_request")

    def generate(self, *, tier, system, messages, max_tokens, tools=None, json_mode=False, temperature=0.2) -> AIResult:
        if not self.configured:
            raise RetryableAIError(f"{self.name}: no API key configured.", code="ai_not_configured")
        started = time.perf_counter()
        body = self._body(tier, system, messages, max_tokens, tools, json_mode, temperature)
        try:
            response = self._client.post(f"{self.base_url}/chat/completions", headers=self._headers(), json=body)
        except httpx.TimeoutException as exc:
            raise RetryableAIError(f"{self.name}: timed out.", code="ai_timeout") from exc
        except httpx.HTTPError as exc:
            raise RetryableAIError(f"{self.name}: connection error ({exc}).", code="ai_connection") from exc
        self._raise_for(response)
        data = response.json()
        latency = int((time.perf_counter() - started) * 1000)
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        tool_uses = []
        for call in message.get("tool_calls") or []:
            fn = call.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            tool_uses.append(ToolUse(id=call.get("id") or dbm.new_id(), name=fn.get("name", ""), input=args if isinstance(args, dict) else {}))
        usage = data.get("usage") or {}
        return AIResult(
            text=(message.get("content") or "").strip(),
            tool_uses=tool_uses,
            stop_reason=choice.get("finish_reason") or "stop",
            provider=self.name,
            model=data.get("model") or body["model"],
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            latency_ms=latency,
            assistant_message={k: v for k, v in message.items() if k in ("role", "content", "tool_calls")},
        )

    def stream(self, *, tier, system, messages, max_tokens, temperature=0.2) -> Iterator[str | AIResult]:
        if not self.configured:
            raise RetryableAIError(f"{self.name}: no API key configured.", code="ai_not_configured")
        started = time.perf_counter()
        body = self._body(tier, system, messages, max_tokens, None, False, temperature, stream=True)
        parts: list[str] = []
        usage: dict = {}
        model = body["model"]
        finish = "stop"
        try:
            with self._client.stream("POST", f"{self.base_url}/chat/completions", headers=self._headers(), json=body) as response:
                if response.status_code >= 400:
                    response.read()
                    self._raise_for(response)
                for line in response.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        event = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    model = event.get("model") or model
                    if event.get("usage"):
                        usage = event["usage"]
                    for choice in event.get("choices") or []:
                        delta = (choice.get("delta") or {}).get("content")
                        if delta:
                            parts.append(delta)
                            yield delta
                        if choice.get("finish_reason"):
                            finish = choice["finish_reason"]
                        # Groq puts usage on x_groq in the last chunk
                    xg = event.get("x_groq") or {}
                    if xg.get("usage"):
                        usage = xg["usage"]
        except httpx.TimeoutException as exc:
            raise RetryableAIError(f"{self.name}: timed out.", code="ai_timeout") from exc
        except httpx.HTTPError as exc:
            raise RetryableAIError(f"{self.name}: connection error ({exc}).", code="ai_connection") from exc
        text = "".join(parts)
        yield AIResult(
            text=text.strip(),
            stop_reason=finish,
            provider=self.name,
            model=model,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or max(1, len(text) // 4)),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


class FakeProvider(Provider):
    """Deterministic provider for tests/offline dev. Handlers keyed by ``[prompt:<name>``."""

    name = "fake"
    models = {"primary": "fake-model", "fast": "fake-model", "vision": "fake-model"}

    def __init__(self) -> None:
        self.handlers: dict[str, Callable[[dict], Any]] = {}
        self.calls: list[dict] = []

    def _dispatch(self, kwargs: dict) -> Any:
        self.calls.append(kwargs)
        system = kwargs.get("system", "")
        for key, handler in self.handlers.items():
            if f"[prompt:{key}@" in system:
                return handler(kwargs)
        default = self.handlers.get("*")
        if default:
            return default(kwargs)
        return {} if kwargs.get("json_mode") else "This is a fake response.\nGROUNDED: no"

    def generate(self, *, tier, system, messages, max_tokens, tools=None, json_mode=False, temperature=0.2) -> AIResult:
        out = self._dispatch({"tier": tier, "system": system, "messages": messages, "tools": tools, "json_mode": json_mode})
        if isinstance(out, AIResult):
            out.provider, out.model = self.name, "fake-model"
            return out
        text = out if isinstance(out, str) else json.dumps(out)
        return AIResult(text=text, provider=self.name, model="fake-model", input_tokens=len(system) // 4 + 50, output_tokens=len(text) // 4, latency_ms=3, assistant_message={"role": "assistant", "content": text})

    def stream(self, *, tier, system, messages, max_tokens, temperature=0.2) -> Iterator[str | AIResult]:
        result = self.generate(tier=tier, system=system, messages=messages, max_tokens=max_tokens)
        for word in result.text.split(" "):
            yield word + " "
        yield result


_providers: list[Provider] | None = None


def build_providers() -> list[Provider]:
    out: list[Provider] = []
    for name in settings.ai_provider_order:
        if name == "groq":
            out.append(OpenAICompatProvider("groq", settings.groq_base_url, settings.groq_api_key, {"primary": settings.groq_model_primary, "fast": settings.groq_model_fast, "vision": settings.groq_model_vision}))
        elif name == "gemini":
            out.append(OpenAICompatProvider("gemini", settings.gemini_base_url, settings.gemini_api_key, {"primary": settings.gemini_model_primary, "fast": settings.gemini_model_fast, "vision": settings.gemini_model_vision}, stream_usage=False))
        elif name == "fake":
            out.append(FakeProvider())
    return out or [FakeProvider()]


def get_providers() -> list[Provider]:
    global _providers
    if _providers is None:
        _providers = build_providers()
    return _providers


def set_providers(providers: list[Provider] | None) -> None:
    global _providers
    _providers = providers


def provider_health() -> list[dict]:
    return [{"name": p.name, "configured": getattr(p, "configured", True), "models": p.models} for p in get_providers()]


# --------------------------------------------------------------------------- client with fallback + observability


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def extract_json(text: str) -> str:
    text = _FENCE.sub("", text.strip()).strip()
    if text.startswith("{") or text.startswith("["):
        return text
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    return text[start:] if start >= 0 else text


class AIClient:
    def __init__(self, providers: list[Provider] | None = None) -> None:
        self.providers = providers or get_providers()

    def _record(self, ctx: CallContext, result: AIResult | None, *, tier: str, status: str, attempts: list[dict], error: str | None = None, latency_ms: int = 0, tool_calls: list | None = None) -> str:
        doc = {
            "user_id": ctx.user_id,
            "project_id": ctx.project_id,
            "feature": ctx.feature,
            "prompt_name": ctx.prompt_name,
            "prompt_version": ctx.prompt_version,
            "provider": result.provider if result else (attempts[-1]["provider"] if attempts else "none"),
            "model": result.model if result else (attempts[-1].get("model") or "unknown" if attempts else "unknown"),
            "tier": tier,
            "input_tokens": result.input_tokens if result else 0,
            "output_tokens": result.output_tokens if result else 0,
            "cost_usd": estimate_cost(result.model, result.input_tokens, result.output_tokens) if result else 0.0,
            "latency_ms": result.latency_ms if result else latency_ms,
            "status": status,
            "error": error,
            "attempts": attempts,
            "retrieval": ctx.retrieval or {},
            "tool_calls": tool_calls or [],
            "request_id": request_id_var.get(),
        }
        dbm.insert(dbm.AI_REQUESTS, doc)
        logger.info("ai request", extra={"feature": ctx.feature, "latency_ms": doc["latency_ms"], "user_id": ctx.user_id, "project_id": ctx.project_id})
        return doc["_id"]

    def _with_fallback(self, fn: Callable[[Provider], AIResult], tier: str) -> tuple[AIResult, list[dict]]:
        attempts: list[dict] = []
        last: Exception | None = None
        for provider in self.providers:
            started = time.perf_counter()
            try:
                result = fn(provider)
                attempts.append({"provider": provider.name, "model": provider.model_for(tier), "ok": True, "latency_ms": result.latency_ms})
                return result, attempts
            except RetryableAIError as exc:
                last = exc
                attempts.append({"provider": provider.name, "model": provider.model_for(tier), "ok": False, "error": str(exc)[:200], "latency_ms": int((time.perf_counter() - started) * 1000)})
                logger.warning("provider %s failed, trying next: %s", provider.name, exc)
                continue
        raise AIUnavailableError("All AI providers failed. " + (str(last) if last else ""), code=getattr(last, "code", "ai_unavailable")) from last

    def generate(self, ctx: CallContext, *, system: str, messages: list[dict], max_tokens: int = 2000, tier: str = "primary", tools: list[ToolSpec] | None = None, temperature: float = 0.2) -> tuple[AIResult, str]:
        started = time.perf_counter()
        try:
            result, attempts = self._with_fallback(lambda p: p.generate(tier=tier, system=system, messages=messages, max_tokens=max_tokens, tools=tools, temperature=temperature), tier)
        except AIUnavailableError as exc:
            self._record(ctx, None, tier=tier, status="error", attempts=[], error=str(exc), latency_ms=int((time.perf_counter() - started) * 1000))
            raise
        status = "fallback" if len(attempts) > 1 else "ok"
        req_id = self._record(ctx, result, tier=tier, status=status, attempts=attempts, tool_calls=[{"name": t.name, "input": t.input} for t in result.tool_uses])
        return result, req_id

    def generate_structured(self, ctx: CallContext, schema: type[T], *, system: str, messages: list[dict], max_tokens: int = 2000, tier: str = "primary", temperature: float = 0.1) -> tuple[T, str]:
        """Generate JSON matching ``schema``; validate; fall back to the next provider if invalid."""
        schema_text = json.dumps(schema.model_json_schema(), indent=None)
        system_full = f"{system}\n\nRespond with ONLY a JSON object matching this JSON schema (no prose, no markdown):\n{schema_text}"
        started = time.perf_counter()
        parsed_holder: dict[str, Any] = {}

        def attempt(provider: Provider) -> AIResult:
            result = provider.generate(tier=tier, system=system_full, messages=messages, max_tokens=max_tokens, json_mode=True, temperature=temperature)
            try:
                parsed_holder["value"] = schema.model_validate_json(extract_json(result.text))
            except (ValidationError, ValueError) as exc:
                raise RetryableAIError(f"{provider.name}: invalid structured output ({str(exc)[:160]})", code="ai_invalid_output") from exc
            return result

        try:
            result, attempts = self._with_fallback(attempt, tier)
        except AIUnavailableError as exc:
            self._record(ctx, None, tier=tier, status="error", attempts=[], error=str(exc), latency_ms=int((time.perf_counter() - started) * 1000))
            raise
        status = "fallback" if len(attempts) > 1 else "ok"
        req_id = self._record(ctx, result, tier=tier, status=status, attempts=attempts)
        return parsed_holder["value"], req_id

    def stream(self, ctx: CallContext, *, system: str, messages: list[dict], max_tokens: int = 2000, tier: str = "primary", temperature: float = 0.3) -> Iterator[str | dict]:
        """Yield text deltas; the final item is a dict {"ai_request_id", "text", "provider"}.

        Falls back to the next provider only if nothing has been streamed yet.
        """
        started = time.perf_counter()
        attempts: list[dict] = []
        last: Exception | None = None
        for provider in self.providers:
            emitted = False
            try:
                for item in provider.stream(tier=tier, system=system, messages=messages, max_tokens=max_tokens, temperature=temperature):
                    if isinstance(item, AIResult):
                        attempts.append({"provider": provider.name, "model": item.model, "ok": True, "latency_ms": item.latency_ms})
                        status = "fallback" if len(attempts) > 1 else "ok"
                        req_id = self._record(ctx, item, tier=tier, status=status, attempts=attempts)
                        yield {"ai_request_id": req_id, "text": item.text, "provider": provider.name, "model": item.model}
                        return
                    emitted = True
                    yield item
            except RetryableAIError as exc:
                last = exc
                attempts.append({"provider": provider.name, "model": provider.model_for(tier), "ok": False, "error": str(exc)[:200]})
                if emitted:
                    break
                continue
        err = AIUnavailableError("All AI providers failed. " + (str(last) if last else ""), code=getattr(last, "code", "ai_unavailable"))
        self._record(ctx, None, tier=tier, status="error", attempts=attempts, error=str(err), latency_ms=int((time.perf_counter() - started) * 1000))
        raise err
