---
name: event_reward_accumulator
kind: gate
input_slots:
  - name: event
    type: event
    required: true
output_slots:
  - name: reward
    type: reward
  - name: notification
    type: notification
window_ms: 0
refractory_ms: 0
auth_required: false
medium: local
---

## Event Reward Accumulator

This gate consumes `event` pulses representing completed units of work and maintains a per-key running balance of accrued credit. On each accrual it emits a `reward` pulse carrying the updated credit, available for optional consumption by any downstream regulator, and a `notification` pulse informing the owning actor of the balance change. It operates purely on push semantics — there is no query slot, and no request/response cycle is required to produce a `reward`.

## Parameters
- `window_ms`: set to 0; the gate has no aggregation window and processes each `event` pulse as it arrives.
- `refractory_ms`: set to 0; every qualifying `event` may trigger a new `reward`/`notification` emission with no enforced cooldown. Instances may raise this to coalesce bursts of events into a single emission.
- `auth_required`: false; this gate performs internal state accumulation and emits pulses to already-authorized downstream consumers, so it does not itself gate on actor authentication.
- `medium`: local; the gate is expected to run colocated with the event source and its downstream consumers within the same processing flow.