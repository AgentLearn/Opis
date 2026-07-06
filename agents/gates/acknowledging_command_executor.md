---
name: acknowledging_command_executor
version: 1
kind: gate
input_slots:
  - name: command
    type: command
    required: true
  - name: auth_token
    type: auth_token
    required: false
output_slots:
  - name: ack
    type: ack
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

## Acknowledging Command Executor

This gate receives a dispatched `command`, performs the execution against its attached effector, and emits an `ack` once execution completes. Ack semantics are at-completion: arrival of `ack` means the effector finished executing the command, not merely that the command was received. On a successful outcome the gate additionally emits an `event` recording the durable result; on a failed outcome it emits a `notification` carrying the failure output instead. Exactly one of `event` or `notification` accompanies each `ack`.

When the attached effector is protected, the optional `auth_token` slot carries the credential forwarded with the execution; when the effector is unprotected the slot is simply left unwired.

## Parameters
- `window_ms`: the join window during which `command` (and `auth_token`, where wired) must arrive before execution proceeds.
- `input_timeout_ms`: bound on effector execution; on expiry the gate emits `ack` plus a `notification` describing the timeout, guaranteeing forward progress past a hung effector.
- `refractory_ms`: set to 0 — each command is an independent work item and no cooldown between executions is required.
- `auth_required`: false — the gate itself does not gate access; it forwards the optional credential to effectors that demand one.
