"""HTTP contract for the agent layer."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.agent.loop import AgentResult
from app.agent.tools import SPECS
from app.api.schemas import KpiTelemetryRequest


class CitationOut(BaseModel):
    chunk_id: str = Field(description="Stable id of the cited runbook section.")
    doc_title: str
    section: str
    score: float
    snippet: str


class TraceStepOut(BaseModel):
    step: int
    kind: str = Field(description="'tool_call' or 'final'.")
    tool: str | None = None
    arguments: dict[str, Any] | None = None
    result_summary: str | None = None
    latency_ms: float = 0.0


class ToolSpecOut(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]


class AgentChatRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "message": (
                        "The cell is at 88% PRB and only 14 Mbps. What is your diagnosis, "
                        "and what does the runbook say about congestion?"
                    ),
                    "cell": {
                        "cell_id": "LTE-MVD-0421",
                        "technology": "LTE",
                        "bandwidth_mhz": 20.0,
                        "prb_utilization_dl_pct": 88.0,
                        "throughput_dl_mbps": 14.0,
                        "cell_capacity_dl_mbps": 120.0,
                        "drop_call_rate_pct": 1.8,
                        "rsrp_dbm": -98.0,
                        "rsrq_db": -14.0,
                        "sinr_db": 8.0,
                        "active_ues": 214,
                    },
                }
            ]
        }
    )

    message: str = Field(min_length=1, max_length=4000, description="Operator question.")
    cell: KpiTelemetryRequest | None = Field(
        default=None,
        description=(
            "Optional cell KPI snapshot. When present, the platform attaches it as "
            "authoritative telemetry; the model never supplies these numbers."
        ),
    )


class AgentChatResponse(BaseModel):
    answer: str
    provider: str
    trace: list[TraceStepOut]
    citations: list[CitationOut]
    engine_version: str

    @classmethod
    def from_result(cls, result: AgentResult) -> AgentChatResponse:
        return cls(
            answer=result.answer,
            provider=result.provider,
            trace=[
                TraceStepOut(
                    step=step.step,
                    kind=step.kind,
                    tool=step.tool,
                    arguments=step.arguments,
                    result_summary=step.result_summary,
                    latency_ms=step.latency_ms,
                )
                for step in result.trace
            ],
            citations=[
                CitationOut(
                    chunk_id=c.chunk_id,
                    doc_title=c.doc_title,
                    section=c.section,
                    score=c.score,
                    snippet=c.snippet,
                )
                for c in result.citations
            ],
            engine_version=result.engine_version,
        )


def tool_catalogue() -> list[ToolSpecOut]:
    return [
        ToolSpecOut(name=spec.name, description=spec.description, parameters=spec.parameters)
        for spec in SPECS
    ]


__all__ = [
    "AgentChatRequest",
    "AgentChatResponse",
    "CitationOut",
    "ToolSpecOut",
    "TraceStepOut",
    "tool_catalogue",
]
