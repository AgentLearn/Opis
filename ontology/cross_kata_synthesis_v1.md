# Cross-kata synthesis v1 — 8 katas, Phase-1 breadth roll-up

Katas mapped: **silicon_sandwiches, ripple_rides, encore_tickets** (commerce),
**sentrygrid_monitoring** (IoT/monitoring), **dockyard_fulfillment** (logistics),
**triageflow_ed** (healthcare), **surveyorswarm_planetary** (autonomous/distributed),
**aegiswatch_threat_detection** (security). 8 domains, 5 broadly non-commerce.
Per-kata detail in `mapping_*.md` and `mapping_batch2_v1.md`.

## 1. Central hypothesis holds: the SA taxonomy is domain-neutral
Every axis (term, logic, template-movement, template-computation, kind) was exercised by
domains with no shared vocabulary. A gate's identity is *how it coordinates and computes*,
not what business it is in. The domain→SA mapping resolved the large majority of behaviours
in all 8 katas against the same fixed axes.

## 2. Domain shape = the axis MIX (a usable fingerprint)
The axes are fixed; their proportions vary by domain and characterize it:
- **commerce** (silicon/ripple/encore): movement-heavy — routing, joins, scatter-gather;
  state for money/inventory/loyalty.
- **monitoring** (sentrygrid): computation-heavy — windowed aggregation dominates.
- **logistics** (dockyard): scheduling + saga-heavy — priority, mutual exclusion, compensation.
- **healthcare** (triage): state-machine-heavy — milestones, resource locks, long-running.
- **distributed** (surveyor/aegis): fusion + fault-tolerance + consensus; CAP tradeoffs explicit.
The axis histogram of a kata is a compact signature of its domain.

## 3. Recurring templates = the genuinely reusable library (breadth payoff)
By the granularity principle (independent usefulness across katas ⇒ library-worthy), the
templates attested in the most domains:

| template / gate | domains | count |
|-----------------|---------|-------|
| intake / auth (Gatekeeper + sentinel) | all 8 | 8 |
| timeout deferred-choice (window→reroute/escalate) | ripple, sentry, dock, triage, aegis | 5 |
| cancellation / compensation | ripple, encore, dock, triage, aegis | 5 |
| heartbeat-timeout + reassign | sentry, dock, surveyor, aegis | 4 |
| mutual exclusion / critical section | encore, dock, triage, surveyor | 4 |
| fan-in join (AND/THRESHOLD, many→1) | encore, triage, surveyor, aegis, silicon | 5 |
| loop / rework (feedback) | dock, triage, surveyor | 3 |
| priority scheduling | dock, triage, aegis | 3 |
| stateful accumulate (Combine+Aggregate) | ripple, silicon, encore, sentry, aegis | 5 |
| payment-precondition join | silicon, ripple, encore | 3 |
| sensor fusion (heterogeneous) | surveyor, aegis | 2 |
| entity resolution / correlation-merge | surveyor, aegis | 2 |
| scoped-owner write | silicon, encore | 2 |

## 4. Confirmed gaps, ranked by cross-domain evidence
The gaps are no longer speculative — each has kata evidence, several across many domains:

1. **Timeout deferred-choice** (5 domains) — "within a window, else re-route/escalate."
   FIRST + window + reroute. **Highest-evidence gap.** (WCP16 Deferred Choice + timeout.)
2. **Cancellation / compensation** (5 domains) — from single release (encore) to multi-leg
   saga (dockyard restock+release). ADR-X001; non-monotonic; the depth varies. **Highest-value.**
3. **Mutual exclusion / critical section** (4 domains) — single-resource (encore),
   dual-resource-atomic (triage), spatial (surveyor). Correctness-critical (oversell, deadlock).
4. **Heartbeat / absence-timeout** (4 domains) — fire on *absence* of input for a period.
   Dead-man's switch; not modeled by presence-triggers or per-firing input_timeout_ms.
5. **Loop / rework** (3 domains) — Opis has feedback synapses but no first-class rework/retry
   routing with a bound. (WCP21 Structured Loop.)
