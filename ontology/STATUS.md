# SA-taxonomy track — status (2026-07-04)

Where the gate-ontology / GraphRAG work stands, and what's open.

## HAVE (built + committed on ga_loop)

**The taxonomy (the target business terms map onto):**
- `corpus/` — 4 sourced corpus files: workflow control-flow patterns (logic axis),
  Enterprise Integration Patterns (movement templates), resilience patterns
  (kinds), computation patterns = Dataflow + DDD (compute templates).
- `sa_taxonomy_v1.json` — the assembled **5-axis** taxonomy: term, logic,
  template_movement, template_computation, kind. 36 nodes, validated, 0 dangling refs.
- `induced_ontology_v1.json` — 43 control-flow patterns induced (OG-RAG App-B recipe
  in `induction_prompt.md`), mapped to Opis logic (9 exact / 26 partial / 8 none).

**The evidence (11 katas mapped domain→SA):**
- Commerce: silicon_sandwiches, ripple_rides, encore_tickets.
- Non-commerce: sentrygrid (monitoring), dockyard (logistics), triageflow (healthcare),
  surveyorswarm (drone swarm), aegiswatch (security+UEBA), titantrain (ML training),
  oracleserve (AI inference), agentmesh (multi-agent).
- Reports: `mapping_*.md` (per kata), `mapping_batch2/3_v1.md`, and the roll-up
  `cross_kata_synthesis_v1.md` (11-kata synthesis, ~20-item v2 edit list).

**The pipeline, step 1:**
- `graph/build_graph.py` + `graph/step1.py` — the taxonomy loaded into an embedded
  **Kùzu** graph DB; step-1 retrieval (kata behaviour → SA-taxonomy subset + candidate
  gates) runs as a **Cypher** query. Working, recall-biased.
- `load_ontology.cypher` — portable Neo4j loader (kept for portability).

**Decisions parked:**
- `ADR-X001_cancellation_primitive.md` — cancellation primitive, decision pending (Phase 3).

## LEARNED (the substance)

1. **Taxonomy is domain-neutral** — held across 11 domains, 8 non-commerce. A gate's
   identity is how it coordinates/computes, not its business.
2. **Axis mix fingerprints a domain** — commerce=movement-heavy, monitoring=compute-heavy,
   distributed=fusion/fault-tolerance/consensus.
3. **The reusable library = recurring templates** (by domain-count): intake/auth,
   fan-in-join, timeout-deferred-choice, cancellation, stateful-accumulate, heartbeat,
   mutual-exclusion, priority-schedule, loop/rework.
4. **New primitive candidates the corpora themselves lack** (2+ katas): sensor fusion,
   entity resolution, quorum/consensus, feedback loop, buffering, sync-barrier,
   checkpoint, speculative-cancel, elastic-scaling/dynamic-instances, contract-net/auction,
   deadlock-detection, hierarchical-delegation, blackboard, load-balancing, ratio-routing.
5. **Structural insights:** axes compose (a breaker's `trips_on` = a windowed reduction);
   granularity principle has two overrides (established-practice + atomicity); cancellation
   is a spectrum (release → saga → speculative-race); CAP and feedback-loops are flow-level
   attributes; stateful-reducer splits into accumulate | enforce-invariant.

## NEED (open work, roughly ordered)

1. ~~Structure the mappings.~~ **DONE** — `graph/extract_mappings.py` parses the 3 table
   layouts → `mappings.jsonl` (101 behaviours / 11 katas, 81 with axis tokens).
2. ~~Precedent-based step-1 retrieval.~~ **DONE** — `build_graph.py` loads behaviours as
   `(Behaviour)-[:USES]->(Concept)` + `-[:REALIZES_GATE]->(Gate)` (197 uses-edges); `step1.py`
   ranks gates by precedent frequency + surfaces nearest precedent behaviours.
   *Caveat:* only 9 precedent-gate edges (gate names existed only in the silicon table) → GATE
   ranking is thin until FA repopulates the library; precedent-BEHAVIOUR retrieval works now.
3. **Step 0 — real term typing.** Currently a hardcoded hint list. Type a kata's DSL terms
   (entity vs value-object, base slot_type) properly before retrieval.
4. **Taxonomy v2.** Fold the ~20 synthesis edits + add corpus files for the new candidates
   (fusion, entity-resolution, consensus, auction) → `sa_taxonomy_v2.json`. Also fills the
   current "no match" gaps (intake, dynamic-membership, elastic-scaling, mutual-exclusion).
5. **ADR-X001 decision** (cancellation) — Phase 3.
6. **Wire step 1 → FA** (generation) — begins Phase 2 (validate-wide). *Now head of the path.*
7. **Agentify the induction** — turn `induction_prompt.md` into FA taxonomy stage 2 with a
   mechanical validator (per the first principle: hand-built = golden recipe).

Retrieval is lexical-trigger-seeded today; as FA populates gates, precedent supersedes
triggers, and embeddings can replace lexical matching later with no schema change.

## Critical path
~~(1) structure mappings~~ → ~~(2) precedent retrieval~~ → **(6) wire to FA** ← now.
Rest (v2 edits, term typing, ADR, agentify) can proceed in parallel.
