# ADR-015: gate needed: driver_dispatcher

## Context
The kata requires a driver to be dispatched and tracked in real time after a delivery order is confirmed. This gate must consume an accepted_order + routing_decision and emit a command to a driver locus, then receive tracking_update events. No existing gate handles dispatch or tracking_update.

## Options

### Option A
driver_dispatcher gate: consumes accepted_order + routing_decision, emits command (dispatch_command) to Driver locus. A separate tracking_relay gate (or locus) handles inbound tracking_update events and forwards them to the customer. auth_required: true.

**Tradeoffs:** Separates dispatch (one-shot) from tracking (continuous stream). Tracking is modeled as a separate event flow, not gated. Clean lifecycle boundaries.

### Option B
driver_dispatcher gate handles both dispatch and tracking within one gate using a long window.

**Tradeoffs:** A single gate with a long window to await tracking updates is anti-pattern in Opis — gates are meant to fire once per window. Tracking should be modeled as repeated events.

### Option C
driver_dispatcher gate handles both dispatch and tracking within one gate using a long window. Vehicle emits possitions.

**Tradeoffs:** requires logic for handling lost connections with driver and reordering if driver ooff the shift

## Decision

C