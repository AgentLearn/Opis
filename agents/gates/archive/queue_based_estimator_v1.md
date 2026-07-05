---
name: queue_based_estimator
kind: gate
input_slots:
  - name: query
    type: query
    required: true
  - name: location
    type: location
    required: true
output_slots:
  - name: estimate
    type: estimate
window_ms: 500
refractory_ms: 0
auth_required: false
medium: local
interaction: pull
---

## Queue Based Estimator

This gate answers a query for a prediction at a given location by pulling the current queue depth from the stateful locus responsible for that location and applying a rate model to compute an estimate. It fires on demand, one pull per incoming query, and emits a single estimate in response. If the pull to the stateful locus does not return within the configured timeout, the gate emits a conservative fallback estimate rather than blocking indefinitely.

## Parameters
- `window_ms`: the maximum time allowed for the round trip to the stateful locus before falling back to a conservative default estimate; keeps response latency bounded under load.
- `auth_required`: false — this gate performs an internal computation and does not gate access on actor identity; any upstream authorisation is handled by the gates that originate the query.
- `input_timeout_ms`: the threshold, measured against `window_ms`, past which the pull to the stateful locus is abandoned and the conservative fallback estimate is emitted instead.
- `refractory_ms`: set to 0 because each query is independent and no cooldown between successive queries is required.