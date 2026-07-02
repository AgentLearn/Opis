---
name: repeat_event_throttle
kind: regulator
input_slots:
  - name: incoming_event
    type: event
    required: true
output_slots:
  - name: threshold_command
    type: command
  - name: below_threshold_ack
    type: ack
window_ms: 300000
refractory_ms: 60000
auth_required: false
medium: local
status: draft
confidence: llm-estimate
---

## Repeat Event Throttle

Maintains a stateful counter keyed by actor identity and increments it on each received event within a rolling time window. When the counter meets or exceeds a configured threshold within `window_ms`, the gate emits a `command` on the `threshold_command` slot (e.g. suspend, cooldown, or any downstream action). While the count remains below the threshold, it emits an `ack` on `below_threshold_ack`. Counters are reset after the rolling window elapses or upon entry into a refractory period following a threshold breach.

## Parameters
- `window_ms`: Duration of the rolling observation window in milliseconds. Events older than this value do not contribute to the actor's counter.
- `refractory_ms`: Minimum quiet period after a threshold command is emitted before the gate will emit another threshold command for the same actor identity, preventing rapid-fire command floods.
- `auth_required`: Set to `false` because this gate operates on already-validated internal events; place `sentinel_auth` upstream if the event source is external.