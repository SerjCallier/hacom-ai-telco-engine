# Coverage and interference

> Source: Internal engineering note. Measurement definitions follow 3GPP TS 36.214 (E-UTRA physical layer measurements); this is an operational summary, not a verbatim standard extract.

## Symptom

Both trouble classes look identical on a dashboard that only plots RSRP: a cluster of
users with poor quality and elevated retransmissions. They require opposite fixes, so
RSRP alone must never be used to decide.

## Detection

Combine reference signal power with a quality indicator:

- weak RSRP and negative SINR means the wanted signal is too weak: coverage-limited.
- good RSRP and poor SINR means the signal is strong but the noise floor is high:
  interference-limited.
- weak RSRP with positive SINR is a normal cell edge condition, not a fault.

## Coverage-limited branch

Coverage-limited means weak RSRP with negative SINR: the wanted signal arrives too weak
relative to the noise floor, so quality cannot be recovered by scheduling or capacity.

Typical causes are an obstruction, a coverage hole behind terrain, or an antenna whose
mechanical or electrical tilt no longer matches the planned footprint.

Fixes, in order of reversibility: verify ReferenceSignalPower and transmit power
configuration, review electrical tilt, then mechanical tilt and azimuth, and only then
consider a new site or repeater.

## Interference-limited branch

Interference-limited means good RSRP with poor SINR: the reference signal is strong but
the noise floor is high, so the limit is other cells rather than distance.

Typical causes are PCI or PRACH root sequence conflicts, antenna overshoot from a
neighbouring site, or pilot pollution where several cells arrive with similar power.

Fixes: audit PCI and PRACH planning, check downtilt on the dominant interferer, and
review neighbour cell lists for missing or duplicated relations. Raising power on the
victim cell makes pilot pollution worse.

## Verification

Confirm the change with both power and quality indicators together. An improvement in
RSRP without an improvement in SINR usually means the interference source was not
addressed.
