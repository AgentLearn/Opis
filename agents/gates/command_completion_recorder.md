---
name: command_completion_recorder
version: 2
kind: gate
input_slots:
  - name: command
    type: command
    required: true
  - name: ack
    type: ack
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
interaction: push
---

## Command Completion Recorder

This gate consumes a dispatched `command` and joins it with a pushed `ack` from the executing locus, acknowledging completed work. When the executor pushes its acknowledgement within `input_timeout_ms`, the gate emits an `event` representing the completion fact. If the executor fails or does not push its acknowledgement before `input_timeout_ms` elapses, the gate emits a `notification` describing the failure or timeout instead, ensuring the flow never blocks on a dead executor.

## Parameters
- `window_ms`: the interval during which the gate actively awaits the pushed acknowledgement from the executing locus before considering the interaction stale.
- `input_timeout_ms`: mandatory bound on how long the gate waits for the executor's pushed completion acknowledgement; on expiry the gate emits `notification` instead of `event`, guaranteeing forward progress.
- `refractory_ms`: set to 0 since each command instance is tracked independently and completion recording has no cooldown between distinct commands.
- `auth_required`: false, as this gate performs an internal bookkeeping interaction with the executing locus rather than acting on behalf of an external actor.