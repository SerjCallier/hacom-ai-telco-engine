# Radio resource congestion

> Source: Internal engineering note. Measurement definitions follow 3GPP TS 32.425 (E-UTRAN); this is an operational summary, not a verbatim standard extract.

## Symptom

Users report slow data in a specific area during busy hours, while the cell stays
accessible and keeps serving traffic. Signalling load is normal and there are no
hardware alarms. The complaint is throughput, not availability.

## Detection

Congestion is not the same as high load. A cell with PRB utilisation above 80% that
still delivers close to its capacity baseline is doing its job.

Treat the cell as congested only when both conditions hold over the same reporting
period:

- downlink PRB utilisation at or above the planning limit (typically 80%), and
- delivered throughput below 60% of the configured capacity baseline.

When utilisation is high but delivered throughput is healthy, classify the cell as
fully loaded with no headroom and plan capacity instead of firefighting.

## Root-cause branches

Separate three cases before acting:

- **Genuine capacity shortfall.** High active user count, uniform degradation across
  the sector, sustained over weeks.
- **Traffic concentration.** A stadium, event or transport hub pulling traffic into
  one sector for a few hours.
- **Scheduler or QoS misconfiguration.** Utilisation is high but the radio link is
  fine; check bearer weights and guaranteed bit rate settings.

## Remediation

Ordered by cost and reversibility:

1. Review scheduler and QoS weights before any hardware change.
2. Enable Mobility Load Balancing so neighbouring carriers absorb part of the load.
3. Activate a second carrier or carrier aggregation where spectrum is available.
4. Densify with small cells for persistent hotspot demand.

## Verification

Re-measure over the same reporting window after each change. A fix that moves
utilisation without improving delivered throughput has shifted the bottleneck rather
than removed it.
