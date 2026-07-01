---
name: order_intake
kind: gate
input_slots:
  - name: order
    type: order
    required: true
  - name: auth_token
    type: auth_token
    required: true
output_slots:
  - name: accepted_order
    type: accepted_order
  - name: rejected_order
    type: rejected_order
window_ms: 5000
refractory_ms: 0
auth_required: true
medium: internet
---

## Order Intake

Receives a raw order alongside a valid auth token and performs a syntactic well-formedness check: slot values are present, quantities are within representable bounds, and referenced item identifiers are non-empty. On success it promotes the order to an `accepted_order` and emits it for downstream processing. On failure it emits a `rejected_order` and the pipeline terminates for that request.

## Parameters
- `window_ms`: Maximum time allowed for the well-formedness check to complete before the gate drops the input and emits a `rejected_order`; set to 5 000 ms to accommodate high-latency ingress paths.
- `auth_required`: `true` — a valid `auth_token` must be present on the `auth_token` slot; `sentinel_auth` must appear upstream in any flow that wires this gate.
- `refractory_ms`: Set to 0 because repeated rapid submissions from the same actor are permitted; rate-limiting, if needed, is the responsibility of an upstream regulator.