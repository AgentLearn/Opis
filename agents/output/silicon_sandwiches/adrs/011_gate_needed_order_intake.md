# ADR-011: gate needed: order_intake

## Context
The kata requires an entry point that captures a customer's sandwich order from mobile app or kiosk, associates it with a location, and emits an order for downstream validation. No existing gate accepts a raw order and produces an accepted_order for the validator pipeline. The order_validator requires accepted_order as input, implying a prior gate must promote a raw order to that type.

## Options

### Option A
order_intake gate: consumes order + auth_token, performs syntactic well-formedness check (items exist, quantities valid), emits accepted_order on success or rejected_order on failure.

**Tradeoffs:** Keeps validation stages separate (intake = structural, order_validator = business rules + payment + stock). Clear single-responsibility. Adds one hop.

### Option B
Expand order_validator to also accept raw order as an alternative input, skipping the intake gate.

**Tradeoffs:** Fewer gates but order_validator becomes overloaded. Harder to reason about the accepted_order precondition it already requires. Violates existing gate contract.

## Decision

A