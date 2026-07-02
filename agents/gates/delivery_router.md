---
name: delivery_router
kind: gate
input_slots:
  - name: incoming_order
    type: order
    required: true
  - name: destination
    type: location
    required: true
  - name: provider_response
    type: query_response
    required: false
logic: {op: THRESHOLD, n: 2}
input_timeout_ms: 4000
output_slots:
  - name: route
    type: routing_decision
window_ms: 4000
refractory_ms: 500
auth_required: false
medium: internet
interaction: pull
status: draft
confidence: llm-estimate
---

## Delivery Router

Fans out to two or more external mapping service loci via query, collecting a `query_response` from each within `window_ms`. Once at least the threshold number of responses arrive (or the input timeout expires), the gate selects the optimal result and emits a single `routing_decision`. If fewer than the minimum required responses arrive before the window expires, the gate emits a `routing_decision` derived from whichever responses were received; upstream circuit-breaker sentinels are expected to guard each provider locus independently.

## Parameters
- `window_ms`: Maximum time to wait for query responses from all external mapping providers before forcing aggregation on partial results. Tune to the slowest acceptable provider round-trip.
- `refractory_ms`: Minimum interval between successive routing computations for the same input pair, preventing redundant fan-out bursts.
- `interaction`: Set to `pull` because the gate initiates outbound queries to external loci and waits for responses rather than being pushed a complete result.
- `logic`: `THRESHOLD n=2` — the gate fires once at least two `query_response` inputs have arrived, corroborating results across redundant providers before computing a route. Stragglers arriving after firing are ignored.
- `input_timeout_ms`: Maximum time to wait for the threshold to be met before aggregating on whatever `query_response` inputs have been received. Bounds the fan-in when providers are slow or unresponsive.