---
name: command_completion_recorder
kind: gate
input_slots:
  - name: command
    type: command
    required: true
output_slots:
  - name: event
    type: event
  - name: notification
    type: notification
window_ms: 5000
refractory_ms: 0
auth_required: false
medium: local
interaction: pull
---

## Command Completion Recorder

This gate consumes a dispatched `command` and performs a bounded pull interaction with the executing locus to obtain a completion acknowledgement. When the executor acknowledges completed work within the timeout window, the gate emits an `event` representing the completion fact. If the executor fails or does not respond before `input_timeout_ms` elapses, the gate emits a `notification` describing the failure or timeout instead, ensuring the flow never blocks on a dead executor.

## Parameters
- `window_ms`: the interval during which the gate actively polls or awaits acknowledgement from the executing locus before considering the interaction stale.
- `input_timeout_ms`: mandatory bound on how long the gate waits for the executor's completion acknowledgement; on expiry the gate emits `notification` instead of `event`, guaranteeing forward progress.
- `refractory_ms`: set to 0 since each command instance is tracked independently and completion recording has no cooldown between distinct commands.
- `auth_required`: false, as this gate performs an internal bookkeeping interaction with the executing locus rather than acting on behalf of an external actor.