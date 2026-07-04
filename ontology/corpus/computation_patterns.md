# Seed corpus: Computation & State Patterns (gate COMPUTATION-template axis)

Motivation: the silicon_sandwiches mapping (mapping_silicon_sandwiches_v1.md, frictions
C/D) showed the EIP template axis has no home for gates that COMPUTE a value or ACCUMULATE
per-entity state — the three coordination literatures cover moving/joining/guarding work,
not doing it. This adds a fourth template family for the "what a gate computes" behaviour
(Zarko, 2026-07-04: add a computation template axis).

Sources (authoritative):
- Akidau, Bradshaw, Chambers, Chernyak, et al., "The Dataflow Model: A Practical Approach
  to Balancing Correctness, Latency, and Cost in Massive-Scale, Unbounded, Out-of-Order
  Data Processing", PVLDB 8(12):1792-1803, 2015.
  https://www.vldb.org/pvldb/vol8/p1792-Akidau.pdf
  (and Akidau, Chernyak, Lax, "Streaming Systems", O'Reilly 2018.)
- Eric Evans, "Domain-Driven Design", Addison-Wesley 2004 — tactical patterns
  (Aggregate, Domain Service, Value Object, Entity). Fowler, martinfowler.com/bliki.

Role in the SA taxonomy: a second **template** family — the COMPUTATION templates —
complementing the EIP movement templates. Where EIP answers "how does the message get to
the right gate," these answer "what new value does the gate produce from its inputs."

Each entry: name | source | computation semantics | Opis gate relevance.

---

## Stateless computation (Dataflow transforms)

- **ParDo / Map (element-wise transform)** — apply a user function to each input element,
  producing zero or more outputs; the fundamental stateless compute primitive, works on
  bounded and unbounded data alike. Opis: a gate that **computes a new value** from its
  inputs without keeping state — `queue_based_estimator` (queue+location → estimate),
  implicit pricing (menu+order → price). This is the missing template for friction C.

- **Filter (predicate)** — a ParDo that emits an element only if a predicate holds. Opis:
  overlaps EIP Message Filter but framed as computation; `order_validator`'s validity test.

- **FlatMap / Split** — a ParDo emitting many outputs per input. Opis: computation-driven
  fan-out (vs. EIP Splitter which is structural). 

## Stateful computation (Dataflow grouping + windowing)

- **GroupByKey** — regroup key-value pairs so all values for a key are collected before
  reduction; requires knowing when a group is complete (→ windowing for unbounded input).
  Opis: per-entity collection prior to a reduce — the mechanism under a per-customer or
  per-zone accumulation.

- **Combine / Reduce (aggregation function)** — fold the values of a group into a single
  result (sum, count, max, custom monoid). Opis: the **stateful reducer** — the compute
  core of `reward_accumulator` (fold loyalty events → points). Missing template for
  friction D (the *computation* half).

- **Windowing** — bucket elements by event time (fixed, sliding, session windows) so an
  unbounded stream can be reduced per bucket. Opis: directly ties to the timing layer
  (`input_timeout_ms`, sliding windows). The Dataflow model is where windowed reduction is
  first-class — grounds Opis windows on the COMPUTATION side (resilience Timeout grounds
  them on the protection side; two independent groundings for the same Opis field).

- **What / Where / When / How** (the Dataflow model's four questions) — *what* is computed
  (transform/aggregate), *where* in event time (windowing), *when* results are emitted
  (triggers/watermarks), *how* refinements relate (accumulation mode). Opis: a checklist
  for specifying a computation gate's contract — especially "when does it emit" maps to
  gate logic + window, "how refinements relate" maps to whether a gate re-emits on updates.

## State ownership (DDD tactical)

- **Aggregate** — a cluster of entities/value-objects treated as one consistency unit with
  a single root; all state changes go through the root, preserving invariants
  transactionally. Opis: the **state-owning gate** — `reward_accumulator` owns per-customer
  loyalty state as an aggregate (the customer is the aggregate root, points the invariant).
  This is the *ownership/consistency* half of friction D (Combine is the *computation* half;
  Aggregate is *who owns the state*).

- **Domain Service** — domain logic that doesn't naturally belong to any single entity or
  value object; a stateless operation over multiple domain objects. Opis: a computation
  gate whose output isn't "owned" by one input term — routing/estimating that spans terms.
  Grounds computation gates that ParDo alone under-describes (the logic is domain, not
  generic map).

- **Value Object** — an immutable value defined only by its attributes (money, date,
  estimate, price), no identity. Opis: the **output term of a computation gate** — an
  `estimate`, a `price`, a `routing_decision` are value objects (computed, immutable,
  identity-less), as opposed to `order`/`customer` which are entities. Useful distinction
  for the TERM axis: some slot_types are entities (identity), others value objects
  (computed) — may inform how business terms map.

- **Entity** — an object with identity persisting over time (customer, order, driver).
  Opis: the identity-bearing terms; the natural aggregate roots for stateful gates.

---

## Cross-reference: computation pattern -> Opis gate (curator's mapping, to test)

| pattern | source | Opis gate / construct |
|---------|--------|-----------------------|
| ParDo / Map | Dataflow | compute gate (queue_based_estimator, pricing) — friction C home |
| Combine / Reduce | Dataflow | stateful reducer (reward_accumulator computation) — friction D (compute half) |
| Windowing | Dataflow | input_timeout_ms / sliding windows (compute-side grounding) |
| Aggregate | DDD | state-owning gate (reward_accumulator ownership) — friction D (state half) |
| Domain Service | DDD | cross-term computation gate |
| Value Object | DDD | computed output terms (estimate, price, routing_decision) |
| Entity | DDD | identity terms / aggregate roots (order, customer, driver) |

## Computation-axis observations (candidate findings, to confirm by induction)
- Friction C (compute) resolves to **ParDo/Map** (+ Domain Service when cross-term).
- Friction D (accumulate) is **two patterns, not one**: Dataflow **Combine** (the
  computation) + DDD **Aggregate** (the state ownership/consistency). A stateful gate
  should declare both — what it folds AND what entity owns the state.
- **Windowing gives Opis windows a second, independent grounding** (compute-side) beyond
  the resilience Timeout (protection-side). Two literatures grounding one Opis field is
  the same corroboration pattern seen elsewhere — strengthens the case that windows are a
  real primitive, not an Opis quirk.
- The **Value Object vs. Entity** distinction may sharpen the TERM axis: computed outputs
  (estimate/price) are value objects; identity terms (order/customer) are entities and are
  the aggregate roots for any stateful gate.
- Boundary check: the Dataflow "when" question (triggers/watermarks — emit early/late,
  handle out-of-order) is largely a **twin/timing** concern, not a static gate contract —
  keep triggers below the flow line unless a kata forces otherwise.
