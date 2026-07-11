---
name: assignment_tracker
version: 3
kind: gate
input_slots:
  - name: command
    type: command
    required: true
  - name: position
    type: location
    required: false
  - name: enrichment
    type: query_response
    required: false
output_slots:
  - name: tracking_update
    type: tracking_update
  - name: notification
    type: notification
window_ms: 300000
refractory_ms: 2000
auth_required: false
medium: internet
---

## Assignment Tracker

This gate consumes a dispatch command that has already been routed to it as a tracked outcome, unconditionally assigns a mobile agent, and begins streaming a sequence of tracking_update pulses reflecting gate-derived status. When a flow wires a push synapse from the mobile-agent locus into this gate's optional `position` input slot, each delivered position pulse yields a tracking_update carrying the real-time position fact alongside the gate-derived status. When a flow wires a synapse from an externally sourced fact stream into this gate's optional `enrichment` input slot, each delivered enrichment pulse likewise yields a tracking_update carrying the sourced facts alongside the gate-derived status. When either the `position` slot or the `enrichment` slot is left unwired, the gate degrades honestly to status-only tracking_update pulses on that dimension — it makes no promise of facts it cannot source. It also emits a notification to the requesting actor confirming that tracking has begun. The gate performs no branching of its own — it only ever runs the assign-and-stream path, since untracked outcomes never reach it.

## Parameters
- `window_ms`: bounds how long the gate keeps emitting tracking_update pulses for a given assignment before the stream is considered closed.
- `refractory_ms`: minimum spacing enforced between successive tracking_update pulses to avoid flooding downstream consumers, applying equally whether or not the `position` or `enrichment` slots are wired.
- `auth_required`: false — this gate only processes commands already authorized upstream by the dispatching flow; it performs no independent access control.