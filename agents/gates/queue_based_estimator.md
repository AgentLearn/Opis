---
name: queue_based_estimator
version: 2
kind: gate
input_slots:
  - name: query
    type: query
    required: true
  - name: location
    type: location
    required: true
  - name: queue_length_response
    type: query_response
    required: true
output_slots:
  - name: estimate
    type: estimate
window_ms: 500
refractory_ms: 0
auth_required: false
medium: local
interaction: pull
logic: {op: THRESHOLD, n: 3}
input_timeout_ms: 500
---

## Queue Based Estimator

This gate answers a query for a prediction at a given location by applying a rate model to a queue depth delivered as a `queue_length_response` — the pull to the stateful locus responsible for that location is performed by a dedicated resolver instance bound to that locus, not by this gate itself. The estimator fires once it has the query, the location, and the resolver's response, and emits a single estimate. If the resolver's response does not arrive before the configured window expires — whether because the resolver signals a failure or simply because the round trip is slow — the gate emits a conservative fallback estimate rather than blocking indefinitely.

## Parameters
- `window_ms`: the maximum time this gate waits for the resolver's `queue_length_response` to arrive before falling back to a conservative default estimate; keeps response latency bounded under load.
- `auth_required`: false — this gate performs an internal computation and does not gate access on actor identity; any upstream authorisation is handled by the gates that originate the query.
- `input_timeout_ms`: the threshold, measured against `window_ms`, past which waiting for the resolver's response is abandoned and the conservative fallback estimate is emitted instead.
- `refractory_ms`: set to 0 because each query is independent and no cooldown between successive queries is required.