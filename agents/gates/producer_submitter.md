---
name: producer_submitter
kind: gate
input_slots:
  - name: validated_order
    type: accepted_order
    required: true
  - name: routing
    type: routing_decision
    required: true
output_slots:
  - name: producer_command
    type: command
  - name: submission_ack
    type: ack
window_ms: 5000
refractory_ms: 500
auth_required: true
medium: lan
status: draft
confidence: llm-estimate
---

## Producer Submitter

Consumes a validated order and a pre-computed routing decision, then emits a command directed at the target producer locus. Fires only when both input slots are satisfied within the window. An acknowledgement is emitted upstream once the command has been dispatched.

## Parameters
- `window_ms`: Maximum time (ms) to wait for both input slots to be populated before the gate discards the partial state and resets.
- `refractory_ms`: Minimum quiet period after firing before the gate will accept a new input pair, preventing duplicate submissions.
- `auth_required`: Both input slots must be preceded by a `sentinel_auth` gate upstream; the gate will not process unauthenticated inputs.