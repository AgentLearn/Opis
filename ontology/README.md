# ontology/ — gate-ontology seeding (OG-RAG-style induction)

First hand-run of the gate-ontology track. Scope: the **control-flow perspective**
only (van der Aalst / Russell workflow patterns), the layer where Opis gate `logic`
and `kind` live. Method follows OG-RAG (arXiv:2412.15235) Appendix B: a fixed
**context definition** + **data** → JSON-LD `@graph`.

Per the Opis first principle, this is a **golden recipe**, not load-bearing product:
`induction_prompt.md` is the prompt an agent (FA taxonomy **stage 2**) must reproduce.

## Files
- `corpus/workflow_control_flow_patterns.md` — hand-curated seed corpus, 43 patterns,
  with source provenance (workflowpatterns.com, BPM-06-22, DPD 2003).
- `induction_prompt.md` — the App-B-adapted induction prompt (context definition +
  instructions). The recipe.
- `induced_ontology_v1.json` — the induced ontology (JSON-LD, 43 patterns + Opis
  targets). Validated: 43/43 patterns, 0 dangling refs.
- `diff_report_v1.md` — the finding: induced ontology diffed against Opis vocabulary.
- `load_ontology.cypher` — Neo4j loader for the gate ontology (gates-RAG store).

## Headline finding
Of 43 control-flow patterns: **9 map exactly, 26 partially, 8 have no Opis counterpart.**
Opis's join logic (AND/OR/FIRST/THRESHOLD) is a faithful subset of the pattern canon —
it collapses the 6 discriminator/partial-join variants by dropping the blocking/
cancelling axes. Opis's genuine novelty is **orthogonal**: the timing + probability layer
(refractory, windows, probabilistic outcomes, latency budgets, self-recovering breaker)
that the workflow-patterns literature deliberately never modeled. Biggest gap: an
explicit **cancellation** primitive (7 patterns), which would complement the breaker.

## Next steps
1. Zarko: decide via ADR which gaps (§4 of the diff report) become real gate primitives
   — the cancellation family is the principled candidate.
2. Optional corpus expansion: add EIP (gate templates) and resilience patterns (kinds)
   as further corpus files, re-run induction to extend beyond control-flow.
3. Agentify: turn `induction_prompt.md` into FA taxonomy stage 2 with a mechanical
   JSON-LD validator (mirrors how stage 1 validates `extends`).
4. Load real gates + slot_types as nodes alongside the patterns
   (Gate-[:USES_LOGIC]->GateLogic, Term-[:EXTENDS]->Term) so gate selection and the
   pattern mapping share one graph.
