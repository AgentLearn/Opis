# Domain→SA mapping: encore_tickets (Phase-1, 3rd kata) + cross-kata synthesis

Third Phase-1 mapping, against 5-axis `sa_taxonomy_v1.json`, with the granularity
principle applied. encore is the first kata to stress **inventory consistency**
("never oversold") and **cancellation/refund with multi-domain effects** — so it tests the
term axis and the mutual-exclusion gap that silicon/ripple didn't reach.

## The mapping

| # | kata behaviour | term | movement tmpl | compute tmpl | logic | kind | resolves? |
|---|----------------|------|---------------|--------------|-------|------|-----------|
| 1 | Reserve seats via app/web | reservation, seat | Gatekeeper (intake/auth) | — | — | sentinel | clean |
| 2 | Payment confirmed before reservation finalized | payment_confirmed, reservation | Aggregator (join) | — | **AND** | plain | clean |
| 3 | Seat inventory never oversold; concurrent reservations resolved vs capacity | inventory_update (entity) | — | **Aggregate (invariant: capacity≥0) + Combine (decrement)** | — | regulator (Critical Section) | **friction: mutual exclusion (gap)** |
| 4 | On payment+reservation, issue digital ticket | ticket (value object) | — | **ParDo** (generate ticket) | **AND** | plain | clean |
| 5 | Organizers update listing/pricing/capacity independently | menu_update; inventory_update | Content Filter (scoped write) | — | — | protected by sentinel | clean (SPLIT — capacity ≠ listing) |
| 6 | Cancel + refund before event start; release seat to inventory | cancel, refund, inventory_update | — | ParDo (refund calc) + Combine (release) | — | plain | **friction: cancellation (Phase 3)** |
| 7 | Loyalty points, rewards at checkout | reward | — | **Combine+Aggregate** (per-customer) | — | plain | clean |

**5 of 7 resolve cleanly.** The two frictions are the two known Phase-3 gaps — cancellation
(#6, third kata confirming ADR-X001) and mutual exclusion (#3).

## NEW finding: inventory = DDD Aggregate as an INVARIANT, not just accumulation
"Seat inventory must never be oversold" is precisely the DDD **Aggregate** pattern's reason
to exist: a transactional consistency boundary enforcing an invariant (remaining_capacity ≥
0). This is a *different* use of the computation/state axis than ripple's counting:
- ripple #6/#8: Aggregate for **accumulation** (count events per entity).
- encore #3: Aggregate for **invariant enforcement** (a constraint that must never break).

So the `template_computation` "stateful reducer" node has two distinct sub-uses —
*accumulate* and *enforce-invariant*. Worth splitting in the taxonomy (candidate v2 edit).

And the concurrency clause ("concurrent reservations safely resolved") = WCP39 **Critical
Section** = the **mutual-exclusion gap** the control-flow diff flagged (§2d) but no earlier
kata exercised. encore is the kata that makes it real: the check-and-decrement of capacity
must be **atomic** across concurrent reservations. Opis has no mutual-exclusion primitive;
`regulator` only partially covers it (guards a shared downstream, but doesn't serialize).

**The granularity principle and the atomicity requirement agree here:** the capacity *check*
and the *decrement* are mutually dependent and must co-occur → UNIFY into one
`inventory_guard` gate — and that unification is *also* what makes the operation atomic
(a Critical Section). The cohesion rule and the concurrency correctness requirement point at
the same boundary. Good corroboration that the granularity principle tracks something real.

## Term axis — first real test, passes
encore forces the DDD Value-Object vs. Entity distinction from the term axis:
- **inventory** = an **entity** with identity (per-event capacity) and an invariant → the
  aggregate root of the inventory_guard.
- **ticket** = a **value object** (computed, immutable, identity-less) → output of a ParDo.
- **reservation** = an entity (identity, lifecycle: requested→finalized→cancelled).
The distinction cleanly predicts which gates are stateful (own an entity) vs. stateless
(emit value objects). The term axis is useful, not decorative.

## Granularity calls (encore)
- **#3 UNIFY** — capacity check + decrement → one `inventory_guard` (mutual dependence +
  atomicity both demand it).
- **#5 SPLIT** — organizer updates: listing/pricing are catalogue writes, but **capacity**
  changes must respect the never-oversold invariant, so capacity must route through the
  inventory aggregate (#3), not a plain catalogue writer. Different axis-role (compute/state
  vs. movement) → split. Driven by the invariant, a clean example.
- **#6 SPLIT** — cancel detection is one gate, but its effects (refund = payment domain,
  seat release = inventory domain) are independently useful and cross domains → emit
  compensation events consumed by a refund gate and the inventory_guard. Matches ADR-X001
  Option A (compensation-as-term), which encore's earlier flow_v2 already hand-built.

---

## Cross-kata synthesis (silicon + ripple + encore)

### Recurring templates = the genuinely reusable library (breadth payoff)
Three behaviours appear in ALL or most katas — by the granularity principle
(independent usefulness across katas), these are the templates that earn a library slot:
- **payment-precondition join** (AND on payment_confirmed) — silicon, ripple, encore. Every
  kata. The strongest reuse signal.
- **loyalty accumulator** (Combine+Aggregate per customer) — silicon, encore.
- **scoped-owner write** (Content Filter + sentinel scope) — silicon (menu), encore (listing).
- **intake/auth** (Gatekeeper + sentinel) — all three.

### Confirmed gaps across katas (Phase-3 backlog, now evidence-backed)
- **Cancellation family** — ripple (×2), encore (×1, multi-effect). Not in silicon. 3 of the
  cancellation patterns (Cancel Task, Cancelling Discriminator, compensation) now have kata
  evidence. ADR-X001 is well-motivated.
- **Mutual exclusion / Critical Section** — encore #3 only, but it's a correctness
  requirement (oversell = real bug), not a nicety. Second-highest-priority gap.
- **Timeout-driven reassignment** — ripple #3 (FIRST + window + re-dispatch); needs the
  cancellation primitive to withdraw the timed-out assignment.

### Axis validation across 3 katas
- **logic** (workflow): AND, FIRST, THRESHOLD all exercised. Solid.
- **template_movement** (EIP): router, aggregator, scatter-gather, filter, wiretap,
  gatekeeper all hit. Solid.
- **template_computation** (Dataflow+DDD): ParDo, Combine, Aggregate(accumulate AND
  invariant), Domain Service all hit across katas. The axis added mid-Phase-1 is now the
  most-exercised addition — clearly warranted.
- **kind** (resilience): sentinel, regulator, breaker, plain all hit; breaker shown to be
  compositional (ripple).
- **term** (slot_types + DDD entity/value-object): validated by encore (entity vs. value
  object predicts statefulness).

### Candidate taxonomy v2 edits (from the 3 katas)
1. Split `stateful reducer` into **accumulate** vs. **enforce-invariant** (ripple vs. encore).
2. Record that **kind composes with computation+timing** (breaker `trips_on` = windowed
   reduction per entity) — richer contract shape.
3. Add a **mutual-exclusion / critical-section** construct (currently a gap, not a node).

## Next
1. Breadth is holding at 3 katas — either add a 4th deliberately *outside* commerce (the
   three so far are all order/payment domains; a non-commerce kata would test generality),
   or declare Phase-1 breadth sufficient and move to loading the graph.
2. Load `sa_taxonomy_v1.json` + all three mappings into Neo4j; gates become nodes, and the
   recurring-template / gap / split-unify analyses become queries.
3. Fold the v2 edits above into `sa_taxonomy_v1.json`.
