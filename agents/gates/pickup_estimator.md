---
name: pickup_estimator
kind: gate
input_slots:
  - name: accepted_order
    type: accepted_order
    required: true
  - name: location
    type: location
    required: true
output_slots:
  - name: pickup_time_estimate
    type: estimate
window_ms: 5000
refractory_ms: 500
auth_required: false
medium: local
interaction: pull
status: draft
confidence: llm-estimate
---

## Pickup Estimator

Receives an accepted order and a location identifier, queries the current queue depth at that location, and emits a best-effort time estimate. The gate fires once both input slots are satisfied within the configured window. The emitted estimate represents a computed prediction derived from instantaneous queue state and should be treated as advisory rather than guaranteed.

## Parameters
- `window_ms`: Maximum time the gate holds a partial input set (accepted_order or location alone) before discarding and waiting for a fresh pair. Set to 5000 ms to tolerate minor slot arrival skew.
- `refractory_ms`: Minimum interval between successive estimate emissions for the same input pair, preventing redundant queue polls under rapid re-submission.
- `auth_required`: false — this gate performs a read-only computation and is safe for unauthenticated callers; no sentinel_auth gate is required upstream.
- `interaction`: pull — the gate responds to an inbound query pairing rather than reacting to a pushed event stream.