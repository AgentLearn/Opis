---
name: loyalty_processor
kind: gate
input_slots:
  - name: payment_confirmed
    type: payment_confirmed
    required: true
  - name: auth_token
    type: auth_token
    required: true
  - name: reward
    type: reward
    required: false
output_slots:
  - name: reward
    type: reward
  - name: customer_notification
    type: notification
window_ms: 5000
refractory_ms: 1000
auth_required: true
medium: local
status: draft
confidence: llm-estimate
---

## Loyalty Processor

Consumes a confirmed payment along with a valid auth token to compute and emit a reward representing accrued credits or points. When an inbound reward slot is also populated, the gate applies the existing reward balance as a discount signal before emitting the updated reward state. A notification slot is emitted to inform the authenticated actor of their current reward status after each processing cycle.

## Parameters
- `window_ms`: Maximum time allowed to accumulate all required inputs before the gate expires the cycle without firing; prevents stale payment confirmations from triggering reward accrual out of order.
- `refractory_ms`: Minimum quiet period after firing before the gate can fire again for the same actor, guarding against duplicate accrual from retried upstream events.
- `auth_required`: Set to true; a `sentinel_auth` gate must appear upstream to supply the `auth_token` slot, ensuring reward mutations are tied to a verified actor identity.
- `reward` (input): Optional; when present, signals that an existing reward balance should be consumed or applied within this processing cycle rather than accruing a new balance from scratch.