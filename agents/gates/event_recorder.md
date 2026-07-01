---
name: event_recorder
kind: gate
input_slots:
  - name: incoming_event
    type: event
    required: true
  - name: token
    type: auth_token
    required: false
output_slots:
  - name: confirmation
    type: ack
window_ms: 5000
refractory_ms: 0
auth_required: false
medium: local
interaction: push
---

## Event Recorder

Accepts an event payload and durably persists it to the event store as a recorded fact. Fires whenever a valid event is received on the input slot. Emits an acknowledgement once the write operation has completed successfully. The persisted record is available for downstream gates or analytics to query independently.

## Parameters
- `window_ms`: Maximum time allowed for the write operation to complete before the gate times out and drops the event; set to 5000 ms to accommodate transient store latency.
- `auth_required`: Set to false by default; if the upstream flow requires authenticated writes, place a sentinel_auth gate upstream and supply an `auth_token` in the optional token slot.
- `refractory_ms`: Zero — the gate imposes no cooldown period, allowing consecutive events to be recorded without delay.