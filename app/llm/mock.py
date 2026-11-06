"""Deterministic stand-in provider.

This is not a language model and the API never pretends it is: every response
carries ``provider: "mock"``. Its job is to let the whole agent harness, the tool
contract and the HTTP surface be exercised and tested with no credentials and no
network, and to keep the demo runnable for a reviewer who does not have an API key.

Routing is keyword-based and intentionally dumb. The value is that it drives the
*same* tool-calling path a real model would drive.
"""

from __future__ import annotations

import json
from typing import Any

from app.llm.base import Completion, Message, ToolCall, ToolSpec

_KNOWLEDGE_HINTS = (
    "manual",
    "runbook",
    "3gpp",
    "etsi",
    "standard",
    "estandar",
    "documentacion",
    "documentación",
    "que dice",
    "qué dice",
    "por que",
    "por qué",
    "why",
    "reference",
)

# Small talk is the only case that is answered without touching a tool. Anything
# else is treated as a troubleshooting question and retrieval is attempted, because
# a whitelist of "knowledge" hints silently fails on every phrasing it did not
# anticipate ("que reviso?", "cual es la causa?"). Retrieval that finds nothing is
# reported as such, which is more useful than refusing to look.
_SMALL_TALK = frozenset(
    {
        "hola",
        "hi",
        "hello",
        "hey",
        "buenas",
        "buenos",
        "dia",
        "dias",
        "tardes",
        "noches",
        "que",
        "tal",
        "como",
        "estas",
        "test",
        "ping",
        "thanks",
        "gracias",
    }
)

_HELP_TEXT = (
    "I can help in two ways. Attach a cell KPI snapshot and I will run the "
    "deterministic diagnostic rules against it, or ask a question about RAN "
    "troubleshooting and I will retrieve the relevant runbook sections with "
    "citations. No cell snapshot was attached to this request and the message "
    "contained no troubleshooting question, so no tool was called."
)


def _is_small_talk(text: str) -> bool:
    words = [word for word in text.lower().replace("?", " ").replace("!", " ").split() if word]
    return not words or all(word in _SMALL_TALK for word in words)


class MockProvider:
    name = "mock"

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        *,
        cell: dict[str, Any] | None = None,
    ) -> Completion:
        tool_messages = [m for m in messages if m.role == "tool"]
        if tool_messages:
            return Completion(content=self._compose(tool_messages))

        user_message = next(
            (m.content for m in reversed(messages) if m.role == "user"),
            "",
        )

        if _is_small_talk(user_message) and cell is None:
            return Completion(content=_HELP_TEXT)

        calls: list[ToolCall] = []
        if cell is not None:
            calls.append(ToolCall(id="call_diagnose", name="diagnose_cell", arguments={}))

        # A snapshot alone is not a knowledge question: without one of these hints the
        # operator asked for a diagnosis, and padding the answer with unrelated
        # runbook sections would be noise.
        wants_knowledge = any(hint in user_message.lower() for hint in _KNOWLEDGE_HINTS)
        if cell is None or wants_knowledge:
            calls.append(
                ToolCall(
                    id="call_search",
                    name="search_runbooks",
                    arguments={"query": user_message, "limit": 3},
                )
            )

        if calls:
            return Completion(tool_calls=tuple(calls))
        return Completion(content=_HELP_TEXT)

    def _compose(self, tool_messages: list[Message]) -> str:
        parts: list[str] = []
        references: list[str] = []
        searched_without_hits = False

        for message in tool_messages:
            try:
                payload = json.loads(message.content)
            except json.JSONDecodeError:
                parts.append("A tool returned an unreadable payload.")
                continue

            if message.name == "diagnose_cell":
                parts.append(self._render_diagnosis(payload))
            elif message.name == "search_runbooks":
                results = payload.get("results", [])
                if not results:
                    searched_without_hits = True
                for hit in results:
                    references.append(f"{hit['doc_title']} > {hit['section']} ({hit['chunk_id']})")

        if searched_without_hits:
            parts.append("No runbook section matched that question, so there is nothing to cite.")
        if references:
            parts.append("Runbook references: " + "; ".join(references) + ".")

        return "\n\n".join(parts) if parts else "No tool produced usable output."

    @staticmethod
    def _render_diagnosis(payload: dict[str, Any]) -> str:
        if "error" in payload:
            return f"Diagnosis unavailable: {payload['error']}"

        verdict = str(payload.get("verdict", "unknown")).upper()
        cell_id = payload.get("cell_id", "cell")
        findings = payload.get("findings", [])

        if not findings:
            text = f"{cell_id}: {verdict}. No diagnostic rule fired on this snapshot."
        else:
            details = "; ".join(f"{f['title']} ({f['rule_id']}, {f['severity']})" for f in findings)
            text = f"{cell_id}: {verdict}. {len(findings)} finding(s): {details}."

        recommendations = payload.get("recommendations") or []
        if len(recommendations) == 1:
            text += f" Recommended action: {recommendations[0]}"
        elif recommendations:
            # One finding can carry several next actions, and several findings can
            # each carry one. Showing only the first silently drops work.
            numbered = " ".join(
                f"({index}) {action}" for index, action in enumerate(recommendations, start=1)
            )
            text += f" Recommended actions: {numbered}"
        return text
