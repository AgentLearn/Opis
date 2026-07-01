# ADR-013: gate needed: pickup_estimator

## Context
The kata requires pickup time to be estimated based on current queue length at the chosen location. This needs a gate that takes a query (or event) plus location, queries queue state, and emits an estimate. No existing gate produces estimate.

## Options

### Option A
pickup_estimator gate: consumes accepted_order + location (or queue query_response), emits estimate (pickup_time_estimate). Queries internal queue service within the gate's window. auth_required: false (read-only, customer-facing).

**Tradeoffs:** Stateless from flow perspective; queue is an internal dependency. Simple to wire. Estimate is best-effort.

### Option B
pickup_estimator gate: consumes query + queue_snapshot (inventory_update used as queue signal), emits estimate. Reuses inventory_update slot type to represent queue depth.

**Tradeoffs:** Avoids a new slot type but semantically stretches inventory_update. Confusing to future maintainers.

## Decision

A