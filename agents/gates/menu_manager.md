---
name: menu_manager
kind: gate
input_slots:
  - name: menu_update_payload
    type: menu_update
    required: true
  - name: credential
    type: auth_token
    required: true
output_slots:
  - name: acknowledgement
    type: ack
  - name: catalogue_change
    type: inventory_update
window_ms: 5000
refractory_ms: 1000
auth_required: true
medium: lan
interaction: push
---

## Menu Manager

Accepts a catalogue change payload together with a scoped credential and applies the update to the product catalogue for the identified location. On successful application it emits an acknowledgement and propagates an inventory update downstream so that dependent gates reflecting current stock or pricing receive the revised state. The gate drops and does not emit on credential failure or malformed payload within the processing window.

## Parameters
- `window_ms`: Maximum time allowed to receive and apply the catalogue change before the gate drops the in-flight payload; set to 5000 ms to accommodate catalogue write latency.
- `refractory_ms`: Minimum quiet period after a successful write before the gate will accept another update for the same location, preventing rapid conflicting writes.
- `auth_required`: Set to `true`; a `sentinel_auth` gate must appear upstream in the flow to validate and scope the credential before this gate is reached.