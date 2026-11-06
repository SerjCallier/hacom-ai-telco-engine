"""Bounded agent loop with an inspectable trace.

The loop is deliberately small and boring: ask the model, execute whatever tools it
requested, feed the results back, repeat until it answers or the step budget runs
out. Every turn is recorded, so an operator can see which tool was called, with
which arguments, what it returned and how long it took.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from app.agent.tools import SPECS, Citation, ToolContext, ToolOutcome, execute_tool
from app.config import ENGINE_VERSION
from app.llm.base import LLMProvider, Message, ToolSpec

SYSTEM_PROMPT = (
    "You are a RAN operations assistant for a mobile network operator. "
    "The platform attaches cell telemetry to the request; you never invent or estimate "
    "measurements yourself. Call diagnose_cell to evaluate the attached snapshot and "
    "search_runbooks for troubleshooting guidance. When you use a runbook section, cite "
    "its chunk id. Be concise and operational: state the verdict, the evidence and the "
    "next action. If neither a snapshot nor a relevant runbook section is available, say "
    "so plainly instead of guessing."
)


@dataclass(frozen=True, slots=True)
class TraceStep:
    step: int
    kind: str
    tool: str | None = None
    arguments: dict[str, Any] | None = None
    result_summary: str | None = None
    latency_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class AgentResult:
    answer: str
    provider: str
    trace: tuple[TraceStep, ...]
    citations: tuple[Citation, ...]
    engine_version: str = ENGINE_VERSION


def _telemetry_message(cell: dict[str, Any]) -> Message:
    return Message(
        role="system",
        content=(
            "Cell telemetry attached by the platform for this request "
            "(authoritative, do not modify):\n"
            + json.dumps(cell, ensure_ascii=False, sort_keys=True)
        ),
    )


def _tool_specs() -> list[ToolSpec]:
    return list(SPECS)


def _dedupe(citations: list[Citation]) -> tuple[Citation, ...]:
    seen: dict[str, Citation] = {}
    for citation in citations:
        seen.setdefault(citation.chunk_id, citation)
    return tuple(seen.values())


async def run_agent(
    message: str,
    provider: LLMProvider,
    ctx: ToolContext,
    cell_payload: dict[str, Any] | None,
    *,
    max_steps: int = 4,
) -> AgentResult:
    messages: list[Message] = [Message(role="system", content=SYSTEM_PROMPT)]
    if cell_payload is not None:
        messages.append(_telemetry_message(cell_payload))
    messages.append(Message(role="user", content=message))

    specs = _tool_specs()
    trace: list[TraceStep] = []
    citations: list[Citation] = []

    for step in range(1, max_steps + 1):
        completion = await provider.complete(messages, specs, cell=cell_payload)

        if not completion.tool_calls:
            answer = (completion.content or "").strip()
            trace.append(TraceStep(step=step, kind="final", result_summary=answer[:200]))
            return AgentResult(
                answer=answer,
                provider=provider.name,
                trace=tuple(trace),
                citations=_dedupe(citations),
            )

        messages.append(
            Message(
                role="assistant",
                content=completion.content or "",
                tool_calls=completion.tool_calls,
            )
        )

        for call in completion.tool_calls:
            started = perf_counter()
            outcome: ToolOutcome = execute_tool(call.name, call.arguments, ctx)
            elapsed_ms = (perf_counter() - started) * 1000

            trace.append(
                TraceStep(
                    step=step,
                    kind="tool_call",
                    tool=call.name,
                    arguments=call.arguments,
                    result_summary=outcome.summary,
                    latency_ms=round(elapsed_ms, 2),
                )
            )
            citations.extend(outcome.citations)

            messages.append(
                Message(
                    role="tool",
                    content=json.dumps(outcome.payload, ensure_ascii=False, default=str),
                    tool_call_id=call.id,
                    name=call.name,
                )
            )

    exhausted = (
        f"The agent stopped after {max_steps} steps without producing a final answer. "
        "Inspect the trace to see which tools were called."
    )
    trace.append(TraceStep(step=max_steps, kind="final", result_summary=exhausted))
    return AgentResult(
        answer=exhausted,
        provider=provider.name,
        trace=tuple(trace),
        citations=_dedupe(citations),
    )
