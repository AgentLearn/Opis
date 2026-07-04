---
name: payment_authorizer
kind: regulator
input_slots:
  - name: payment
    type: payment
    required: true
  - name: reward
    type: reward
    required: false
output_slots:
  - name: payment_confirmed
    type: payment_confirmed
  - name: payment_failed
    type: payment_failed
window_ms: 5000
refractory_ms: 30000
auth_required: false
medium: internet
---

## Payment Authorizer

This gate consumes a payment request, optionally adjusted by a reward credit that reduces the transaction amount, and submits it to an external processor for a single-phase authorization. It emits `payment_confirmed` on success or `payment_failed` on decline, and downstream gates treat `payment_confirmed` as a hard precondition for fulfilment. Because it acts as a regulator, repeated processor failures trip it into a cooldown state so a struggling processor is not hammered with retries.

## Parameters
- `window_ms`: maximum time to wait for the processor to respond before treating the attempt as failed.
- `refractory_ms`: cooldown period after a `payment_failed` outcome during which further authorization attempts are suppressed, allowing the processor to recover.
- `auth_required`: false — this gate authorizes a transaction against an external processor and does not itself require an authenticated actor upstream.