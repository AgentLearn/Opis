# Domain→SA mapping batch 3: titantrain, oracleserve, agentmesh

Three scale/AI/multi-agent katas — the domains that most stress distributed coordination.
Mapped against 5-axis `sa_taxonomy_v1.json` with the granularity lens. Compact tables +
the NEW candidates each surfaces. Rolls into `cross_kata_synthesis_v1.md` (updated to 11 katas).

Legend: **bold** = new territory / gap; tmpl-M = movement (EIP), tmpl-C = computation.

---

## TitanTrain (distributed ML training at scale)

| # | behaviour | term | tmpl-M | tmpl-C | logic | kind | note |
|---|-----------|------|--------|--------|-------|------|------|
| 1 | ingest data, transform to features in batches | features (VO) | — | ParDo + Windowing (batch) | — | plain | batch compute |
| 2 | remove duplicate/malformed records | record | Message Filter | Entity Resolution | — | plain | entity-res (3rd domain) |
| 3 | workers compute gradients → aggregate to update | gradient | Aggregator | Combine (all-reduce) | **AND (many→1)** | plain | large-scale fan-in |
| 4 | sync each step; stragglers → proceed on majority | — | Aggregator | — | **SYNC BARRIER → THRESHOLD** | plain | **NEW logic flavor; CAP sync-vs-async** |
| 5 | checkpoint periodically; resume after failure | checkpoint | — | — | — | plain | **NEW: state snapshot / durability** |
| 6 | scarce accelerators by priority; exclusive hold | job | — | priority schedule | — | regulator | priority(4th) + mutual-excl(6th, scarce resource) |
| 7 | many HP trials; stop losers early, keep best | trial | — | — | **FIRST/best** | plain | **NEW: speculative exec + cancel (WCP32)** |
| 8 | promote model only after benchmark validation | model | — | — | — | plain | quality Milestone |
| 9 | deployed accuracy degrades → auto-retrain | — | — | — | — | plain | feedback loop (2nd domain) |

New: **sync barrier** (repeated AND-join, straggler-tolerant → THRESHOLD; the BSP model),
**checkpoint/snapshot** (durability & recovery — no corpus names it; source: Chandy-Lamport
distributed snapshots), **speculative execution with cancel** (race N trials, keep best,
cancel rest = Cancelling Partial Join WCP32 — a new *speculative* flavor of the cancellation
family). Confirms entity-resolution, feedback loop.

## OracleServe (AI inference at scale)

| # | behaviour | term | tmpl-M | tmpl-C | logic | kind | note |
|---|-----------|------|--------|--------|-------|------|------|
| 1 | route requests across replicas, balance load | request | **Competing Consumers (load balance)** | — | — | plain | movement (1st explicit LB) |
| 2 | serve identical/near-dup from cache | request | — | Entity Resolution (near-dup) | — | plain | **cache**; entity-res (4th) |
| 3 | accumulate into batches for accelerator | batch | — | Windowing (batch) | — | plain | **buffering (2nd hit)** |
| 4 | guardrails filter unsafe in+out | — | Message Filter (pre+post) | — | — | plain | safety gate; pre+post placement |
| 5 | combine several models; resolve disagreement | answer | Aggregator | **Fusion / Quorum** | THRESHOLD | plain | fusion(3rd)+quorum(2nd) confirm |
| 6 | primary slow/down → fallback to simpler model | — | Content-Based Router | — | FIRST+window | **breaker** | **fallback = breaker+timeout (confirm)** |
| 7 | route a fraction to candidate model (canary) | request | **ratio / weighted router** | — | — | plain | **NEW: probabilistic routing (cousin of Opis prob-outcomes)** |
| 8 | monitor prediction distribution for drift | metric | — | Combine+Windowing + anomaly | — | plain | drift = monitoring anomaly (confirm) |
| 9 | collect user feedback → improve models | feedback | — | — | — | plain | feedback loop (3rd) + human-in-loop |
| 10 | per-tenant rate limit by plan | — | — | — | — | regulator | value/priority-weighted |

New: **load balancing** (Competing Consumers — first explicit movement instance),
**ratio/canary routing** (weighted probabilistic routing — the first external cousin of Opis's
genuinely-original probabilistic outcomes; A/B split by fraction). Confirms fusion/quorum,
breaker+timeout fallback, buffering, feedback loop, anomaly, regulator.

## AgentMesh (scalable multi-agent coordination) — Opis dogfood-adjacent

| # | behaviour | term | tmpl-M | tmpl-C | logic | kind | note |
|---|-----------|------|--------|--------|-------|------|------|
| 1 | coordinator decomposes goal → delegate subtasks | task | Splitter | — | — | plain | **NEW: hierarchical delegation / recursion (WCP22)** |
| 2 | agents register/deregister dynamically | agent | — | — | — | plain | **NEW: dynamic membership / registry** |
| 3 | spawn agents on load, retire when idle | — | — | — | — | regulator | **NEW: elastic scaling / dynamic instances (WCP15 gap, 1st hit)** |
| 4 | agents bid; best-suited wins task | bid | — | — | **auction/best** | plain | **NEW: contract-net / auction** |
| 5 | shared workspace; conflicting writes prevented | — | — | — | — | regulator | **NEW: blackboard + mutual-excl (5th)** |
| 6 | aggregate subtask results; proceed when enough | result | Aggregator | Combine | **THRESHOLD** | plain | fan-in (confirm) |
| 7 | unresponsive agent → reassign its tasks | task | Content-Based Router | Aggregate (liveness) | — | breaker | heartbeat (5th) |
| 8 | circular task deps detected + broken | — | — | — | — | plain | **NEW: deadlock / cycle detection** |
| 9 | unresolved in bound → escalate to human | — | Content-Based Router | — | FIRST+window | plain | timeout-escalation (confirm) |
| 10 | full decomposition tracked as hierarchical job | job (entity) | — | Aggregate | — | plain | recursion + long-running |

New (richest kata for new primitives — 6): **hierarchical delegation/recursion** (WCP22, maps
to Opis gate-internals/GA), **dynamic membership** (service registry), **elastic scaling /
dynamic instances** (WCP15 — the dynamic-MI gap, finally exercised), **contract-net / auction**
(market-based allocation; source: Smith 1980 Contract Net Protocol; absent from all corpora),
**blackboard shared-state** (+ mutual exclusion), **deadlock/cycle detection**. Confirms fan-in,
heartbeat, timeout-escalation, long-running entity.

## Granularity calls (batch 3, condensed)
- **UNIFY:** titan #7 (trial-scoring + kill-losers co-depend → one speculative-trial-manager),
  agentmesh #10 (the hierarchical job IS one entity).
- **SPLIT:** oracle #4 (pre-inference vs post-inference guardrails are independently useful →
  two filter gates at different flow positions), oracle #6 (fallback routing vs the primary
  call — fallback is separately useful), titan #2 (dedup vs malformed-filter are different
  compute roles).
- **Atomicity override:** titan #6 (accelerator acquire+hold), agentmesh #5 (blackboard write
  lock) — mutual-exclusion, one atomic gate.
- **Established-practice override:** oracle #5 (ensemble = Scatter-Gather+resolve, one idiom).
- **Recursion note:** agentmesh #1/#10 — hierarchical delegation is Opis's own gate-internals
  recursion turned into a domain behaviour. The taxonomy describing a system shaped like Opis
  itself is a useful dogfood signal.
