---
name: driver_dispatcher
kind: gate
input_slots:
  - name: accepted_order
    type: accepted_order
    required: true
  - name: routing_decision
    type: routing_decision
    required: true
  - name: tracking_update
    type: tracking_update
    required: false
output_slots:
  - name: dispatch_command
    type: command
  - name: relay_tracking
    type: tracking_update
  - name: dispatch_failed
    type: event
window_ms: 3600000
refractory_ms: 5000
auth_required: true
medium: internet
interaction: push
---

## Driver Dispatcher

Consumes an accepted order and a routing decision to emit a dispatch command to the assigned agent locus. Once dispatched, the gate accepts a continuous stream of inbound position or status updates and relays them downstream. If the upstream agent connection is lost or the agent becomes unavailable within the active window, the gate emits a failure event to allow upstream recovery logic to act.

## Parameters
- `window_ms`: Duration the gate remains active after firing the initial dispatch command, allowing inbound tracking updates to be relayed for the lifetime of the active assignment (default: 3 600 000 ms = 1 hour).
- `refractory_ms`: Minimum interval between successive relay emissions for inbound position updates, preventing downstream flood from high-frequency position sources.
- `auth_required`: All dispatch commands and tracking relay paths require a verified auth token upstream; an unauthenticated actor cannot trigger dispatch or receive relayed position data.
- `tracking_update` (input): Optional and repeating within the window; each arriving update is re-emitted on `relay_tracking`. Absence of updates within a configurable dead-band triggers `dispatch_failed`.
- `dispatch_failed`: Emitted when the agent locus does not acknowledge the dispatch command within the window, or when tracking updates cease unexpectedly, enabling upstream rerouting or reassignment logic.