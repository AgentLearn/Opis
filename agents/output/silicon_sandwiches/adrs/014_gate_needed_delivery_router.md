# ADR-014: gate needed: delivery_router

## Context
The kata requires integration with ≥2 external traffic-aware mapping services to compute delivery directions and route orders to the correct shop. This gate must fan out to multiple external mapping loci and aggregate results into a routing_decision. No existing gate produces routing_decision.

## Options

### Option A
delivery_router gate: consumes order + location (destination), fans out to ≥2 mapping service loci via query, collects query_response from each within window_ms, picks best route, emits routing_decision. auth_required: false.

**Tradeoffs:** Window-based aggregation naturally handles the multi-provider fan-in. If one provider is slow, the window timeout determines fallback behavior. Clean and idiomatic Opis.

### Option B
Two separate single-provider router gates whose results are merged by a routing_aggregator gate.

**Tradeoffs:** More granular but adds gates and synapses for the same logical outcome. Over-engineered for the stated requirement.

## Decision

A Requires another gate: external circuit breakers, one for each provider. Blocks until first open