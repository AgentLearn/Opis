# ADR-002: gate needed: order_validator

## Context
After payment is confirmed, the order must be validated (items available, location reachable, data complete) before kitchen submission. A gate is needed that requires both an order slot and a payment_confirmed slot within a time window and emits accepted_order or rejected_order. No existing gate covers this.

## Options

### Option A
Monolithic order_validator gate: performs item availability, price consistency, and location checks internally, emitting a single accepted_order or rejected_order.

**Tradeoffs:** Single point of truth for validation; couples inventory, pricing, and routing concerns into one gate; harder to extend per-franchise.

### Option B
Composed validator: a lightweight order_validator gate that aggregates results from separate inventory_check and pricing_check sub-gates before emitting its outcome.

**Tradeoffs:** More extensible and testable per concern; increases gate count and synapse complexity; window_ms must accommodate all sub-gate latencies.

## Decision

B