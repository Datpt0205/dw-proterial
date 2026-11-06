"""OpenAI-compatible chat-completions adapter (real provider path).

Works with any endpoint speaking the /chat/completions dialect (OpenAI, Azure
OpenAI with base_url, vLLM, Ollama-openai, ...). Enabled via configuration;
the production profile refuses to run with the mock instead of this.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass

import httpx

from dw_agent_runtime.model.gateway import ModelUsage
from dw_agent_runtime.model.profiles import ModelRoute, Provider
from dw_agent_runtime.model.prompts import RenderedPrompt
from dw_agent_runtime.model.streaming import StreamedAnswer
from dw_kernel.errors import InfrastructureError
from dw_kernel.resilience import CircuitBreaker


@dataclass
class OpenAICompatibleAdapter:
    """Implements ``ModelProviderAdapter`` over HTTP.

    ``structured_mode``:
    - "json_schema": native structured output (OpenAI, vLLM >= 0.6, ...)
    - "json_object": JSON mode + schema embedded in the prompt (DeepSeek, older
      providers). Output is still validated against the schema by the gateway.
    """

    base_url: str
    api_key: str
    provider: Provider = Provider.OPENAI_COMPATIBLE
    structured_mode: str = "json_schema"
    breaker: CircuitBreaker | None = None  # trips on repeated provider failures

    @property
    def provider_name(self) -> str:
        return self.provider

    async def complete_json(
        self,
        prompt: RenderedPrompt,
        json_schema: dict[str, object],
        route: ModelRoute,
        *,
        max_output_tokens: int | None,
    ) -> tuple[dict[str, object], ModelUsage, str | None]:
        body = _build_request_body(
            prompt,
            json_schema,
            route,
            structured_mode=self.structured_mode,
            max_output_tokens=max_output_tokens,
        )

        if self.breaker is not None:
            self.breaker.before_call()
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=route.timeout_seconds,
            ) as client:
                response = await client.post("/chat/completions", json=body)
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException as exc:
            if self.breaker is not None:
                self.breaker.record_failure()
            raise InfrastructureError(
                "model provider timed out",
                details={"provider": self.provider, "model": route.model},
            ) from exc
        except httpx.HTTPError as exc:
            if self.breaker is not None:
                self.breaker.record_failure()
            raise InfrastructureError(
                "model provider request failed",
                details={"provider": self.provider, "error": type(exc).__name__},
            ) from exc
        if self.breaker is not None:
            self.breaker.record_success()

        try:
            message = data["choices"][0]["message"]
            parsed = _extract_json_object(str(message.get("content") or ""))
            usage_data = data.get("usage", {})
        except (KeyError, IndexError, ValueError, json.JSONDecodeError) as exc:
            raise InfrastructureError(
                "model provider returned an unparseable response",
                details={"provider": self.provider},
            ) from exc

        reasoning = message.get("reasoning_content")
        usage = ModelUsage(
            provider=self.provider,
            model=route.model,
            input_tokens=int(usage_data.get("prompt_tokens", 0)),
            output_tokens=int(usage_data.get("completion_tokens", 0)),
        )
        return parsed, usage, str(reasoning) if reasoning else None

    async def stream_json(
        self,
        prompt: RenderedPrompt,
        json_schema: dict[str, object],
        route: ModelRoute,
        *,
        max_output_tokens: int | None,
    ) -> AsyncGenerator[str | StreamedAnswer, None]:
        """`complete_json` with ``stream: true``: the visible text as the
        server sends it (a thinking model's reasoning is not visible text),
        then the parsed answer. ``timeout_seconds`` is the longest silence,
        so a model still loading is waited for as long as an unstreamed call
        waits, and closing this generator closes the connection, which ends
        the generation on the server."""
        body = {
            **_build_request_body(
                prompt,
                json_schema,
                route,
                structured_mode=self.structured_mode,
                max_output_tokens=max_output_tokens,
            ),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if self.breaker is not None:
            self.breaker.before_call()
        written: list[str] = []
        usage: ModelUsage | None = None
        try:
            async with (
                httpx.AsyncClient(
                    base_url=self.base_url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=route.timeout_seconds,
                ) as client,
                client.stream("POST", "/chat/completions", json=body) as response,
            ):
                response.raise_for_status()
                async for line in response.aiter_lines():
                    payload = line.removeprefix("data:").strip()
                    if not line.startswith("data:") or payload == "[DONE]":
                        continue
                    chunk = json.loads(payload)
                    if chunk.get("usage"):
                        usage = ModelUsage(
                            provider=self.provider,
                            model=route.model,
                            input_tokens=int(chunk["usage"].get("prompt_tokens", 0)),
                            output_tokens=int(chunk["usage"].get("completion_tokens", 0)),
                        )
                    for choice in chunk.get("choices") or []:
                        text = (choice.get("delta") or {}).get("content")
                        if text:
                            written.append(text)
                            yield text
        except httpx.TimeoutException as exc:
            if self.breaker is not None:
                self.breaker.record_failure()
            raise InfrastructureError(
                "model provider timed out",
                details={"provider": self.provider, "model": route.model},
            ) from exc
        except httpx.HTTPError as exc:
            if self.breaker is not None:
                self.breaker.record_failure()
            raise InfrastructureError(
                "model provider request failed",
                details={"provider": self.provider, "error": type(exc).__name__},
            ) from exc
        if self.breaker is not None:
            self.breaker.record_success()
        try:
            parsed = _extract_json_object("".join(written))
        except (ValueError, json.JSONDecodeError) as exc:
            raise InfrastructureError(
                "model provider returned an unparseable response",
                details={"provider": self.provider},
            ) from exc
        yield StreamedAnswer(parsed, usage)


def _build_request_body(
    prompt: RenderedPrompt,
    json_schema: dict[str, object],
    route: ModelRoute,
    *,
    structured_mode: str,
    max_output_tokens: int | None,
) -> dict[str, object]:
    is_reasoner = "reasoner" in route.model or route.model.endswith("-r1")
    if structured_mode == "json_object" or is_reasoner:
        schema_hint = (
            "\n\nTrả về DUY NHẤT một JSON object hợp lệ đúng schema sau, "
            "không kèm giải thích:\n" + json.dumps(json_schema, ensure_ascii=False)
        )
        messages = [
            {"role": "system", "content": prompt.system + schema_hint},
            {"role": "user", "content": prompt.user},
        ]
        response_format: dict[str, object] | None = None if is_reasoner else {"type": "json_object"}
    else:
        messages = [
            {"role": "system", "content": prompt.system},
            {"role": "user", "content": prompt.user},
        ]
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": "structured_output", "schema": json_schema},
        }

    body: dict[str, object] = {"model": route.model, "messages": messages}
    if response_format is not None:
        body["response_format"] = response_format
    if route.temperature is not None:
        body["temperature"] = route.temperature
    if route.reasoning_effort is not None:
        # Chat-completions' own key. "none" is how a local server (Ollama,
        # vLLM with a Qwen3 template) is told not to think; left unset, the
        # server's default applies, which for a thinking model is to think.
        body["reasoning_effort"] = route.reasoning_effort
    if max_output_tokens:
        reasoning_family = route.model.startswith(("gpt-5", "o1", "o3", "o4"))
        body["max_completion_tokens" if reasoning_family else "max_tokens"] = max_output_tokens
    return body


def _extract_json_object(content: str) -> dict[str, object]:
    """Parse a JSON object from model text, tolerating code fences/preambles.

    Strict path first; reasoning models sometimes wrap the object in ```json
    fences or prepend prose, so fall back to the outermost {...} slice.
    """
    text = content.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("model returned no JSON object") from None
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("model returned non-object JSON")
    return parsed
