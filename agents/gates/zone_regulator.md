---
name: zone_regulator
kind: regulator
input_slots:
  - name: inbound_order
    type: order
    required: true
  - name: zone_routing
    type: routing_decision
    required: true
output_slots:
  - name: passed_order
    type: accepted_order
  - name: blocked_order
    type: rejected_order
window_ms: 60000
refractory_ms: 5000
auth_required: false
medium: local
---

## Zone Regulator

This gate applies demand-based rate limiting and pricing adjustment to inbound orders conditioned on a zone's current demand signal. On each activation it evaluates the per-zone request counter against a configured demand threshold: if the counter is within limit, it emits an `accepted_order` with a surge-adjusted cost factor embedded from the `routing_decision`; if the counter exceeds the threshold within the active window, it emits a `rejected_order` and the order is not forwarded. Per-zone counters are maintained internally and reset at the boundary of each `window_ms` interval.

## Parameters
- `window_ms`: Duration of the sliding window (60 000 ms = 1 minute) over which per-zone order counts are accumulated before the counter resets.
- `refractory_ms`: Minimum quiet period after a rate-limit rejection before the gate re-evaluates new arrivals for that zone, preventing rapid retry floods.
- `auth_required`: Set to `false`; this gate operates on already-validated flow data and does not require upstream sentinel authentication itself. Set to `true` if the gate is placed behind a protected boundary and `sentinel_auth` must appear upstream.