6. **Priority scheduling** (3 domains) — priority/value-weighted queues; Dataflow/EIP have no
   priority. Triage adds **mutable priority** (re-triage changes a queued item's rank).

## 5. NEW template/primitive candidates surfaced (need corpus additions)
These are not gaps in Opis vs. the corpora — they are gaps in the **corpora themselves**;
the assembled taxonomy doesn't yet name them, and 2+ katas need them:

- **Sensor fusion (heterogeneous multi-source integration)** — surveyor #4, aegis #3.
  Combine different *modalities/methods* into one estimate. Distinct from Dataflow Combine
  (same-type fold per key). Candidate source: **data-fusion / Kalman-Bayesian estimation
  literature (JDL fusion model)**. → extend computation corpus.
- **Entity resolution / correlation-merge** — surveyor #6 (landmarks), aegis #6 (alerts→case).
  Decide two records denote the *same entity*, then merge. Distinct from dedup-by-key.
  Candidate source: **record-linkage / entity-resolution literature; CRDT merge**. → extend
  computation corpus.
- **Quorum / consensus (Byzantine-tolerant)** — aegis #4/#5 (corroborate before accusing a
  trusted insider). Voting over independent signals; no source ontology has it. Candidate
  source: **distributed-consensus literature (quorum, BFT)**. → possibly a 6th mini-axis or a
  logic-axis extension (it is a *kind of join* — agreement join).
- **Feedback loop (closed-loop control)** — surveyor #11 (map re-tasks drones). Output feeds
  input; all prior katas are open pipelines. Candidate source: **control theory / MAPE-K
  autonomic loop**. → likely a flow-topology property, not a gate template.
- **Buffering / store-and-forward** — surveyor #8 (WCP24 Persistent Trigger, first hit).
  Retain input until deliverable. Gap already known; now has a kata.

## 6. Structural insights (the taxonomy teaching us about gates)
- **Axes compose.** A per-entity breaker = kind × computation(Combine+Aggregate) × timing
  (window) — its `trips_on` is a windowed reduction, not a scalar. (ripple, sentry, aegis.)
- **Stateful reducer has two sub-uses:** *accumulate* (count/sum — loyalty, confidence,
  liveness) vs. *enforce-invariant* (capacity≥0 — encore). Split in taxonomy v2.
- **Granularity principle has two overrides, both now attested:** (a) established practice
  (Scatter-Gather bundles reconcile), (b) **atomicity** (dual-resource lock, check+decrement
  must be one transaction even though the parts are independently useful). Atomicity override
  is new from batch 2 — add it to the principle.
- **CAP is expressible.** Distributed katas (surveyor, aegis) make the A-vs-C choice concrete:
  proceed-on-fraction + buffer-then-sync = availability + partition tolerance over consistency;
  reconcile/correlate = eventual-consistency repair. The taxonomy can *describe* the tradeoff
  a flow takes — a candidate quality attribute on a flow.

## 7. Candidate taxonomy v2 edit list (consolidated)
1. Split `stateful reducer` → **accumulate** | **enforce-invariant**.
2. Add **sensor fusion** compute template (source: JDL/Kalman fusion).
3. Add **entity resolution / merge** compute template (source: record-linkage / CRDT).
4. Add **quorum / consensus** construct (source: distributed consensus) — decide axis home.
5. Add **priority scheduling** construct incl. mutable priority (no corpus source yet — new).
6. Add **mutual exclusion / critical section** construct (WCP39) — with atomic multi-resource.
7. Add **timeout deferred-choice** construct (WCP16 + timeout) — highest-evidence gap.
8. Add **absence / heartbeat-timeout** construct.
9. Add **loop / rework** construct (WCP21) with a bound.
10. Add **buffering / persistent-trigger** construct (WCP24).
11. Record **kind ∘ computation ∘ timing** composition (richer `trips_on`).
12. Add **feedback-loop** and **CAP tradeoff** as flow-level (topology/quality) properties.
13. Add **atomicity** as a second override to the granularity principle.

---

## UPDATE — batch 3 rolls the synthesis to 11 katas (titantrain, oracleserve, agentmesh)

Domains now: commerce ×3, monitoring, logistics, healthcare, autonomous/distributed,
security, **ML training, AI inference, multi-agent** — 11 katas, 8 broadly non-commerce.
Central hypothesis still holds: every axis exercised, no domain broke the 5-axis frame.

