---
name: routed_command_dispatcher
version: 2
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
window_ms: 5000
refractory_ms: 0
auth_required: false
medium: local
---

## Routed Command Dispatcher

This gate joins an accepted order with its routing decision (and optional target location) and emits a command addressed to the selected locus. Use this gate when downstream execution of the command must not be silently missed; pair the dispatch target with an instance of the recorder template to obtain non-loss guarantees at the flow level.

## Parameters
- `window_ms`: the join window during which the accepted_order and routing_decision (and location, if present) must all arrive before the dispatch computation proceeds.
- `refractory_ms`: set to 0 since each join represents a distinct work item and no cooldown between dispatches is required.
- `auth_required`: false — this gate operates on already-validated internal work items and does not itself gate access.