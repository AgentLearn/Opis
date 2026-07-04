# Diff report v1: induced control-flow ontology vs. Opis vocabulary

Inputs:
- `induced_ontology_v1.json` — 43 control-flow patterns induced from the seed corpus.
- Opis vocabulary (verified against repo on 2026-07-04):
  - gate logic operators AND / OR / FIRST / THRESHOLD — confirmed in `agents/fa/prompts.py`.
  - gate kinds regulator / breaker / sentinel (+ plain) — confirmed in prompts.py; regulator
    and sentinel currently instantiated in `agents/gates/index.md`.
  - fields `recovery_ms`, `trips_on`, `input_timeout_ms`, `optional` — confirmed in prompts.py.

The finding is the mapping distribution, not the ontology itself. Of 43 patterns:
**9 map exactly, 26 partially, 8 have no Opis counterpart.**

## 1. Exact matches — Opis vocabulary is well-grounded in the literature

These nine confirm Opis's core join/routing vocabulary is not ad-hoc; each is a named,
40-year-old pattern:

| WCP | pattern | Opis |
|-----|---------|------|
| WCP1 | Sequence | synapse |
| WCP2 | Parallel Split | synapse fan-out |
| WCP3 | Synchronization (AND-join) | `logic: AND` |
| WCP4 | Exclusive Choice (XOR-split) | outcome-based routing |
| WCP5 | Simple Merge (XOR-join) | `logic: OR` |
| WCP9 | Structured Discriminator | `logic: FIRST` |
| WCP30 | Structured Partial Join (N-of-M) | `logic: THRESHOLD` |
| WCP33 | Generalised AND-Join | `logic: AND` (general graph) |
| WCP10 | Arbitrary Cycles | feedback synapse |

Key structural confirmation: **FIRST is the N=1 specialization of THRESHOLD** (WCP9
`specializes` WCP30 in the ontology) — matching the workflow-patterns literature exactly
(the Discriminator is the 1-out-of-m Partial Join). Worth encoding in prompts.py as a
documented relationship rather than two independent operators.

## 2. Patterns Opis LACKS (gaps to consider)

### 2a. Cancellation as an explicit signal (WCP19/20/25/26/29/32/35)
The literature treats cancellation as a first-class control-flow act: Cancel Task,
Cancel Region, Cancelling Discriminator/Partial Join (winner cancels losers). Opis has
only the **breaker** (self-tripping, self-recovering) — which is a *reactive* suppressor,
not an *actively propagated* cancel. **Gap: no "winner cancels the losing branches" or
"cancel this downstream region" primitive.** This is the single most systematic missing
family — 7 patterns touch it. Candidate: a `cancels:` edge or a cancellation outcome that
actively withdraws named downstream gates.

### 2b. Synchronizing Merge with run-determined arrival count (WCP6/7/37/38)
Opis `AND` expects a statically-declared input bundle. Multi-Choice + Structured
Synchronizing Merge waits for *exactly the branches a prior split activated* — a count
known only at runtime. Opis cannot express "wait for however many of these got
activated." **Gap: dynamic/conditional AND-join.** WCP38 (cyclic synchronizing merge) is
the acknowledged hard case and maps onto the proof.py fixed point over cyclic flows —
worth noting as a known frontier, not a quick add.

### 2c. Dynamic multiple instances (WCP14/15/36)
Data-determined and dynamic instance counts (one instance per line item, count unknown
until done). Opis flows are statically typed; this correctly lives in the **CA payload/
body layer**, not the flow graph. **Not a gate-logic gap — a deliberate layer boundary.**
Documenting it as out-of-scope is the right outcome.

### 2d. Serialization / mutual exclusion (WCP17/39/40)
Interleaved routing, critical section: "these run one-at-a-time, order free." Opis's
**regulator** partially covers critical-section (guarding a shared downstream) but there
is no partial-order / interleaving primitive. **Gap: mutual-exclusion over a set of gates.**
Lower priority — rare in the katas so far.

### 2e. Persistent (buffered) trigger (WCP24)
Transient trigger maps to Opis's fire-and-forget event + `input_timeout_ms` window.
Persistent trigger (retain the signal until ready) has **no gate-logic primitive** — it
lives inside gate internals (a queue) today. Candidate: a `buffered` input flag paralleling
`optional`.

## 3. Opis-ORIGINAL constructs (no WCP counterpart) — candidate contributions

The literature is **untimed** (Petri-net token semantics). Everything time- or
probability-valued in Opis is absent from the 43 patterns. Confirmed originals:

- **refractory period (`recovery_ms`)** — time-gated suppression after firing. WCP's
  Blocking Discriminator/Partial Join express cross-case blocking *structurally* (block
  until reset) but never with a **timer**. Opis's timed refractory is genuinely new.
- **input window (`input_timeout_ms` as a budget)** — temporal scoping of a join. WCP
  joins wait indefinitely; no notion of "give up after t."
- **probabilistic outcomes** — gates emit outcomes with probabilities for twin sampling.
  No WCP analog whatsoever.
- **latency budgets (p50/p95 timing contracts)** — WCP has no timing perspective.
- **breaker as a self-recovering kind (`trips_on`/`recovery_ms`)** — WCP has Cancel
  patterns (external withdrawal) but not a self-tripping, timer-recovering circuit breaker.

**Interpretation:** Opis's join *logic* is a faithful, slightly-reduced subset of the
control-flow patterns (it collapses the 6 discriminator/partial-join variants into
FIRST/THRESHOLD by dropping the blocking/cancelling axes). Opis's genuine novelty is
orthogonal to the branching taxonomy: it is the **timing and probability layer** the
workflow-patterns literature deliberately never modeled. That is a clean, defensible
statement of what Opis adds.

## 4. Recommended actions (for Zarko to decide via ADR, not auto-applied)

1. Document FIRST = THRESHOLD(n=1) in prompts.py (cheap, purely descriptive).
2. Consider a cancellation primitive (2a) — the biggest and most principled gap; touches
   7 patterns and complements the breaker rather than duplicating it.
3. Record dynamic-MI (2c) explicitly as a CA-layer boundary in OpisDescription — turns a
   "gap" into a stated design decision.
4. Keep refractory / window / probabilistic outcomes / latency framed as Opis's core
   contribution in the docs; they are what the 43-pattern canon cannot say.
5. Defer synchronizing-merge (2b) and serialization (2d) — real but rare in current katas.

## 5. Method note (first-principle)

This was a hand-run: the corpus was hand-curated and the induction produced by one pass
over it. Per the Opis first principle the deliverable is the *recipe* — `induction_prompt.md`
is the golden prompt an agent (FA taxonomy stage 2) must reproduce, with the same
context-definition schema and a mechanical validator over the induced JSON-LD (every
`inCategory`/`mapsToOpis` id must resolve; every pattern must carry a mappingStrength).
The validation already ran: 43/43 patterns, 0 dangling refs.
