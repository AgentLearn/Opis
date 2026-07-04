---
name: scoped_catalogue_writer
kind: gate
input_slots:
  - name: menu_update
    type: menu_update
    required: true
  - name: auth_token
    type: auth_token
    required: true
  - name: ownership_record
    type: query_response
    required: true
output_slots:
  - name: write_committed
    type: event
  - name: scope_violation
    type: notification
  - name: ownership_query
    type: query
window_ms: 5000
refractory_ms: 0
auth_required: true
medium: lan
---

## Scoped Catalogue Writer

This gate applies a catalogue update only when the requesting actor's identity matches the current ownership record for the targeted partition. On receipt of a `menu_update` and `auth_token`, it emits a `query` to fetch the latest ownership record for the target partition, then compares the returned identity against the token. On match it commits the write and emits an `event`; on mismatch it emits a `notification` reporting the scope violation and discards the update.

## Parameters
- `window_ms`: maximum time allowed between issuing the ownership query and receiving the `query_response` before the write attempt is abandoned.
- `auth_required`: true — `auth_token` must be validated by an upstream sentinel_auth before reaching this gate.
- `refractory_ms`: set to 0 since each write is independently scope-checked against a fresh ownership lookup; no cooldown is needed between writes.