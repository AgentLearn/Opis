---
name: completion_finalizer
kind: gate
input_slots:
  - name: confirmed_payment
    type: payment_confirmed
    required: true
  - name: validated_order
    type: accepted_order
    required: true
output_slots:
  - name: completion_event
    type: event
  - name: actor_notification
    type: notification
window_ms: 5000
refractory_ms: 1000
auth_required: true
medium: local
interaction: push
---

## Completion Finalizer

Joins a confirmed payment with an accepted order using AND logic; both inputs must arrive within `window_ms` for the gate to fire. On successful join it emits a terminal completion event signalling that the processing pipeline has concluded, and a notification directed at the relevant actor. If either input is absent before the window expires the gate discards the partial state and waits for a new pairing.

## Parameters
- `window_ms`: Maximum time allowed between arrival of the first and second input slot before the partial join is discarded; prevents stale pairings from accumulating.
- `refractory_ms`: Minimum quiet period after firing during which the gate ignores further input, preventing duplicate completion events from near-simultaneous retries.
- `auth_required`: Both input slots carry sensitive financial and order data; an upstream `sentinel_auth` gate must have issued a valid `auth_token` before this gate will accept input.