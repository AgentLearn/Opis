---
name: order_validator
kind: gate
input_slots:
  - name: order
    type: order
    required: true
output_slots:
  - name: accepted_order
    type: accepted_order
  - name: rejected_order
    type: rejected_order
window_ms: 200
refractory_ms: 0
auth_required: false
medium: local
---

## Order Validator

Validates an incoming order against structural and business rules before any payment is attempted. Fires as soon as an order slot arrives, evaluates it within the configured window, and emits either an accepted_order or a rejected_order — never both. Downstream gates use this outcome to decide whether to proceed toward payment collection, ensuring money is never taken on an order that has not first been deemed likely valid.

## Parameters
- `window_ms`: maximum time allotted to complete validation checks before the gate must resolve to accepted or rejected.
- `refractory_ms`: set to 0 since each order is validated independently with no cooldown needed between evaluations.
- `auth_required`: false — validation is a structural/business-rule check on the order content itself and does not require actor authentication upstream.