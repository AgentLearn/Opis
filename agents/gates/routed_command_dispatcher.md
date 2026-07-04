---
name: routed_command_dispatcher
kind: gate
input_slots:
  - name: accepted_order
    type: accepted_order
    required: true
  - name: routing_decision
    type: routing_decision
    required: true
  - name: location
    type: location
    required: false
output_slots:
  - name: command
    type: command
  - name: no_ack_notification
    type: notification
window_ms: 5000
refractory_ms: 0
auth_required: false
medium: local
---

## Routed Command Dispatcher

This gate joins an accepted order with its routing decision (and optional target location) and emits a command addressed to the selected locus. It expects an acknowledgement in return; if no ack arrives within the timeout window, it either re-emits the command or raises a notification to surface the failure. Use this gate when downstream execution of the command must not be silently missed.

## Parameters
- `window_ms`: the join window during which the accepted_order and routing_decision (and location, if present) must all arrive before the dispatch computation proceeds.
- `refractory_ms`: set to 0 since each join represents a distinct work item and no cooldown between dispatches is required.
- `auth_required`: false — this gate operates on already-validated internal work items and does not itself gate access.
- `input_timeout_ms`: the ack-wait period after emitting a command; if no ack is received within this period the gate re-emits the command or emits a no_ack_notification instead.