---
name: payment_processor
kind: gate
input_slots:
  - name: incoming_payment
    type: payment
    required: true
  - name: auth_token
    type: auth_token
    required: true
output_slots:
  - name: confirmed_payment
    type: payment_confirmed
  - name: failed_payment
    type: payment_failed
window_ms: 15000
refractory_ms: 2000
auth_required: true
medium: internet
status: specified
confidence: llm-estimate
---

## Payment Processor

Accepts a payment slot and an auth token, synchronously contacts the configured payment
provider, and emits exactly one outcome: `payment_confirmed` on success or `payment_failed`
on any failure or timeout. No downstream gate receives a signal until one outcome is emitted.

## Parameters
- `window_ms`: Maximum time the gate waits for the provider to respond before emitting `payment_failed` (default 15 s).
- `refractory_ms`: Minimum quiet period after an outcome before the gate re-arms, preventing duplicate charge attempts on rapid retries (default 2 s).
- `auth_required`: true — sentinel_auth must appear upstream to supply the auth_token slot.
- `medium`: internet — payment providers are always external systems.
