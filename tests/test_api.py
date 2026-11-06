from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

client = TestClient(create_app())


def test_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_sample_payload_is_accepted_by_the_analyze_endpoint() -> None:
    payload = client.get("/api/v1/telemetry/sample").json()

    response = client.post("/api/v1/telemetry/analyze", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["cell_id"] == payload["cell_id"]
    assert body["verdict"] in {"healthy", "watch", "degraded", "critical"}
    assert "metric_sources" in body


def test_analyze_detects_congestion_end_to_end() -> None:
    response = client.post(
        "/api/v1/telemetry/analyze",
        json={
            "cell_id": "LTE-MVD-0421",
            "technology": "LTE",
            "bandwidth_mhz": 20.0,
            "prb_utilization_dl_pct": 96.0,
            "throughput_dl_mbps": 30.0,
            "cell_capacity_dl_mbps": 120.0,
            "drop_call_rate_pct": 2.6,
            "rsrp_dbm": -96.0,
            "rsrq_db": -13.0,
            "sinr_db": 7.0,
            "active_ues": 260,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "critical"
    rule_ids = {f["rule_id"] for f in body["findings"]}
    assert "RADIO_RESOURCE_CONGESTION" in rule_ids
    assert body["recommendations"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("prb_utilization_dl_pct", 140.0),
        ("prb_utilization_dl_pct", -1.0),
        ("bandwidth_mhz", 0.0),
        ("rsrp_dbm", -200.0),
    ],
)
def test_out_of_range_values_are_rejected_with_422(field: str, value: float) -> None:
    payload = client.get("/api/v1/telemetry/sample").json()
    payload[field] = value

    response = client.post("/api/v1/telemetry/analyze", json=payload)

    assert response.status_code == 422


def test_openapi_schema_is_generated() -> None:
    schema = client.get("/openapi.json").json()

    assert "/api/v1/telemetry/analyze" in schema["paths"]
