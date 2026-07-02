---
name: order_validator
kind: gate
input_slots:
  - name: inbound_order
    type: accepted_order
    required: true
  - name: confirmed_payment
    type: payment_confirmed
    required: true
  - name: inventory_result
    type: inventory_update
    required: true
  - name: location_check
    type: routing_decision
    required: true
output_slots:
  - name: valid_order
    type: accepted_order
  - name: invalid_order
    type: rejected_order
window_ms: 8000
refractory_ms: 500
auth_required: true
medium: lan
status: draft
confidence: llm-estimate
---

## Order Validator

Aggregates a confirmed payment with results from upstream inventory and routing sub-gates
to determine whether an order is fit for submission. Fires when all four required input
slots arrive within the window, emitting `accepted_order` if all checks pass or
`rejected_order` otherwise. Composes rather than internalises sub-gate concerns — each
validation dimension can be extended or replaced independently.

## Parameters
- `window_ms`: 8000 — accommodates combined worst-case latency from upstream sub-gates; tune once p99 latencies are profiled.
- `refractory_ms`: 500 — suppresses duplicate slot deliveries from retried synapse pushes.
- `auth_required`: true — sentinel_auth must appear upstream.
- `medium`: lan — all sub-gate results travel within the same service mesh.