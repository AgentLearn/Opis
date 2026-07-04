# ADR-X001: cancellation as a gate-vocabulary primitive

Cross-cutting (schema-level, not kata-scoped). Motivated by `ontology/diff_report_v1.md`
§2a: of the 43 control-flow patterns, seven form a cancellation family
(WCP19 Cancel Task, WCP20 Cancel Case, WCP25 Cancel Region, WCP26 Cancel MI,
WCP29 Cancelling Discriminator, WCP32 Cancelling Partial Join, WCP35 Cancelling
Partial Join for MI) with **no Opis counterpart**. It is the single largest and most
systematic gap the induction found.

## Context

Opis's only cancellation-adjacent primitive is the **breaker**: it trips on its own
`trips_on` condition and self-recovers after `recovery_ms`. That is *reactive
self-suppression* — a gate silencing itself. The literature's cancellation family is
*active propagation*: one gate's outcome withdraws in-flight work at OTHER, named
downstream gates (Cancel Task/Region), or a first/threshold winner actively cancels the
losing branches (Cancelling Discriminator/Partial Join).

This gap is real in the current katas, and Opis has already been paying for its absence:

- **ripple_rides:** "Riders can cancel a requested ride before a driver arrives" and
  "if no matched driver accepts within a short window, reassign to the next best driver."
  Both require withdrawing an outstanding dispatch — a cancel of in-flight work.
- **encore_tickets:** "Customers can cancel a reservation... releasing the seat back to
  available inventory." Handled in `flow_v2` by hand-building a *separate*
  CancellationIntake → CancellationRouter path — i.e. cancellation was modeled as an
  ordinary forward pulse because there was no primitive for it.

The central tension is not domain modeling — it is the **proof layer**. `proof.py`'s
requirement coverage is a **monotonic AND-join fixed point**: pulses accumulate and are
never retracted; `drain()` only ever adds reachable types. Cancellation is
**non-monotonic** — it retracts pulses / withdraws enabled gates. A naive active-cancel
primitive would violate the core assumption the prover, the conformance checker, and the
twin's pulse propagation are all built on. Any option here must state what it does to
that assumption.

## Options

### Option A
**Cancellation as a first-class term (pulse), flowing through normal synapses.**
Introduce a `cancellation` base slot type. A cancellable gate declares it consumes a
`cancellation` (like `optional`), and on receiving one emits its own
compensating/terminal outcome. Cancellation is just another typed fact that travels —
consistent with the standing ontology rule ("facts that travel are terms; things that
act are loci"). This is what encore_tickets' hand-built CancellationRouter path already
approximates.

**Tradeoffs:** Zero new mechanism — reuses pulses, synapses, and the existing monotonic
proof model intact (a cancellation pulse is just another reachable type; nothing is
retracted, the downstream gate *reacts* forward). Cleanest fit with Opis doctrine and
the twin. Cost: it does NOT model true withdrawal of in-flight work — the cancelled gate
still "fires" (into a cancelled/compensated outcome) rather than being un-fired. Semantic
honesty: this is compensation, not cancellation. Maps WCP19/20 well, WCP29/32
(winner-cancels-losers mid-flight) only approximately.

### Option B
**Active cancel edge: a `cancels: [gate_ids]` field on a gate outcome.**
An outcome may name downstream gates (or a region) whose in-flight pulses are actively
withdrawn when that outcome fires. Directly models Cancel Task/Region and the Cancelling
Discriminator/Partial Join (the FIRST/THRESHOLD winner lists the losers in `cancels:`).

**Tradeoffs:** Faithful to the literature — expresses true withdrawal, closes all 7
patterns. Cost is heavy and lands on the verifiers: cancellation is non-monotonic, so
`proof.py`'s fixed point, `gate_proof.py`, conformance, and the twin's virtual-clock
propagation all need a retraction model (a pulse can be removed after being enqueued).
This is the assumption those tools were explicitly built NOT to need. High research value,
high blast radius. Would need its own verifier work before any gate uses it.

### Option C
**Generalize the breaker with an external trip input.**
Keep one cancellation concept. Today a breaker trips on `trips_on`; add an external trip
synapse so an upstream gate can trip a downstream breaker, suppressing its region until
`recovery_ms`. Reuses all existing breaker machinery.

**Tradeoffs:** Smallest surface — no new type, no new field, breaker semantics already
understood by the twin. But it conflates two different things: a breaker *auto-recovers*
after a timer, whereas a cancel is usually *permanent for that flow run*. Modeling a
one-shot cancel as a self-healing breaker is a semantic mismatch that will mislead FA.
Suppression is also coarse (whole region, timer-based), not the targeted withdrawal
WCP19/29 describe.

### Architect's option (optional)

<!-- Add your own alternative here and name it in Decision. One candidate worth naming:
     Option A now (compensation term, unblocks the katas cheaply and honestly) + a
     deferred Option B once a retraction-aware proof model is scoped — i.e. sequence
     them rather than choose. -->

## Decision

<!-- Fill in your choice here before proceeding. -->
