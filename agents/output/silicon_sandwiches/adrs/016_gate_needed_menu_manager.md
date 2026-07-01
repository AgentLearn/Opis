# ADR-016: gate needed: menu_manager

## Context
Franchise owners must be able to update their own menu and pricing independently. This requires a gate that accepts a menu_update command from an authenticated franchise owner and applies it to the catalogue for that location. No existing gate accepts menu_update.

## Options

### Option A
menu_manager gate: consumes menu_update + auth_token (franchise owner scope), emits ack on success, emits inventory_update to propagate catalogue changes downstream. auth_required: true.

**Tradeoffs:** Auth scoping at the gate level ensures owners can only update their own location. inventory_update reuse connects menu changes to order validation stock checks.

### Option B
menu_manager gate: consumes menu_update + auth_token, emits only ack. Inventory sync handled out-of-band.

**Tradeoffs:** Simpler gate but breaks the flow continuity — order_validator won't see updated inventory without an explicit inventory_update synapse.

## Decision

A