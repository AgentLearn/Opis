# ADR-003: gate needed: zone_regulator

## Context
The flow requires a gate that applies demand-based rate limiting to inbound orders per zone, and computes surge pricing adjustments. It must accept a routing_decision (containing zone + demand signal) and an order, and either pass the order through with a surge-adjusted routing_decision or emit a rejected_order when the zone rate limit is exceeded. No existing gate acts as a regulator on order flow conditioned on zone demand — delivery_router computes routing but does not throttle or price-adjust.

## Options

### Option A
Add zone_regulator gate (kind: regulator): inputs order + routing_decision, outputs accepted_order (with surge pricing applied) or rejected_order (rate limit exceeded). Maintains per-zone counters and demand thresholds.

**Tradeoffs:** Clean separation of surge/rate-limit logic from routing. Reusable for any zone-based throttling scenario. Adds one more hop in the critical path.

### Option B
Extend delivery_router to also output a surge-tagged routing_decision and add a rate_limit flag; let order_intake reject on that flag.

**Tradeoffs:** Fewer gates but delivery_router takes on surge pricing and throttling responsibility — violates single-responsibility. order_intake would need to interpret rate_limit signals, coupling two concerns.

## Decision

A
