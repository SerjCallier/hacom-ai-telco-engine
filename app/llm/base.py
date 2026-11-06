"""Provider-neutral chat completion contract.

The agent loop knows nothing about OpenAI, Anthropic or a local runtime. It speaks
in messages, tool specifications and completions. Swapping providers is a config
change, not a code change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class LLMError(RuntimeError):
    """A provider call failed in a way the caller should surface."""


class LLMNotConfigured(LLMError):
    """The selected provider cannot run with the current configuration."""


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]

    def to_openai(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Message:
    role: str
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None
    name: str | None = None


@dataclass(frozen=True, slots=True)
class Completion:
    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()


class LLMProvider(Protocol):
    name: str

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        *,
        cell: dict[str, Any] | None = None,
    ) -> Completion:
        """Return the next assistant turn.

        ``cell`` is a convenience for the deterministic mock provider, which cannot
        read the system prompt on its own. Real providers ignore it: for them the
        snapshot travels inside the conversation as a system message.
        """
        ...
