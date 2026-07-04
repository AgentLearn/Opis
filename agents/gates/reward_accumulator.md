---
name: reward_accumulator
kind: gate
input_slots:
  - name: event
    type: event
    required: true
  - name: query
    type: query
    required: true
output_slots:
  - name: reward
    type: reward
window_ms: 5000
refractory_ms: 1000
auth_required: false
medium: local
interaction: pull
---

## Reward Accumulator

Consumes completion events for a given actor and appends each to a per-actor ledger, building an auditable running balance. When a redemption query arrives, it computes the current balance from the ledger and emits a reward pulse that can flow as an optional input into a downstream payment gate. The ledger is append-only, so the balance is always replayable from history.

## Parameters
- `window_ms`: the maximum lag tolerated between an event being recorded and it becoming visible in the computed balance; keeps ledger writes batched for efficiency while bounding eventual-consistency drift.
- `refractory_ms`: minimum spacing enforced between successive redemption emissions for the same actor, preventing duplicate reward pulses from rapid repeat queries.
- `auth_required`: not enforced at this gate; actor identity is assumed to be established upstream before events and queries reach this gate.