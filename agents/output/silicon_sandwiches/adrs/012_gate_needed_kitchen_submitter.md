# ADR-012: gate needed: kitchen_submitter

## Context
The kata requires that once payment is confirmed and the order is validated, the order is sent to the correct shop kitchen. No existing gate accepts accepted_order and emits a command to a kitchen locus. This is a distinct side-effecting gate that must fire only after full validation.

## Options

### Option A
kitchen_submitter gate: consumes accepted_order + routing_decision, emits command (kitchen_order_command) to the target shop, emits ack back upstream. auth_required: true.

**Tradeoffs:** Explicit routing dependency ensures order goes to correct location. Clean separation of routing from submission.

### Option B
kitchen_submitter gate: consumes only accepted_order, derives location from embedded order payload, emits command.

**Tradeoffs:** Simpler wiring but location logic bleeds into the gate, duplicating routing concern. Harder to swap routing providers.

## Decision

Option A with change that *kitchen* is replaced by *producer*.  So kitchen type is producer.