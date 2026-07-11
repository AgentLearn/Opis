---
name: ack_completion_recorder
kind: gate
input_slots:
  - name: ack
    type: ack
    required: true
output_slots:
  - name: event
    type: event
  - name: notification
    type: notification
window_ms: 500
refractory_ms: 1000
auth_required: false
medium: local
---

## Ack Completion Recorder

Consumes a single acknowledgement signal that marks a command as executed and records its durable completion. On receiving an ack it emits an event capturing the completion fact and a notification surfacing the outcome to an interested actor. No coincidence with the originating command pulse is required — the ack payload itself carries the correlation needed to identify what was completed.

## Parameters
- `window_ms`: the interval within which an incoming ack is processed and turned into outputs; since only one input slot exists, this bounds internal processing latency rather than any cross-slot coincidence.
- `refractory_ms`: minimum interval between successive firings, preventing duplicate completion records from rapid repeat acks for the same or overlapping signals.
- `auth_required`: false — this gate only records a completion already vouched for upstream; it performs no authorisation of its own.