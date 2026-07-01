# ADR-004: gate needed: completion_finalizer

## Context
A gate is needed that accepts a confirmed payment and an accepted order, then emits a completion event. No existing gate covers this contract: order_validator requires inventory_update and routing_decision (irrelevant to finalization), driver_dispatcher requires routing_decision and tracking_update, and event_recorder only accepts an already-formed event. The system needs a primitive that joins payment confirmation with an accepted order to produce a terminal completion event.

## Options

### Option A
Add a completion_finalizer gate: inputs payment_confirmed + accepted_order, emits event (completed) and notification. AND logic, auth_required: true.

**Tradeoffs:** Clean separation of finalization from dispatch and recording. Requires a new gate in the index.

### Option B
Reuse order_validator by also supplying routing_decision and a synthetic inventory_update, forcing those inputs into every ride completion path.

**Tradeoffs:** Satisfies template contract structurally but pollutes the completion path with irrelevant slot types; semantically misleading and fragile.

## Decision

A
