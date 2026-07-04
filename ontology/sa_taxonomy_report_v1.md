# SA taxonomy report v1 — assembled from published ontologies

Phase-1 (breadth-build) deliverable: the **SA taxonomy** — the gate-composition
vocabulary — assembled from three established ontologies, one per axis, plus the
domain-facing term axis. This is the literature-grounded TARGET that business domain
terms map onto (Phase-1 also exercises that mapping; see "Next" below).

Files: `sa_taxonomy_v1.json` (assembled, validated: 29 nodes, 0 dangling refs),
`corpus/workflow_control_flow_patterns.md`, `corpus/enterprise_integration_patterns.md`,
`corpus/resilience_patterns.md`, `induced_ontology_v1.json` (full 43-pattern logic axis).

## The four axes and their sources

| axis | what it fixes about a gate | source ontology | grounding |
|------|---------------------------|-----------------|-----------|
| **term** | what data flows (domain-facing) | Opis slot_types; OWL-S/FIBO if needed | not re-derived this run |
| **logic** | how it joins/branches inputs | van der Aalst/Russell Workflow Patterns (43) | 9 exact / 26 partial / 8 none |
| **template** | what it does to messages | Hohpe & Woolf EIP (65) | routing+transformation groups |
| **kind** | its stability role | Nygard Release It! + Azure resilience | **all 3 non-plain kinds exact** |

Of the 21 gate-vocabulary nodes (logic + template + kind): **15 exact, 3 partial, 3 no
Opis counterpart.**

## Headline: the kind axis is the best-grounded, and confirms Opis borrowed well

All three non-plain gate kinds have **exact source definitions** in the resilience
literature — Opis did not invent them:
- `breaker` = **Circuit Breaker** (trips_on = threshold, recovery_ms = timeout-to-half-open).
- `sentinel` = **Gatekeeper** (validation broker in front of a protected resource).
- `regulator` = **Throttling / Governor** (rate limiting to a safe envelope).

## The logic and template axes meet at the Aggregator

The EIP **Aggregator** is the *template* form of the gate `logic` join: its completeness
condition ("wait for all" / "wait for n") IS AND / THRESHOLD, plus a correlation. This is
the one place the three axes are not independent — a join gate is simultaneously a logic
value and a template. Worth encoding: `routing_decision_aggregator` should declare both.

And FIRST = THRESHOLD(n=1) (Discriminator = 1-of-m Partial Join) — same collapse noted in
the logic-axis diff. The gate logic operators are a faithful, slightly-reduced subset of
the workflow-pattern canon.

## The timing nuance — stated precisely

The logic-axis diff called windows/refractory "Opis-original." The resilience corpus
sharpens this: they are original to **workflow modeling** (that literature is untimed) but
**standard in resilience engineering**:
- `input_timeout_ms` = the **Timeout** stability pattern (exact).
- `recovery_ms` = Circuit Breaker recovery + Governor rate-limit (grounded).

So the honest claim is narrower than "Opis invented timed gates": Opis's contribution is
*bringing the resilience-engineering timing layer into the workflow-pattern composition
model* — the two literatures never met, and gates are where they do. What remains with
**no counterpart in any of the three ontologies**:
- **probabilistic outcomes** (twin-sampling) — genuinely Opis-original.
- **p50/p95 latency budgets** — distributional, vs. Timeout's hard bound (partial).

## Consistent gaps across two axes (the same three families)
The template axis surfaces the SAME gaps as the control-flow axis, independently:
- **Dynamic Router** (EIP) ↔ runtime-mutable routing — no Opis template.
- **Resequencer / Durable Subscriber** (EIP) ↔ ordering + buffering ↔ WCP24 Persistent
  Trigger. Buffering/ordering has no gate-logic primitive (lives in gate internals / CA).
- **Bulkhead** (resilience) ↔ per-compartment isolation — the one kind-axis gap; a
  candidate refinement of `regulator`.

Two independent literatures pointing at the same missing family (runtime-dynamic /
ordering / buffering) is a stronger signal than the control-flow diff alone gave.

## Clean layer boundaries confirmed (gaps that are actually decisions)
EIP Message Translator / Normalizer / Canonical Data Model and resilience Retry /
Backpressure land **below or beside** the gate layer — the CA schema layer and
gate-internals / synapse layer respectively. These are not gaps; they confirm the
standing "payload content = CA layer" boundary from an outside source.

## Next (Phase-1 continues)
1. **Exercise the domain→SA mapping on a kata** — take one kata's business behaviours and
   resolve each to the 4-tuple (term, logic, template, kind) against this taxonomy. This
   is the actual Phase-1 skill; the taxonomy above is only the target.
2. Load `sa_taxonomy_v1.json` + `induced_ontology_v1.json` into Neo4j (extend
   `load_ontology.cypher`) so the mapping is queryable.
3. Term axis: decide whether to ground slot_types in OWL-S IOPE / FIBO or keep Opis's own.
4. (Deferred to Phase 3) deep primitive gaps — cancellation (ADR-X001), bulkhead
   isolation, buffering/ordering.
