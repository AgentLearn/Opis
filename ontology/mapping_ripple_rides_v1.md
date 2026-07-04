# Domain→SA mapping: ripple_rides (Phase-1 cross-kata validation)

Second Phase-1 mapping. ripple_rides has no current gates (workspace mid blank-slate
reset), so this is a clean domain→SA mapping from the kata alone, against the 5-axis
`sa_taxonomy_v1.json`. Two goals: (1) cross-kata breadth-validation — does the taxonomy
(esp. the new computation axis) hold on a second domain; (2) apply the gate-granularity
principle (unify inseparable / split independently-useful; established practice or a second
pass may override).

## The mapping

| # | kata behaviour | term | movement tmpl | compute tmpl | logic | kind | resolves? |
|---|----------------|------|---------------|--------------|-------|------|-----------|
| 1 | Rider requests ride (pickup/dest) via app | ride_request, location | Gatekeeper (intake/auth) | — | — | sentinel | clean |
| 2 | Match request vs several nearby drivers at once, weighing proximity+availability | routing_decision | Scatter-Gather (query N drivers) | **Domain Service** (rank candidates) | THRESHOLD/AND on responses | plain | clean (split candidate) |
| 3 | No accept in short window → reassign to next best | command (assignment) | Content-Based Router (re-dispatch) | — | **FIRST + window** | plain | **friction: timeout-reassign** |
| 4 | High demand → surge pricing + rate-limit new requests per zone | price, ride_request | — | **ParDo** (surge price) | — | **regulator** (per-zone) | clean (SPLIT — see below) |
| 5 | Payment confirmed before ride marked complete | payment_confirmed, ride | Aggregator (join) | — | **AND** | plain | clean |
| 6 | Driver repeatedly fails to accept in window → suspend new assignments | assignment | — | **Combine+Aggregate** (count fails/driver) | — | **breaker** (per-driver) | clean (compositional) |
| 7 | On completion, record rating for rider AND driver | event→rating | Wire Tap / recorder (fan-out ×2) | — | — | plain | clean (UNIFY) |
| 8 | Rider cancels before driver arrives; repeated late cancels → cooldown | cancel; ride_request | — | Combine+Aggregate (count cancels/rider) | — | **breaker** (per-rider cooldown) | **friction: cancellation (Phase 3)** + clean cooldown |

**6 of 8 resolve cleanly**; the two frictions (timeout-reassign #3, active cancel #8) are
the **cancellation family** already parked as Phase 3 (ADR-X001) — ripple confirms it is
real and recurrent, not a silicon artifact.

## Cross-kata validation of the computation axis (the reason to trust adding it)
The computation axis, added for silicon's two gates, is exercised **heavily** in ripple —
independently of silicon:
- **ParDo** — surge pricing (#4: demand → price multiplier).
- **Domain Service** — driver matching/ranking (#2: score candidates across terms).
- **Combine + Aggregate** — per-driver failure counting (#6) and per-rider cancellation
  counting (#8).
Three of ripple's eight behaviours need the computation axis. It was not silicon-specific;
the axis earns its place. Cross-kata breadth-validation is working as intended.

## NEW finding: the axes COMPOSE — a per-entity breaker is kind × computation × timing
Behaviours #6 and #8 are both "count an entity's failures within a window, and when the
count crosses a threshold, trip." Decomposed against the taxonomy:
- **kind = breaker** (trips_on threshold, recovery_ms = suspension/cooldown period),
- **compute = Combine+Aggregate** (the trip condition is a *stateful reduction per entity*),
- **timing = window** (counted "within a short window").

So a breaker's `trips_on` is not a scalar predicate — it is often itself a windowed
stateful reduction keyed by an entity (driver, rider). **The kind axis composes with the
computation and timing axes.** This is a genuine modeling insight the taxonomy made
visible: gate `kind` and gate `template_computation` are not orthogonal for stability
gates — the resilience role is *driven by* an accumulation. Candidate contract shape:
`kind: breaker, trips_on: {reduce: count, over: window, per: driver, threshold: n}`.

## Gate-granularity principle applied (split / unify calls)
- **#4 SPLIT — surge pricing vs. zone rate-limiting.** Same trigger (high demand) but
  independently useful: you can rate-limit a zone without surging, and surge-price without
  rate-limiting. → two gates: a `surge_pricer` (compute/ParDo) and a `zone_rate_limiter`
  (regulator). Clean textbook case of the split rule.
- **#6 UNIFY — count-failures + suspend.** The per-driver failure count is useless except
  to drive the suspension decision, and the suspension needs the count; they always
  co-occur with mutual dependence. → one `driver_reliability_breaker` gate (counts and
  trips). Clean case of the unify rule.
- **#7 UNIFY — rider rating + driver rating.** Both emitted from the same completion event,
  always together; neither is a standalone gate. → one `completion_rating_recorder` with a
  fan-out (two outputs), not two gates.
- **#8 SPLIT — cancel vs. cooldown.** Cancelling a ride is useful on its own (most cancels
  are one-offs); the cooldown only engages on *repeated* late cancels. Different lifetimes,
  independently useful. → a cancellation handler (Phase 3 primitive) + a `rider_cooldown_breaker`.
- **#2 SPLIT candidate, but established practice may override.** Matching = gather driver
  availability (Scatter-Gather) + rank candidates (Domain Service). The gather is reusable
  (ETA, surge could use live driver states) → argues split. BUT EIP **Scatter-Gather is one
  established pattern** that includes the aggregate step. Per Zarko's override clause: keep
  as one gate for now (established practice wins), revisit in a second pass if the gather is
  actually reused by another gate.

The granularity principle interacts cleanly with the taxonomy: the **split** calls are
usually "two different axes bundled" (compute + kind in #4) and the **unify** calls are
"one axis, one purpose, mutually dependent" (#6, #7). Useful heuristic: a gate spanning two
axis-roles that are separately useful is a split smell; a gate whose parts share one
axis-role and co-depend is correctly unified.

## Findings summary (ripple)
1. Computation axis validated cross-kata (3/8 behaviours) — not silicon-specific.
2. **Axes compose:** per-entity breakers = kind × computation(Combine+Aggregate) × window.
   Suggests a richer `trips_on` contract shape. Worth an ADR later (Phase 3).
3. Cancellation family recurs (#3, #8) — reinforces ADR-X001, still Phase 3.
4. Granularity principle gives clean split (#4, #8) and unify (#6, #7) calls; #2 deferred
   to established practice per the override clause.

## Next
1. (Breadth continues) map a 3rd kata (encore_tickets — cancellation/refund heavy; will
   pile more evidence on the cancellation gap and test the term axis with inventory).
2. Load `sa_taxonomy_v1.json` + both mappings into Neo4j; a gate then becomes a node with
   edges to its axis values, and split/unify candidates become graph queries.
3. (Phase 3 backlog) cancellation primitive (ADR-X001); composite `trips_on` shape.
