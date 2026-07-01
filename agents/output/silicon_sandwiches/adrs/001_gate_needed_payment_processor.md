# ADR-001: gate needed: payment_processor

## Context
Silicon Sandwiches requires payment to be confirmed before any order reaches the kitchen. A gate is needed that accepts a payment slot, contacts a payment provider, and emits either payment_confirmed or payment_failed. No existing gate covers this.

## Options

### Option A
Synchronous payment_processor gate: blocks until the payment provider responds, emits payment_confirmed or payment_failed inline.

**Tradeoffs:** Simple wiring, easy rollback on failure; increases latency for the customer-facing checkout path; payment provider outages stall the gate.

### Option B
Async payment_processor gate: fires a command to the provider and awaits a webhook/callback event before emitting the outcome.

**Tradeoffs:** Decouples latency from provider SLA; requires a callback locus and correlation ID tracking; more complex wiring.

## Decision

Option A