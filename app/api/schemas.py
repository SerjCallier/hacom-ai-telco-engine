"""HTTP contract for the telemetry diagnostics API.

Pydantic validates shape and range. Semantic validation (does this measurement
contradict the configured capacity?) belongs to the rule engine, because it is a
network-reality question, not a schema question.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.domain.kpis import KpiSnapshot, RadioAccessTech
from app.domain.rules import DiagnosticReport


class KpiTelemetryRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "cell_id": "LTE-MVD-0421",
                    "technology": "LTE",
                    "bandwidth_mhz": 20.0,
                    "prb_utilization_dl_pct": 88.0,
                    "throughput_dl_mbps": 4.2,
                    "cell_capacity_dl_mbps": 120.0,
                    "drop_call_rate_pct": 1.8,
                    "rsrp_dbm": -98.0,
                    "rsrq_db": -14.0,
                    "sinr_db": 8.0,
                    "active_ues": 214,
                }
            ]
        }
    )

    cell_id: str = Field(
        min_length=1,
        max_length=64,
        description="Cell identifier as used by the OSS (eNodeB/gNodeB + sector).",
    )
    technology: RadioAccessTech = Field(
        default=RadioAccessTech.LTE,
        description="Radio access technology of the cell.",
    )
    bandwidth_mhz: float = Field(
        gt=0,
        le=400,
        description="Carrier bandwidth in MHz. Required to compute spectral efficiency.",
    )
    prb_utilization_dl_pct: float = Field(
        ge=0,
        le=100,
        description="Downlink PRB utilisation over the reporting period, in percent.",
    )
    throughput_dl_mbps: float = Field(
        ge=0,
        description="Average downlink user-plane throughput delivered by the cell, in Mbps.",
    )
    cell_capacity_dl_mbps: float = Field(
        gt=0,
        description=(
            "Configured capacity baseline for the cell in Mbps "
            "(bandwidth x expected spectral efficiency x MIMO layers)."
        ),
    )
    drop_call_rate_pct: float = Field(
        ge=0,
        le=100,
        description="Drop call rate over the reporting period, in percent.",
    )
    rsrp_dbm: float = Field(
        ge=-156,
        le=-30,
        description="Average Reference Signal Received Power, in dBm.",
    )
    rsrq_db: float = Field(
        ge=-34.5,
        le=3,
        description="Average Reference Signal Received Quality, in dB (negative scale).",
    )
    sinr_db: float = Field(
        ge=-20,
        le=40,
        description="Average Signal to Interference plus Noise Ratio, in dB.",
    )
    active_ues: int = Field(
        ge=0,
        description="Average number of active user equipment in the cell.",
    )

    def to_snapshot(self) -> KpiSnapshot:
        return KpiSnapshot(
            cell_id=self.cell_id,
            technology=self.technology,
            bandwidth_mhz=self.bandwidth_mhz,
            prb_utilization_dl_pct=self.prb_utilization_dl_pct,
            throughput_dl_mbps=self.throughput_dl_mbps,
            cell_capacity_dl_mbps=self.cell_capacity_dl_mbps,
            drop_call_rate_pct=self.drop_call_rate_pct,
            rsrp_dbm=self.rsrp_dbm,
            rsrq_db=self.rsrq_db,
            sinr_db=self.sinr_db,
            active_ues=self.active_ues,
        )


class FindingOut(BaseModel):
    rule_id: str
    severity: str
    title: str
    rationale: str
    evidence: dict[str, float | int | str]


class DiagnosticResponse(BaseModel):
    cell_id: str
    technology: str
    verdict: str
    findings: list[FindingOut]
    recommendations: list[str]
    metric_sources: dict[str, str]
    engine_version: str

    @classmethod
    def from_report(cls, report: DiagnosticReport) -> DiagnosticResponse:
        return cls.model_validate(report.to_dict())
