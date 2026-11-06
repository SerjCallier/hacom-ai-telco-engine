"""RAN KPI value objects.

The snapshot is a frozen value object so the rule engine is a set of pure
functions: no I/O, no clock, no global state. That makes every diagnostic
reproducible and testable without a network or a model.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RadioAccessTech(StrEnum):
    LTE = "LTE"
    NR = "NR"


@dataclass(frozen=True, slots=True)
class KpiSnapshot:
    """One observation of a cell over a reporting period.

    ``cell_capacity_dl_mbps`` is the configured capacity baseline for the cell
    (bandwidth x expected spectral efficiency x MIMO layers), not a measurement.
    It is required because raw throughput is meaningless without a reference:
    5 Mbps is healthy on a 3 MHz cell and pathological on a 100 MHz one.
    """

    cell_id: str
    technology: RadioAccessTech
    bandwidth_mhz: float
    prb_utilization_dl_pct: float
    throughput_dl_mbps: float
    cell_capacity_dl_mbps: float
    drop_call_rate_pct: float
    rsrp_dbm: float
    rsrq_db: float
    sinr_db: float
    active_ues: int

    @property
    def capacity_ratio_pct(self) -> float:
        """Delivered throughput as a share of the configured capacity baseline."""
        if self.cell_capacity_dl_mbps <= 0:
            return 0.0
        return self.throughput_dl_mbps / self.cell_capacity_dl_mbps * 100.0

    @property
    def spectral_efficiency_bps_hz(self) -> float:
        """Bits per second per Hertz.

        Reference points for LTE downlink: around 1.0 bps/Hz or less indicates a
        problem; 1.5-2.5 bps/Hz is a typical healthy range; higher values appear
        with wideband carriers and higher-order MIMO. These are engineering
        rules of thumb, not standardised limits.
        """
        if self.bandwidth_mhz <= 0:
            return 0.0
        return self.throughput_dl_mbps / self.bandwidth_mhz
