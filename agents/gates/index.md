# Gates Index

Computing-level gate library. FA selects gates by matching domain archetypes to input slot types.

Every gate carries a lifecycle `status` and a `confidence` provenance tag in its
frontmatter. The current library is **seed stock**: contracts were proposed
one-shot during early kata runs and are unvalidated drafts, not authoritative
primitives. A contract is promoted only with evidence — grounding in real-life
architectures (`sourced`) or high-quality sandboxed twin runs (`twin-validated`).

Lifecycle: `draft` (ADR only) → `specified` (contract + proved internals) →
`simulated` (twin-validated timing) → `measured` (real CA implementation PDs).
Demotion is possible: evidence from any lower stage can invalidate the stage above.

| gate | kind | input slot types | output slot types | auth_required |
|------|------|-------------------|-------------------|---------------|
| payment_processor | gate | payment, auth_token | payment_confirmed, payment_failed | true |
| order_validator | gate | accepted_order, payment_confirmed, inventory_update, routing_decision | accepted_order, rejected_order | true |
| order_intake | gate | order, auth_token | accepted_order, rejected_order | true |
| producer_submitter | gate | accepted_order, routing_decision | command, ack | true |
| pickup_estimator | gate | accepted_order, location | estimate | false |
| delivery_router | gate | order, location | routing_decision | false |
| driver_dispatcher | gate | accepted_order, routing_decision, tracking_update | command, tracking_update, event | true |
| menu_manager | gate | menu_update, auth_token | ack, inventory_update | true |
| loyalty_processor | gate | payment_confirmed, auth_token, reward | reward, notification | true |
| sentinel_auth | sentinel | auth_request | auth_token | false |
| event_recorder | gate | event, auth_token | ack | false |
| repeat_event_throttle | regulator | event | command, ack | false |
| zone_regulator | regulator | order, routing_decision | accepted_order, rejected_order | false |
| completion_finalizer | gate | payment_confirmed, accepted_order | event, notification | true |
