# Domain→SA mapping: silicon_sandwiches (Phase-1 mapping exercise)

First run of the actual Phase-1 skill: resolve each business behaviour in a kata to the
SA-taxonomy 4-tuple **(term, logic, template, kind)** against `sa_taxonomy_v1.json`.
The taxonomy is the target; this exercise stress-tests it. Existing silicon gates are
referenced to check the mapping against what the FA agent actually produced.

## The mapping

| # | kata behaviour | term (data) | template (EIP) | logic | kind (resilience) | existing gate | resolves? |
|---|----------------|-------------|----------------|-------|-------------------|---------------|-----------|
| 1 | Auth from app/kiosk (implicit) | auth_request→auth_token | Gatekeeper | — | **sentinel** | auth_token | clean |
| 2 | Validate order | order→accepted/rejected_order | Content Filter + Message Filter | — | plain (Fail Fast) | order_validator | clean |
| 3 | Payment confirmed before kitchen | payment→payment_confirmed/failed | **(none — external processor)** | AND w/ order gate | plain w/ prob-outcome | payment_authorizer | **friction A + B** |
| 4 | Join order+payment → submit | [accepted_order, payment_confirmed]→command | **Aggregator** | **AND** | plain | (join in dispatcher) | clean |
| 5 | Pickup estimate from queue length | (queue,location)→estimate | **(none — computation)** | — | plain | queue_based_estimator | **friction C** |
| 6 | Routing via ≥2 mapping services | query→routing_decision | **Scatter-Gather** | **THRESHOLD n=2** | plain | routing_decision_aggregator | clean |
| 7 | Send order to correct location | (accepted_order,routing_decision)→command | **Content-Based Router** | — | plain | routed_command_dispatcher | clean |
| 8 | Dispatch + track driver (optional pickup) | command→tracking_update | Content-Based Router + **Wire Tap** | — (input `optional`) | plain | assignment_tracker | clean |
| 9 | Owners update their OWN menu/pricing | menu_update→event | Content Filter (scoped write) | — | protected by sentinel | scoped_catalogue_writer | clean |
| 10 | Loyalty points, rewards at checkout | event→reward | **(none — stateful accumulation)** | — | plain | reward_accumulator | **friction D** |

**7 of 10 behaviours resolve cleanly** against the assembled taxonomy — the mapping
mechanism works and the taxonomy's breadth holds. Three friction points, and they are the
Phase-1 payoff (the taxonomy is incomplete exactly where the exercise found).

## Friction A — payment kind is mis-grounded (confirms a known defect independently)
`payment_authorizer` is tagged **`kind: regulator`**. On the kind axis, regulator =
Throttling / Governor (rate-limiting to a safe envelope). Payment authorization is not
rate-limiting — it is an external call with a domain outcome. The taxonomy says its kind
should be **plain** (a processor), with the money-guarding role belonging to the sentinel
(auth) and a Fail-Fast validation, not a regulator. This independently reproduces the
"payment_authorizer kind:regulator WRONG KIND, amend later" note already in the project
log — the SA taxonomy catches it from first principles, which is a good validation of the
taxonomy itself.

## Friction B, C, D — the template axis has no home for two gate families
EIP is a **message-movement** vocabulary (route / filter / aggregate / split / enrich /
observe). Three silicon gates are not moving messages — they are **computing** or
**accumulating**, and neither EIP nor workflow-patterns nor resilience covers that:

- **Computation gates** (friction C: `queue_based_estimator`; also implicit pricing):
  take inputs and compute a *new value* (an estimate, a price, a score). The closest EIP
  pattern is Content Enricher, but that *augments from an external source* — it does not
  *compute*. There is no "calculator / transformer-by-computation" template in any of the
  three source ontologies.
- **Stateful-accumulation gates** (friction D: `reward_accumulator`): maintain long-lived
  per-entity state (points per customer) updated by a stream of events. EIP Aggregator is
  the nearest, but it correlates a *finite* set of messages to one output then resets — it
  is not unbounded per-entity state. This is closer to a **DDD Aggregate** or a
  stream-processing **stateful reducer** than to any messaging pattern.
- **Payment/external-call gates** (friction B): an external request-reply with a domain
  outcome. EIP has Service Activator / Request-Reply, but those describe *connection to*
  the messaging system, not a gate whose *purpose is the external effect*. Partial home.

## The Phase-1 finding
The three source ontologies give the SA taxonomy strong coverage of **control and
movement** (how gates join, branch, route, guard, throttle) but **no template-axis
vocabulary for computation, external effects, or stateful accumulation** — the "business
logic" a gate performs on payloads. This is a coherent gap: the sourced literatures are
all about *coordinating* work, not *doing* it. Candidate sources for a computation/state
template axis, to add in a later breadth pass:
- **Dataflow / stream-processing patterns** (map/filter/reduce/window; e.g. Akidau et al.
  "Streaming Systems", or the Dataflow model) — for computation and stateful reducers.
- **DDD tactical patterns** (Aggregate, Domain Service) — for per-entity state ownership.

Note this may partly be a *layer* question rather than a gap: computation could be
declared CA-layer (the gate's implementation computes; the flow only types its
inputs/outputs). Worth an explicit decision — is "what a gate computes" part of the SA
taxonomy, or is it below the flow line like payload content? That decision is the natural
next Phase-1 question, and it generalizes beyond silicon.

## RESOLUTION (2026-07-04): computation axis added
Zarko chose to add a computation template axis rather than push compute below the flow
line. `corpus/computation_patterns.md` + new `template_computation` axis in
`sa_taxonomy_v1.json` (Dataflow ParDo/Combine/window + DDD Aggregate/Domain-Service/
Value-Object). Frictions now resolve:
- **Friction C** (queue_based_estimator) → `compute / transform` (Dataflow ParDo + DDD
  Domain Service). Clean.
- **Friction D** (reward_accumulator) → `stateful reducer` = **two patterns**: Dataflow
  **Combine** (the fold) + DDD **Aggregate** (per-customer state ownership). A stateful
  gate declares both. Clean.
- Friction A (payment kind) stands — it's a kind-axis correction, not a template gap.

Bonus: **Dataflow Windowing gives Opis windows a second independent grounding** (compute
side) on top of resilience Timeout (protection side) — two literatures, one Opis field.
And the DDD **Value Object vs. Entity** distinction now sharpens the TERM axis: computed
outputs (estimate/price/routing_decision) are value objects; identity terms
(order/customer/driver) are entities and the aggregate roots for stateful gates.

Post-resolution: **9 of 10 behaviours resolve cleanly**; the one remaining item (payment
kind) is a defect in an existing gate, not a taxonomy gap.

## Next
1. Run the same mapping on a *second* kata (ripple_rides — dispatch/reassign/surge stresses
   the kind axis and the cancellation gap differently). Cross-kata breadth-validation.
2. Load `sa_taxonomy_v1.json` + this mapping into Neo4j so domain→SA becomes a traversal.
