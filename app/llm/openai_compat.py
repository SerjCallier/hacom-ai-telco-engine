"""OpenAI-compatible chat completions provider.

Speaks the ``/chat/completions`` shape used by OpenAI, Groq, vLLM, LM Studio and
Ollama's compatibility endpoint. Implemented over ``httpx`` instead of a vendor SDK
so the provider surface stays one HTTP contract rather than one library version.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.llm.base import Completion, LLMError, Message, ToolCall, ToolSpec


def _serialise_message(message: Message) -> dict[str, Any]:
    payload: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
            }
            for call in message.tool_calls
        ]
    if message.tool_call_id:
        payload["tool_call_id"] = message.tool_call_id
    return payload


def _parse_tool_calls(raw_calls: list[dict[str, Any]]) -> tuple[ToolCall, ...]:
    calls: list[ToolCall] = []
    for index, raw in enumerate(raw_calls):
        function = raw.get("function") or {}
        raw_arguments = function.get("arguments") or "{}"
        try:
            arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else {}
        except json.JSONDecodeError as exc:
            raise LLMError(f"Provider returned unparsable tool arguments: {raw_arguments}") from exc
        calls.append(
            ToolCall(
                id=raw.get("id") or f"call_{index}",
                name=function.get("name", ""),
                arguments=arguments,
            )
        )
    return tuple(calls)


class OpenAiCompatibleProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.2,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.name = "openai-compatible"
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._timeout = timeout_seconds

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        *,
        cell: dict[str, Any] | None = None,
    ) -> Completion:
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [_serialise_message(m) for m in messages],
            "temperature": self._temperature,
        }
        if tools:
            body["tools"] = [spec.to_openai() for spec in tools]

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    json=body,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
        except httpx.HTTPError as exc:
            raise LLMError(f"Provider request failed: {exc}") from exc

        if response.status_code >= 400:
            raise LLMError(f"Provider returned {response.status_code}: {response.text[:300]}")

        try:
            message = response.json()["choices"][0]["message"]
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError("Provider response did not contain a completion") from exc

        return Completion(
            content=message.get("content"),
            tool_calls=_parse_tool_calls(message.get("tool_calls") or []),
        )
