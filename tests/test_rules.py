from __future__ import annotations

from typing import Any

import pytest

from app.config import Thresholds
from app.domain.kpis import KpiSnapshot, RadioAccessTech
from app.domain.rules import Severity, Verdict, diagnose

THRESHOLDS = Thresholds()


def snap(**overrides: Any) -> KpiSnapshot:
    base: dict[str, Any] = {
        "cell_id": "LTE-MVD-0421",
        "technology": RadioAccessTech.LTE,
        "bandwidth_mhz": 20.0,
        "prb_utilization_dl_pct": 45.0,
        "throughput_dl_mbps": 60.0,
        "cell_capacity_dl_mbps": 120.0,
        "drop_call_rate_pct": 0.2,
        "rsrp_dbm": -85.0,
        "rsrq_db": -9.0,
        "sinr_db": 20.0,
        "active_ues": 120,
    }
    base.update(overrides)
    return KpiSnapshot(**base)


def rule_ids(report) -> set[str]:
    return {f.rule_id for f in report.findings}


def test_healthy_cell_reports_no_findings() -> None:
    report = diagnose(snap(), THRESHOLDS)

    assert report.verdict is Verdict.HEALTHY
    assert report.findings == ()
    assert report.recommendations == ()


def test_busy_cell_delivering_well_is_not_congestion() -> None:
    """High PRB alone is load, not congestion: the differentiator of this engine."""
    report = diagnose(
        snap(prb_utilization_dl_pct=92.0, throughput_dl_mbps=110.0),
        THRESHOLDS,
    )

    assert "RADIO_RESOURCE_CONGESTION" not in rule_ids(report)
    assert "CAPACITY_HEADROOM_EXHAUSTED" in rule_ids(report)
    assert report.verdict is Verdict.WATCH


def test_prb_saturation_with_poor_delivery_is_congestion() -> None:
    report = diagnose(
        snap(prb_utilization_dl_pct=88.0, throughput_dl_mbps=40.0),
        THRESHOLDS,
    )

    assert "RADIO_RESOURCE_CONGESTION" in rule_ids(report)
    assert report.verdict is Verdict.DEGRADED


def test_severe_congestion_escalates_to_critical() -> None:
    report = diagnose(
        snap(prb_utilization_dl_pct=96.0, throughput_dl_mbps=30.0),
        THRESHOLDS,
    )

    congestion = next(f for f in report.findings if f.rule_id == "RADIO_RESOURCE_CONGESTION")
    assert congestion.severity is Severity.CRITICAL
    assert report.verdict is Verdict.CRITICAL


def test_capacity_pressure_is_watch_only() -> None:
    report = diagnose(
        snap(prb_utilization_dl_pct=74.0, throughput_dl_mbps=90.0),
        THRESHOLDS,
    )

    assert rule_ids(report) == {"CAPACITY_PRESSURE"}
    assert report.verdict is Verdict.WATCH


def test_weak_rsrp_with_negative_sinr_is_a_coverage_problem() -> None:
    report = diagnose(snap(rsrp_dbm=-115.0, sinr_db=-2.0), THRESHOLDS)

    assert "COVERAGE_LIMITED" in rule_ids(report)
    assert "INTERFERENCE_LIMITED" not in rule_ids(report)
    assert report.verdict is Verdict.DEGRADED


def test_good_rsrp_with_poor_sinr_is_an_interference_problem() -> None:
    """The same poor quality, opposite root cause: this is the RAN judgement layer."""
    report = diagnose(snap(rsrp_dbm=-84.0, sinr_db=2.0), THRESHOLDS)

    assert "INTERFERENCE_LIMITED" in rule_ids(report)
    assert "COVERAGE_LIMITED" not in rule_ids(report)


def test_weak_rsrp_with_positive_sinr_is_only_a_watch() -> None:
    report = diagnose(snap(rsrp_dbm=-112.0, sinr_db=8.0), THRESHOLDS)

    assert "WEAK_COVERAGE_CELL_EDGE" in rule_ids(report)
    assert "COVERAGE_LIMITED" not in rule_ids(report)
    assert report.verdict is Verdict.WATCH


def test_low_spectral_efficiency_with_healthy_radio_points_away_from_rf() -> None:
    report = diagnose(
        snap(prb_utilization_dl_pct=30.0, throughput_dl_mbps=8.0, sinr_db=18.0),
        THRESHOLDS,
    )

    assert "LOW_SPECTRAL_EFFICIENCY" in rule_ids(report)
    assert report.verdict is Verdict.WATCH


def test_drop_call_rate_above_target_is_flagged() -> None:
    report = diagnose(snap(drop_call_rate_pct=1.6), THRESHOLDS)

    finding = next(f for f in report.findings if f.rule_id == "HIGH_DROP_CALL_RATE")
    assert finding.severity is Severity.DEGRADED


def test_drop_call_rate_far_above_target_is_critical() -> None:
    report = diagnose(snap(drop_call_rate_pct=3.4), THRESHOLDS)

    finding = next(f for f in report.findings if f.rule_id == "HIGH_DROP_CALL_RATE")
    assert finding.severity is Severity.CRITICAL


def test_throughput_above_capacity_is_flagged_as_data_quality() -> None:
    report = diagnose(snap(throughput_dl_mbps=130.0), THRESHOLDS)

    assert "DATA_THROUGHPUT_EXCEEDS_CAPACITY" in rule_ids(report)


def test_findings_are_ordered_by_severity() -> None:
    report = diagnose(
        snap(prb_utilization_dl_pct=95.0, throughput_dl_mbps=30.0, drop_call_rate_pct=9.0),
        THRESHOLDS,
    )

    severities = [int(f.severity) for f in report.findings]
    assert severities == sorted(severities, reverse=True)


def test_diagnose_is_deterministic() -> None:
    snapshot = snap(prb_utilization_dl_pct=88.0, throughput_dl_mbps=40.0)

    first = diagnose(snapshot, THRESHOLDS)
    second = diagnose(snapshot, THRESHOLDS)

    assert first == second


@pytest.mark.parametrize("prb", [0.0, 50.0, 100.0])
def test_prb_boundaries_do_not_raise(prb: float) -> None:
    diagnose(snap(prb_utilization_dl_pct=prb), THRESHOLDS)
