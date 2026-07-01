# ADR-017: gate needed: loyalty_processor

## Context
The kata requires loyalty points to be tracked per customer and rewards applied at checkout. This needs a gate that can both accrue points from a completed order and emit a reward (discount/credit) that feeds back into the checkout flow. No existing gate handles reward slot type.

## Options

### Option A
loyalty_processor gate: consumes payment_confirmed + auth_token, emits reward (points accrual event) and optionally a notification to the customer. A second gate instance or the same gate at checkout consumes order + reward to apply discount before payment. auth_required: true.

**Tradeoffs:** Two-phase model (accrue after payment, apply before next payment) correctly models loyalty lifecycle. Reward slot type is used canonically.

### Option B
loyalty_processor gate: consumes order + auth_token, emits reward inline during checkout, then emits updated order with discount applied.

**Tradeoffs:** Single gate but mixes pre-payment discount with post-payment accrual. Reward application and accrual have different timing requirements — conflating them creates ordering hazards.

## Decision

A