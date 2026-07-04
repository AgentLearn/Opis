# Ontology-induction prompt (golden recipe)

Adapted from OG-RAG (Sharma, Kumar, Li — Microsoft Research, arXiv:2412.15235),
Appendix B.1 "Ontology Prompt". OG-RAG's prompt maps DATA onto a fixed CONTEXT
DEFINITION and emits JSON-LD under an `@graph` namespace. We reuse that two-part
shape: a **context definition** (the schema/vocabulary we want the ontology to use)
plus the **data** (the seed corpus), producing a JSON-LD `@graph`.

This is the hand-run golden recipe. The agentified form is FA taxonomy **stage 2**:
the same context definition becomes a system prompt, the corpus becomes retrieved
context, and the induced ontology is mechanically validated (as taxonomy stage 1
already validates `extends` against slot_types).

Per the Opis first principle: this hand-built induction defines the recipe an agent
must reproduce. Nothing here is load-bearing product; it is scaffolding + evidence.

---

## Context Definition (schema the induced ontology must use)

An ontology O ⊆ S × A × (S ∪ {φ}) is a set of triples (subject, attribute, value),
where value is another entity or an unspecified domain value (OG-RAG Definition 1).

Entity types (classes):
- `ControlFlowPattern` — a named, reusable control-flow construct from the literature.
- `PatternCategory` — a grouping of patterns (Basic, Advanced Branching, Multiple
  Instance, State-Based, Cancellation, Iteration, Termination, Trigger).
- `GateLogic` — an Opis gate join-logic operator (AND, OR, FIRST, THRESHOLD).
- `GateKind` — an Opis gate kind (regulator, breaker, sentinel, plain).
- `OpisConstruct` — any Opis primitive not reducible to GateLogic/GateKind
  (refractory, window, probabilistic outcome, latency budget, synapse, outcome-routing).

Attributes (relations):
- `wcpId` — the WCP identifier (literal).
- `inCategory` — ControlFlowPattern → PatternCategory.
- `semantics` — literal one-line control-flow meaning.
- `synchronizes` — literal: does the pattern wait for multiple inputs? (all / n-of-m /
  one / none).
- `mapsToOpis` — ControlFlowPattern → GateLogic | GateKind | OpisConstruct (the
  induced alignment; may be φ if none).
- `mappingStrength` — literal: exact | partial | none.
- `opisGap` — literal note on what Opis lacks to fully express the pattern (or φ).
- `generalizes` / `specializes` — ControlFlowPattern → ControlFlowPattern (e.g.
  Structured Discriminator specializes Structured Partial Join with n=1).

## Induction instructions (adapted from OG-RAG B.1)

Generate a JSON-LD using the following data and the above context definition for a
software-architecture control-flow pattern ontology.
Use `@graph` for the data in JSON-LD.
Be comprehensive: emit one node per ControlFlowPattern in the corpus (all 43), one per
PatternCategory, and the GateLogic / GateKind / OpisConstruct nodes they map to.
Do not combine enumerated patterns into a single node; keep each separate to disambiguate.
Populate every pattern; do not leave any item out.
For each pattern, fill `mapsToOpis`, `mappingStrength`, and `opisGap` — these three
fields ARE the finding; φ / "none" is a valid and important value.
Keep nesting minimal while remaining unambiguous.

## Data

The seed corpus: `corpus/workflow_control_flow_patterns.md` (43 control-flow patterns
with categories, semantics, and the curator's candidate Opis mapping — the induction
must independently confirm or revise each mapping, it is not bound by the curator table).

## Output

`induced_ontology_v1.json` — the JSON-LD `@graph`.
