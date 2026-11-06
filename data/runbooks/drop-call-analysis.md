# Drop call analysis

> Source: Internal engineering note. Counters follow 3GPP TS 32.425 (E-UTRAN); this is an operational summary, not a verbatim standard extract.

## Symptom

A cell or cluster reports a drop call rate above the operator target while overall
traffic volume looks normal. The raw number says nothing about the cause.

## Detection

Compare the drop call rate against the operator target for the service mix, not against
a generic industry number. Break the rate down by release cause before drawing any
conclusion; an aggregate rate hides whether the network is dropping calls for radio
reasons, handover failures or core-side releases.

A drop call rate that rises together with weak RSRP in the same cells points at radio
coverage. A rate that rises while RSRP and SINR stay healthy points away from radio.

## Release cause classification

Classify the drop call rate by release cause before anything else. A handover-driven
drop rate behaves differently from a radio-driven one, and the fix is different.

- Radio connection lost with poor RF quality: coverage or interference.
- Handover failure: missing neighbour relation, too-late or too-early handover
  parameters, or a target cell that is itself congested.
- Core or transport release: outside the radio domain, escalate to the packet core
  team with the cause code rather than adjusting tilt.

## Remediation

Do not change radio parameters before the release cause breakdown exists. Tilt changes
applied to a core-side release problem degrade coverage without fixing the drops.

## Verification

Track the drop call rate and the cause distribution together after the change. A
falling aggregate rate with an unchanged cause distribution can simply be traffic
variation.
