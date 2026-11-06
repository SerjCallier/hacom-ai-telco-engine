"""Deterministic RAN diagnostic rules.

Design intent: the rules engine is the part of this system that must never
depend on an LLM. It encodes radio-engineering judgement that a generic backend
developer would not write, for example distinguishing a *loaded* cell from a
*congested* one, or separating a coverage problem from an interference problem
when RSRP alone looks the same.

Every rule is a pure function ``(KpiSnapshot, Thresholds) -> Finding | None``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum

from app.config import ENGINE_VERSION, Thresholds
from app.domain.kpis import KpiSnapshot


class Severity(IntEnum):
    INFO = 1
    WATCH = 2
    DEGRADED = 3
    CRITICAL = 4


class Verdict(StrEnum):
    HEALTHY = "healthy"
    WATCH = "watch"
    DEGRADED = "degraded"
    CRITICAL = "critical"


SEVERITY_TO_VERDICT: dict[Severity, Verdict] = {
    Severity.INFO: Verdict.WATCH,
    Severity.WATCH: Verdict.WATCH,
    Severity.DEGRADED: Verdict.DEGRADED,
    Severity.CRITICAL: Verdict.CRITICAL,
}


@dataclass(frozen=True, slots=True)
class Finding:
    rule_id: str
    severity: Severity
    title: str
    rationale: str
    evidence: dict[str, float | int | str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DiagnosticReport:
    cell_id: str
    technology: str
    verdict: Verdict
    findings: tuple[Finding, ...]
    recommendations: tuple[str, ...]
    metric_sources: dict[str, str]
    engine_version: str = ENGINE_VERSION

    def to_dict(self) -> dict[str, object]:
        """Serialisable form used by the HTTP contract and by the agent tools."""
        return {
            "cell_id": self.cell_id,
            "technology": self.technology,
            "verdict": self.verdict.value,
            "findings": [
                {
                    "rule_id": f.rule_id,
                    "severity": f.severity.name.lower(),
                    "title": f.title,
                    "rationale": f.rationale,
                    "evidence": f.evidence,
                }
                for f in self.findings
            ],
            "recommendations": list(self.recommendations),
            "metric_sources": self.metric_sources,
            "engine_version": self.engine_version,
        }


METRIC_SOURCES: dict[str, str] = {
    "rsrp_dbm": "3GPP TS 36.214 (E-UTRA physical layer measurements)",
    "rsrq_db": "3GPP TS 36.214 (E-UTRA physical layer measurements)",
    "sinr_db": "Vendor/OSS-derived quality indicator, not a standardised UE report in TS 36.214",
    "prb_utilization_dl_pct": "3GPP TS 32.425 (E-UTRAN PRB usage) / TS 28.552 (NR)",
    "throughput_dl_mbps": "3GPP TS 32.425 (E-UTRAN throughput measurements)",
    "drop_call_rate_pct": "Derived from E-RAB release counters, 3GPP TS 32.425",
}

RECOMMENDATIONS: dict[str, str] = {
    "DATA_THROUGHPUT_EXCEEDS_CAPACITY": (
        "Reconcile the counter reporting period and refresh the capacity baseline "
        "before acting on this report."
    ),
    "RADIO_RESOURCE_CONGESTION": (
        "Sustained PRB saturation with poor delivered efficiency: enable Mobility Load "
        "Balancing, evaluate a second carrier (CA) or small-cell densification, and review "
        "scheduler/QoS weights before adding hardware."
    ),
    "CAPACITY_HEADROOM_EXHAUSTED": (
        "The cell is serving well but has no spare radio resources: start the capacity "
        "plan now, before demand growth turns this into congestion."
    ),
    "CAPACITY_PRESSURE": (
        "PRB utilisation is approaching the planning limit: track the trend and plan "
        "capacity action ahead of saturation."
    ),
    "COVERAGE_LIMITED": (
        "Weak reference signal combined with poor SINR: audit RF power configuration "
        "(ReferenceSignalPower) and antenna tilt/azimuth to close the coverage gap."
    ),
    "WEAK_COVERAGE_CELL_EDGE": (
        "Weak but usable cell-edge signal: validate handover margins and neighbour "
        "relations before changing tilt, otherwise mobility gets worse."
    ),
    "INTERFERENCE_LIMITED": (
        "Good RSRP with poor SINR is not a coverage problem: audit PCI/PRACH-root "
        "conflicts, antenna overshoot and pilot pollution."
    ),
    "LOW_SPECTRAL_EFFICIENCY": (
        "Radio conditions look healthy while delivered bits per Hertz are low: check "
        "scheduler parameters, backhaul capacity and QCI/QoS mapping."
    ),
    "HIGH_DROP_CALL_RATE": (
        "Break the drop reason codes down (radio, handover, core) before touching radio "
        "parameters, so the fix targets the actual release cause."
    ),
}


def _check_data_quality(s: KpiSnapshot, p: Thresholds) -> Finding | None:
    if s.throughput_dl_mbps > s.cell_capacity_dl_mbps * 1.05:
        return Finding(
            rule_id="DATA_THROUGHPUT_EXCEEDS_CAPACITY",
            severity=Severity.WATCH,
            title="Reported throughput exceeds the configured cell capacity",
            rationale=(
                "Throughput above the capacity baseline usually means a stale baseline or "
                "counters aggregated over different periods. Diagnostics built on "
                "inconsistent inputs are not trustworthy."
            ),
            evidence={
                "throughput_dl_mbps": s.throughput_dl_mbps,
                "cell_capacity_dl_mbps": s.cell_capacity_dl_mbps,
            },
        )
    return None


def _check_radio_resources(s: KpiSnapshot, p: Thresholds) -> Finding | None:
    """Separate a busy cell from a congested one.

    High PRB utilisation on its own is not congestion: a fully loaded cell that
    still delivers near its capacity baseline is doing its job. Congestion is
    resource exhaustion *plus* degraded delivered efficiency.
    """
    prb = s.prb_utilization_dl_pct
    efficiency_pct = s.capacity_ratio_pct

    if prb >= p.severe_congestion_prb_pct and efficiency_pct < p.severe_congestion_efficiency_pct:
        return Finding(
            rule_id="RADIO_RESOURCE_CONGESTION",
            severity=Severity.CRITICAL,
            title="Severe radio resource congestion",
            rationale=(
                "PRB utilisation is at or above the severe limit while delivered throughput "
                "is below 40% of the cell capacity baseline. Users are competing for radio "
                "resources and losing."
            ),
            evidence={
                "prb_utilization_dl_pct": prb,
                "capacity_ratio_pct": round(efficiency_pct, 1),
            },
        )

    if prb >= p.congestion_prb_pct and efficiency_pct < p.congestion_efficiency_pct:
        return Finding(
            rule_id="RADIO_RESOURCE_CONGESTION",
            severity=Severity.DEGRADED,
            title="Radio resource congestion",
            rationale=(
                "PRB utilisation is at or above the congestion limit while delivered "
                "throughput is below 60% of the cell capacity baseline: the cell is out of "
                "radio resources, not merely busy."
            ),
            evidence={
                "prb_utilization_dl_pct": prb,
                "capacity_ratio_pct": round(efficiency_pct, 1),
            },
        )

    if prb >= p.severe_congestion_prb_pct:
        return Finding(
            rule_id="CAPACITY_HEADROOM_EXHAUSTED",
            severity=Severity.WATCH,
            title="Cell is fully loaded with no spare radio resources",
            rationale=(
                "Delivered throughput is healthy, so this is not congestion yet, but PRB "
                "utilisation leaves no headroom for traffic growth."
            ),
            evidence={
                "prb_utilization_dl_pct": prb,
                "capacity_ratio_pct": round(efficiency_pct, 1),
            },
        )

    if prb >= p.capacity_watch_prb_pct:
        return Finding(
            rule_id="CAPACITY_PRESSURE",
            severity=Severity.WATCH,
            title="Radio resource utilisation approaching the planning limit",
            rationale=(
                "PRB utilisation is in the watch band. Delivered throughput is still "
                "healthy, so the action is planning, not firefighting."
            ),
            evidence={
                "prb_utilization_dl_pct": prb,
                "capacity_ratio_pct": round(efficiency_pct, 1),
            },
        )

    return None


def _check_coverage(s: KpiSnapshot, p: Thresholds) -> Finding | None:
    if s.rsrp_dbm > p.weak_rsrp_dbm:
        return None

    if s.sinr_db < p.coverage_sinr_db:
        return Finding(
            rule_id="COVERAGE_LIMITED",
            severity=Severity.DEGRADED,
            title="Coverage-limited cell",
            rationale=(
                "RSRP is below the weak-signal limit and SINR is negative: the cell is "
                "noise-limited because the wanted signal itself is too weak."
            ),
            evidence={"rsrp_dbm": s.rsrp_dbm, "sinr_db": s.sinr_db},
        )

    return Finding(
        rule_id="WEAK_COVERAGE_CELL_EDGE",
        severity=Severity.WATCH,
        title="Weak but usable cell-edge signal",
        rationale=(
            "RSRP is below the weak-signal limit while SINR stays positive. That pattern is "
            "usual at the cell edge and is not automatically a fault."
        ),
        evidence={"rsrp_dbm": s.rsrp_dbm, "sinr_db": s.sinr_db},
    )


def _check_interference(s: KpiSnapshot, p: Thresholds) -> Finding | None:
    if s.rsrp_dbm <= p.good_rsrp_dbm:
        return None
    if s.sinr_db >= p.interference_sinr_db:
        return None

    return Finding(
        rule_id="INTERFERENCE_LIMITED",
        severity=Severity.DEGRADED,
        title="Interference-limited cell",
        rationale=(
            "Reference signal power is good while SINR is poor. The signal is strong enough "
            "but the noise floor is high, which points to interference rather than coverage."
        ),
        evidence={"rsrp_dbm": s.rsrp_dbm, "sinr_db": s.sinr_db, "rsrq_db": s.rsrq_db},
    )


def _check_spectral_efficiency(s: KpiSnapshot, p: Thresholds) -> Finding | None:
    if s.prb_utilization_dl_pct >= p.congestion_prb_pct:
        return None
    if s.sinr_db < p.interference_sinr_db:
        return None

    efficiency = s.spectral_efficiency_bps_hz
    if efficiency >= p.min_spectral_efficiency_bps_hz:
        return None

    return Finding(
        rule_id="LOW_SPECTRAL_EFFICIENCY",
        severity=Severity.WATCH,
        title="Low spectral efficiency with healthy radio conditions",
        rationale=(
            "There are spare PRBs and SINR is healthy, yet bits per Hertz are low. When "
            "radio conditions are not the constraint, the suspect is the scheduler, the "
            "transport network or QoS configuration."
        ),
        evidence={
            "spectral_efficiency_bps_hz": round(efficiency, 2),
            "bandwidth_mhz": s.bandwidth_mhz,
            "prb_utilization_dl_pct": s.prb_utilization_dl_pct,
            "sinr_db": s.sinr_db,
        },
    )


def _check_drop_call_rate(s: KpiSnapshot, p: Thresholds) -> Finding | None:
    dcr = s.drop_call_rate_pct
    if dcr <= p.max_drop_call_rate_pct:
        return None

    severity = Severity.CRITICAL if dcr > p.critical_drop_call_rate_pct else Severity.DEGRADED

    return Finding(
        rule_id="HIGH_DROP_CALL_RATE",
        severity=severity,
        title="Drop call rate above policy target",
        rationale=(
            "The drop call rate exceeds the operator target. Combined with the RF findings "
            "in this report it separates a coverage/handover cause from a core-side cause."
        ),
        evidence={"drop_call_rate_pct": dcr, "policy_max_pct": p.max_drop_call_rate_pct},
    )


Rule = Callable[[KpiSnapshot, Thresholds], Finding | None]

RULES: tuple[Rule, ...] = (
    _check_data_quality,
    _check_radio_resources,
    _check_coverage,
    _check_interference,
    _check_spectral_efficiency,
    _check_drop_call_rate,
)


def _verdict(findings: tuple[Finding, ...]) -> Verdict:
    if not findings:
        return Verdict.HEALTHY
    worst = max(f.severity for f in findings)
    return SEVERITY_TO_VERDICT[worst]


def _recommendations(findings: tuple[Finding, ...]) -> tuple[str, ...]:
    seen: list[str] = []
    for finding in findings:
        text = RECOMMENDATIONS.get(finding.rule_id)
        if text and text not in seen:
            seen.append(text)
    return tuple(seen)


def diagnose(snapshot: KpiSnapshot, thresholds: Thresholds) -> DiagnosticReport:
    findings = tuple(
        finding for rule in RULES if (finding := rule(snapshot, thresholds)) is not None
    )
    ordered = tuple(sorted(findings, key=lambda f: (-int(f.severity), f.rule_id)))
    return DiagnosticReport(
        cell_id=snapshot.cell_id,
        technology=snapshot.technology.value,
        verdict=_verdict(ordered),
        findings=ordered,
        recommendations=_recommendations(ordered),
        metric_sources=METRIC_SOURCES,
    )
