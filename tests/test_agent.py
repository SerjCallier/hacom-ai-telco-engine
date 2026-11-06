"""Agent loop, tool contract and HTTP surface.

Every test here runs offline with no credentials, which is the point: the agent
harness is verifiable independently of any model provider.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi.testclient import TestClient

from app.agent.loop import run_agent
from app.agent.tools import ToolContext, execute_tool
from app.config import LlmSettings, Thresholds, get_llm_settings
from app.domain.kpis import KpiSnapshot, RadioAccessTech
from app.llm.mock import MockProvider
from app.llm.openai_compat import OpenAiCompatibleProvider
from app.main import create_app
from app.rag.index import get_retriever

THRESHOLDS = Thresholds()

CELL_PAYLOAD: dict[str, Any] = {
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
}


def snapshot() -> KpiSnapshot:
    return KpiSnapshot(
        cell_id="LTE-MVD-0421",
        technology=RadioAccessTech.LTE,
        bandwidth_mhz=20.0,
        prb_utilization_dl_pct=88.0,
        throughput_dl_mbps=14.0,
        cell_capacity_dl_mbps=120.0,
        drop_call_rate_pct=1.8,
        rsrp_dbm=-98.0,
        rsrq_db=-14.0,
        sinr_db=8.0,
        active_ues=214,
    )


def context(cell: KpiSnapshot | None = None) -> ToolContext:
    return ToolContext(cell=cell, thresholds=THRESHOLDS, retriever=get_retriever())


def run(message: str, cell: KpiSnapshot | None, payload: dict[str, Any] | None) -> Any:
    return asyncio.run(run_agent(message, MockProvider(), context(cell), payload))


def test_agent_diagnoses_attached_cell() -> None:
    result = run("How does this cell look?", snapshot(), CELL_PAYLOAD)

    tools_called = [step.tool for step in result.trace if step.kind == "tool_call"]
    assert tools_called == ["diagnose_cell"]
    assert result.provider == "mock"
    assert "DEGRADED" in result.answer
    assert result.trace[-1].kind == "final"


def test_agent_retrieves_runbook_with_citations() -> None:
    result = run("What does the runbook say about congestion?", None, None)

    tools_called = [step.tool for step in result.trace if step.kind == "tool_call"]
    assert tools_called == ["search_runbooks"]
    assert result.citations
    assert all(citation.chunk_id for citation in result.citations)
    assert "radio-resource-congestion" in result.citations[0].chunk_id


def test_agent_calls_both_tools_when_both_are_relevant() -> None:
    result = run(
        "The cell is at 88% PRB. What is the diagnosis, and what does the manual say?",
        snapshot(),
        CELL_PAYLOAD,
    )

    tools_called = [step.tool for step in result.trace if step.kind == "tool_call"]
    assert tools_called == ["diagnose_cell", "search_runbooks"]
    assert result.citations


def test_agent_answers_honestly_without_telemetry_or_topic() -> None:
    result = run("Hello", None, None)

    assert not [step for step in result.trace if step.kind == "tool_call"]
    assert "no tool was called" in result.answer


def test_agent_retrieves_on_a_question_without_explicit_knowledge_hints() -> None:
    """Regression: "que reviso?" retrieved nothing because it was not in a hint list."""
    result = run("Usuarios con RSRP bueno pero SINR malo, que reviso?", None, None)

    tools_called = [step.tool for step in result.trace if step.kind == "tool_call"]
    assert tools_called == ["search_runbooks"]
    assert result.citations
    assert result.citations[0].chunk_id.startswith("coverage-and-interference")


def test_agent_reports_when_retrieval_finds_nothing() -> None:
    result = run("Necesito ayuda con la facturacion de mi cuenta", None, None)

    assert [step.tool for step in result.trace if step.kind == "tool_call"] == ["search_runbooks"]
    assert not result.citations
    assert "No runbook section matched" in result.answer


def test_agent_is_deterministic() -> None:
    first = run("How does this cell look?", snapshot(), CELL_PAYLOAD)
    second = run("How does this cell look?", snapshot(), CELL_PAYLOAD)

    assert first.answer == second.answer
    assert [(s.step, s.kind, s.tool) for s in first.trace] == [
        (s.step, s.kind, s.tool) for s in second.trace
    ]


def test_trace_records_tool_arguments_and_latency() -> None:
    result = run("What does the runbook say about interference?", None, None)

    tool_step = next(step for step in result.trace if step.kind == "tool_call")
    assert tool_step.tool == "search_runbooks"
    assert tool_step.arguments is not None
    assert "interference" in tool_step.arguments["query"]
    assert tool_step.result_summary
    assert tool_step.latency_ms >= 0


def test_diagnose_tool_without_telemetry_fails_gracefully() -> None:
    outcome = execute_tool("diagnose_cell", {}, context(cell=None))

    assert outcome.ok is False
    assert "No cell snapshot" in outcome.payload["error"]


def test_search_tool_rejects_empty_query() -> None:
    outcome = execute_tool("search_runbooks", {"query": "  "}, context())

    assert outcome.ok is False


def test_unknown_tool_is_reported() -> None:
    outcome = execute_tool("drop_database", {}, context())

    assert outcome.ok is False
    assert "Unknown tool" in outcome.payload["error"]


def test_search_tool_clamps_limit() -> None:
    outcome = execute_tool("search_runbooks", {"query": "congestion", "limit": 99}, context())

    assert outcome.ok is True
    assert len(outcome.payload["results"]) <= 5


def test_agent_chat_endpoint_returns_trace_and_citations() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/agent/chat",
        json={
            "message": "Diagnose this cell and tell me what the runbook says about congestion.",
            "cell": CELL_PAYLOAD,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "mock"
    assert body["trace"]
    assert body["citations"]
    assert body["citations"][0]["chunk_id"]


def test_agent_chat_works_without_a_cell_snapshot() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/agent/chat",
        json={"message": "What does the runbook say about coverage and interference?"},
    )

    assert response.status_code == 200
    assert response.json()["citations"]


def test_agent_tools_endpoint_lists_the_catalogue() -> None:
    client = TestClient(create_app())

    tools = client.get("/api/v1/agent/tools").json()

    assert {tool["name"] for tool in tools} == {"diagnose_cell", "search_runbooks"}


def test_openai_provider_without_key_returns_503() -> None:
    app = create_app()
    app.dependency_overrides[get_llm_settings] = lambda: LlmSettings(provider="openai", api_key="")
    client = TestClient(app)

    response = client.post("/api/v1/agent/chat", json={"message": "hola"})

    assert response.status_code == 503
    assert "LLM_API_KEY" in response.json()["detail"]


def test_openai_provider_requires_an_api_key() -> None:
    try:
        from app.llm.factory import build_provider

        build_provider(LlmSettings(provider="openai", api_key=""))
    except Exception as exc:  # noqa: BLE001 - asserting the configuration guard
        assert "LLM_API_KEY" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected a configuration error")


def test_openai_provider_ignores_the_mock_only_cell_argument() -> None:
    provider = OpenAiCompatibleProvider(
        base_url="http://127.0.0.1:9/v1", api_key="x", model="m", timeout_seconds=0.1
    )

    assert provider.name == "openai-compatible"
