---
name: routing_decision_aggregator
kind: gate
input_slots:
  - name: query
    type: query
    required: true
  - name: provider_response
    type: query_response
    required: false
output_slots:
  - name: provider_query
    type: query
  - name: routing_decision
    type: routing_decision
window_ms: 3000
refractory_ms: 500
auth_required: false
medium: internet
---

## Routing Decision Aggregator

Fans an incoming query out to multiple external providers and collects their query_response inputs, reconciling whichever subset arrives within the window into a single routing_decision. Firing occurs once a minimum threshold count of responses has been received, or when the window elapses, whichever comes first — it does not wait for every provider to respond. Slow or failing providers beyond the threshold are simply excluded from the reconciliation.

## Parameters
- `window_ms`: maximum time allowed to collect provider responses before forcing a fire with whatever has arrived; balances latency against reconciliation quality.
- `refractory_ms`: minimum spacing between successive aggregation cycles to prevent redundant re-querying while a prior cycle's decision is still fresh.
- `auth_required`: false — this gate operates as an internal computation stage and does not itself gate access on caller identity.
- `threshold`: the minimum count of provider_response inputs (n ≥ 2) required to consider the aggregation satisfied before the window elapses.