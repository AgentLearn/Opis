# ADR-001: gate needed: event_recorder

## Context
The flow requires a gate that accepts an event (and optionally an auth_token) and persists it as a recorded fact, emitting an ack. No existing gate accepts an event as its primary input and writes it to a store — loyalty_processor handles payment_confirmed, not generic events. This gate is needed wherever the system must durably record a fact (e.g. a rating, a cancellation) that other gates or analytics may later query.

## Options

### Option A
Add event_recorder gate: inputs event + auth_token, outputs ack. Stateless write — simply persists the event payload to the event store and acknowledges.

**Tradeoffs:** Simple and reusable; no aggregation logic. Cannot detect patterns (e.g. repeated events from same actor). Requires a separate gate for pattern detection.

### Option B
Extend loyalty_processor to also accept raw events and emit ack alongside reward/notification.

**Tradeoffs:** Reduces gate count but violates single-responsibility; loyalty_processor becomes overloaded with unrelated concerns. Poor reusability.

## Decision

A