### Recurring templates (updated counts, 11 katas)
- intake/auth: still broad; **fan-in join (AND/THRESHOLD)** now ~8 domains (added titan
  all-reduce, oracle ensemble, agentmesh result-aggregation) — the single most universal join.
- **heartbeat + reassign** now 5 (added agentmesh).
- **feedback loop** now 3 (surveyor, titan retrain, oracle RLHF) — promoted from a 1-off to a
  recurring, cross-domain construct. No longer an edge case.
- **entity resolution** now 4 (surveyor, aegis, titan dedup, oracle cache) — strong.
- **mutual exclusion** now 6 (added titan accelerators, agentmesh blackboard).
- **timeout deferred-choice** now 6 (added oracle fallback, agentmesh escalation) — still #1.

### NEW candidates from batch 3 (added to §5 list)
- **Sync barrier** (titan #4) — repeated AND-join per iteration, straggler-tolerant → THRESHOLD;
  the BSP model. A new *logic-axis* flavor (barrier vs. one-shot join). CAP: sync vs async SGD.
- **Checkpoint / state snapshot** (titan #5) — periodic durable state for recovery. No corpus
  names it. Source: Chandy-Lamport distributed snapshots. Likely a flow-level durability property.
- **Speculative execution + cancel** (titan #7) — race N, keep best, cancel rest = Cancelling
  Partial Join (WCP32). New *speculative* flavor of the cancellation family (§4.2).
- **Elastic scaling / dynamic instances** (agentmesh #3) — WCP15 (MI without runtime knowledge),
  the dynamic-instance gap flagged in the control-flow corpus, now first exercised.
- **Dynamic membership / service registry** (agentmesh #2) — agents join/leave at runtime.
- **Contract-net / auction** (agentmesh #4) — market-based task allocation; a *negotiated* join,
  not a router decision. Source: Smith 1980 Contract Net Protocol. Absent from all corpora.
- **Deadlock / cycle detection** (agentmesh #8) — mutual-exclusion family, correctness.
- **Hierarchical delegation / recursion** (agentmesh #1/#10) — WCP22; maps onto Opis's own
  gate-internals recursion (GA). Dogfood-adjacent.
- **Blackboard shared-state** (agentmesh #5) — shared mutable workspace + mutual exclusion.
- **Load balancing** (oracle #1) — Competing Consumers (EIP), first explicit movement instance.
- **Ratio / canary routing** (oracle #7) — weighted probabilistic routing; the first external
  cousin of Opis's genuinely-original probabilistic outcomes (A/B split by fraction).

### Structural insight from batch 3
- **AgentMesh describes a system shaped like Opis itself** (coordinator delegates to agents,
  recursion, dynamic pool). The taxonomy handling it is a dogfood signal — the SA taxonomy can
  describe agentic architectures, which is what Opis builds.
- **Feedback loops crossed the threshold from anomaly to axis-property.** With 3 domains
  (survey re-task, titan retrain, oracle RLHF), closed-loop output→input is a recurring
  flow-topology property, joining CAP as a flow-level (not gate-level) attribute.
- **The cancellation family now spans single-release → multi-leg saga → speculative-race**
  (encore, dockyard, titan). It is not one primitive but a spectrum by "what is withdrawn."

### Consolidated v2 edit list now ~20 items
The §7 list (13) plus the 11 batch-3 candidates above (several overlap: speculative-cancel
folds into cancellation; sync-barrier extends logic; elastic-scaling = WCP15 buffering-family).
Net-new taxonomy nodes to add in v2: sync-barrier (logic), checkpoint (flow durability),
elastic-scaling/dynamic-instances, dynamic-membership, contract-net/auction, deadlock-detection,
hierarchical-delegation/recursion, blackboard, load-balancing (movement), ratio-routing.

---

## 8. Recommendation
Phase-1 breadth is well-attested (8 domains, axes generalize, gaps cross-validated, new
template candidates identified with sources). Suggested close-out of Phase 1:
1. Add the 3 corpus files the new candidates need (fusion, entity-resolution, consensus) and
   fold the v2 edits into `sa_taxonomy_v2.json`.
2. Load the taxonomy + all 8 mappings into Neo4j so §3–§5 (recurring templates, gap evidence,
   new candidates) become live queries rather than hand-maintained tables.
3. Then Phase 2 (validate wide via FA runs) / Phase 3 (depth per kata) per the strategy.
