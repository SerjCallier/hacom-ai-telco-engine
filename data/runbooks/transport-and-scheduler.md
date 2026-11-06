# Transport and scheduler efficiency

> Source: Internal engineering note. Counters follow 3GPP TS 32.425 (E-UTRAN); this is an operational summary, not a verbatim standard extract.

## Symptom

Users report low speed, but radio indicators look healthy: reference signal power is
good, SINR is good, and PRB utilisation has spare room. Adding capacity does not help.

## Detection

Compute spectral efficiency as delivered throughput in Mbps divided by carrier
bandwidth in MHz. Around 1.0 bit per second per Hertz or below, with healthy radio
conditions and spare PRBs, means the constraint is not the radio interface.

Check in this order:

- transport or backhaul saturation between the cell site and the aggregation point;
- scheduler configuration and bearer weights;
- packet loss and retransmission counters on the backhaul link;
- QoS class mapping for the affected traffic type.

## Remediation

Fix the transport or configuration bottleneck before touching radio parameters. Radio
changes applied to a transport-limited cell reduce coverage without improving speed,
because the radio interface was never the constraint.

## Verification

Spectral efficiency should rise while PRB utilisation stays roughly flat. If utilisation
rises with efficiency, the original constraint was in the radio domain after all and the
diagnosis was wrong.
