"""Tools the agent can call.

The important design constraint: the model never supplies telemetry. The platform
attaches the KPI snapshot to the request, and ``diagnose_cell`` reads it from the
execution context. A model that hallucinates numbers therefore cannot fabricate a
diagnosis, because the numbers it would need are not in its hands.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import Thresholds
from app.domain.kpis import KpiSnapshot
from app.domain.rules import diagnose
from app.llm.base import ToolSpec
from app.rag.index import Retriever


@dataclass(frozen=True, slots=True)
class Citation:
    chunk_id: str
    doc_title: str
    section: str
    score: float
    snippet: str


@dataclass(frozen=True, slots=True)
class ToolOutcome:
    ok: bool
    payload: dict[str, Any]
    summary: str
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class ToolContext:
    cell: KpiSnapshot | None
    thresholds: Thresholds
    retriever: Retriever


SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="diagnose_cell",
        description=(
            "Run the deterministic RAN diagnostic rules against the cell snapshot attached "
            "to this request. Takes no arguments: the platform supplies the telemetry, so "
            "the model cannot invent measurements. Returns verdict, findings with evidence, "
            "and recommendations."
        ),
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    ToolSpec(
        name="search_runbooks",
        description=(
            "Search the operational runbook corpus for troubleshooting guidance. Returns "
            "chunks with stable ids, document title and section, so the answer can cite the "
            "exact section it used. Use it for 'what does the runbook say' questions."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The troubleshooting question or keywords to look up.",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                    "default": 3,
                    "description": "Maximum number of runbook sections to return.",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    ),
)


def _diagnose_cell(ctx: ToolContext) -> ToolOutcome:
    if ctx.cell is None:
        return ToolOutcome(
            ok=False,
            payload={
                "error": (
                    "No cell snapshot is attached to this request. Send the 'cell' object "
                    "with the chat request to run diagnostics."
                )
            },
            summary="diagnose_cell rejected: no telemetry attached",
        )

    report = diagnose(ctx.cell, ctx.thresholds)
    payload = report.to_dict()
    summary = (
        f"{report.verdict.value}: {len(report.findings)} finding(s) "
        f"[{', '.join(f.rule_id for f in report.findings) or 'none'}]"
    )
    return ToolOutcome(ok=True, payload=payload, summary=summary)


def _search_runbooks(ctx: ToolContext, arguments: dict[str, Any]) -> ToolOutcome:
    query = str(arguments.get("query", "")).strip()
    if not query:
        return ToolOutcome(
            ok=False,
            payload={"error": "search_runbooks requires a non-empty 'query'."},
            summary="search_runbooks rejected: empty query",
        )

    limit = arguments.get("limit", 3)
    limit = max(1, min(int(limit), 5)) if isinstance(limit, (int, float)) else 3

    hits = ctx.retriever.search(query, limit=limit)
    results = [
        {
            "chunk_id": hit.chunk.chunk_id,
            "doc_title": hit.chunk.doc_title,
            "section": hit.chunk.section,
            "score": hit.score,
            "snippet": hit.chunk.snippet[:400],
            "source": hit.chunk.source,
        }
        for hit in hits
    ]
    citations = tuple(
        Citation(
            chunk_id=hit.chunk.chunk_id,
            doc_title=hit.chunk.doc_title,
            section=hit.chunk.section,
            score=hit.score,
            snippet=hit.chunk.snippet[:400],
        )
        for hit in hits
    )

    summary = (
        f"{len(results)} chunk(s): {', '.join(r['chunk_id'] for r in results)}"
        if results
        else "0 chunks matched"
    )
    return ToolOutcome(
        ok=bool(results),
        payload={"query": query, "results": results},
        summary=summary,
        citations=citations,
    )


def execute_tool(name: str, arguments: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
    if name == "diagnose_cell":
        return _diagnose_cell(ctx)
    if name == "search_runbooks":
        return _search_runbooks(ctx, arguments)
    return ToolOutcome(
        ok=False,
        payload={"error": f"Unknown tool: {name}"},
        summary=f"unknown tool {name!r}",
    )
