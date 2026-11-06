from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.agent.loop import run_agent
from app.agent.tools import ToolContext
from app.api.agent_schemas import (
    AgentChatRequest,
    AgentChatResponse,
    ToolSpecOut,
    tool_catalogue,
)
from app.api.schemas import DiagnosticResponse, KpiTelemetryRequest
from app.config import LlmSettings, Thresholds, get_llm_settings, get_thresholds
from app.domain.rules import diagnose
from app.llm.base import LLMError, LLMNotConfigured, LLMProvider
from app.llm.factory import build_provider
from app.rag.index import get_retriever

router = APIRouter()

ThresholdsDep = Annotated[Thresholds, Depends(get_thresholds)]
LlmSettingsDep = Annotated[LlmSettings, Depends(get_llm_settings)]


def get_agent_provider(settings: LlmSettingsDep) -> LLMProvider:
    try:
        return build_provider(settings)
    except LLMNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


ProviderDep = Annotated[LLMProvider, Depends(get_agent_provider)]


@router.post(
    "/telemetry/analyze",
    response_model=DiagnosticResponse,
    summary="Diagnose one cell from its KPI snapshot",
    description=(
        "Runs the deterministic radio-engineering rule engine over a single cell KPI "
        "snapshot. No language model is involved: the same input always produces the "
        "same verdict, findings and recommendations."
    ),
    tags=["telemetry"],
)
def analyze_telemetry(
    payload: KpiTelemetryRequest,
    thresholds: ThresholdsDep,
) -> DiagnosticResponse:
    snapshot = payload.to_snapshot()
    report = diagnose(snapshot, thresholds)
    return DiagnosticResponse.from_report(report)


@router.get(
    "/telemetry/sample",
    response_model=KpiTelemetryRequest,
    summary="Return a sample request payload",
    description="Convenience endpoint so the demo can be exercised without crafting a body.",
    tags=["telemetry"],
)
def sample_payload() -> KpiTelemetryRequest:
    examples = KpiTelemetryRequest.model_config["json_schema_extra"]["examples"]
    return KpiTelemetryRequest.model_validate(examples[0])


@router.get(
    "/agent/tools",
    response_model=list[ToolSpecOut],
    summary="List the tools the agent can call",
    tags=["agent"],
)
def list_agent_tools() -> list[ToolSpecOut]:
    return tool_catalogue()


@router.post(
    "/agent/chat",
    response_model=AgentChatResponse,
    summary="Ask the RAN assistant",
    description=(
        "Runs the bounded agent loop: the model may call diagnose_cell against the "
        "attached snapshot and search_runbooks for troubleshooting guidance. Every tool "
        "call is returned in 'trace', and retrieved runbook sections are returned as "
        "citations with stable chunk ids. With LLM_PROVIDER=mock the whole path runs "
        "with no credentials."
    ),
    tags=["agent"],
)
async def agent_chat(
    payload: AgentChatRequest,
    provider: ProviderDep,
    thresholds: ThresholdsDep,
    llm: LlmSettingsDep,
) -> AgentChatResponse:
    cell_snapshot = payload.cell.to_snapshot() if payload.cell else None
    cell_payload = payload.cell.model_dump(mode="json") if payload.cell else None

    context = ToolContext(
        cell=cell_snapshot,
        thresholds=thresholds,
        retriever=get_retriever(),
    )

    try:
        result = await run_agent(
            payload.message,
            provider,
            context,
            cell_payload,
            max_steps=llm.max_steps,
        )
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return AgentChatResponse.from_result(result)
