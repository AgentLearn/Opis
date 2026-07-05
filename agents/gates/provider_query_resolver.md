---
name: provider_query_resolver
kind: gate
input_slots:
  - name: query
    type: query
    required: true
output_slots:
  - name: query_response
    type: query_response
  - name: timeout_event
    type: event
window_ms: 5000
refractory_ms: 0
input_timeout_ms: 3000
auth_required: false
medium: internet
---

## Provider Query Resolver

This gate accepts a `query` and performs a bounded pull against a single designated external provider locus, making that provider's response a first-class produced type for downstream path proofs. On success it emits `query_response`; if the provider does not answer within `input_timeout_ms` it emits `event` instead, so timeout/failure is explicit and provable in the flow. One instance is bound to exactly one external provider; aggregating across N providers requires N instances wired into the consuming gate's `query_response` slot.

## Parameters
- `window_ms`: the overall processing window during which the gate accepts a `query` and completes either output path.
- `refractory_ms`: minimum quiet period after emitting an output before the gate accepts another `query`; set to `0` since each query is independent and no debounce is needed.
- `input_timeout_ms`: mandatory deadline for the bound external locus to answer the pull; exceeding it forces emission of the `timeout_event` output instead of `query_response`.
- `auth_required`: `false` — this gate mediates an internal request/response cycle and does not itself gate access for an external actor; any actor-facing authorisation happens upstream of the originating `query`.
- `medium`: `internet` — the bound provider locus is reached over a network boundary external to the local flow.