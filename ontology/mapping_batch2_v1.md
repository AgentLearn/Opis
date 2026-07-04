# Domain→SA mapping batch 2: dockyard, triageflow, surveyorswarm, aegiswatch

Four katas built together to target known gaps + new axis territory (loops/rework,
priority/scheduling, sagas, many-to-one fan-in, distributed/fault-tolerant). Mapped against
5-axis `sa_taxonomy_v1.json` with the granularity lens. Compact per-kata tables + the NEW
templates/gaps each surfaces; full cross-kata roll-up in `cross_kata_synthesis_v1.md`.

Legend: **bold** = new territory or a gap; tmpl-M = movement (EIP), tmpl-C = computation.

---

## DockYard (warehouse fulfillment)

| # | behaviour | term | tmpl-M | tmpl-C | logic | kind | note |
|---|-----------|------|--------|--------|-------|------|------|
| 1 | pick waves by deadline+priority | wave | Aggregator (batch) | **priority schedule** | — | plain | **priority (new)** |
| 2 | one picker per bin at a time | assignment | — | — | — | regulator | **mutual excl. (2nd)** |
| 3 | ship only when all items packed | order | Aggregator | — | **AND (many→1)** | plain | fan-in |
| 4 | failed QC → re-pick alternate bin | item | Content-Based Router | — | — | plain | **loop/rework (new)** |
| 5 | dock not free in window → reroute | shipment | Content-Based Router | — | FIRST+window | plain | **timeout-choice** |
| 6 | scanner silent → picker off, reassign | task | Content-Based Router | Aggregate (liveness) | — | breaker | **heartbeat (2nd)** |
| 7 | order cancelled → restock + release slot | cancel | — | Combine (restock) | — | plain | **cancel SAGA (multi-step)** |
| 8 | per-zone throughput limit | — | — | — | — | regulator | clean |

New here: **priority scheduling**, **loop/rework**, **multi-step compensation saga** (deeper
than encore's single release — restock N items AND release slot = a saga with several undo
legs). Mutual exclusion 2nd instance.

## TriageFlow (emergency department)

| # | behaviour | term | tmpl-M | tmpl-C | logic | kind | note |
|---|-----------|------|--------|--------|-------|------|------|
| 1 | triage → acuity; seen by acuity not arrival | patient (entity) | — | classify (ParDo) + **priority** | — | plain | **priority (2nd, non-commerce)** |
| 2 | room only if free AND clinician free; 1-at-a-time each | assignment | — | — | AND | regulator | **dual-resource mutual excl.** |
| 3 | treat only after triage+bed+consent | — | Aggregator | — | **AND + Milestone** | plain | **state-based enabling (WCP18)** |
| 4 | diagnosis combines multiple test results | diagnosis (VO) | Aggregator | Combine | **THRESHOLD/AND** | plain | fan-in |
| 5 | condition changes → re-triage, update priority | patient | — | — | — | plain | **loop + mutate queued priority** |
| 6 | no clinician in window → escalate attending | notification | Content-Based Router | — | FIRST+window | plain | **timeout-choice** |
| 7 | leaves without being seen → release resources | cancel | — | — | — | plain | **cancellation** |
| 8 | encounter tracked arrival→discharge | encounter (entity) | — | Aggregate | — | plain | long-running |

New here: **dual-resource mutual exclusion** (two shared resources acquired together — harder
than encore's single inventory), **Milestone / state-based enabling** (first proper WCP18
instance: a gate enabled only in a state), **dynamic priority mutation** (re-triage changes a
*queued* item's priority — the priority queue is mutable, which no compute pattern models).

## SurveyorSwarm (autonomous planetary survey) — also a CAP illustration

| # | behaviour | term | tmpl-M | tmpl-C | logic | kind | note |
|---|-----------|------|--------|--------|-------|------|------|
| 1 | divide sectors, assign to available drones | sector | Recipient List | — | — | plain | partition/assign |
| 2 | no overlapping sectors; deconflict paths | assignment | — | — | — | regulator | **spatial mutual excl. (3rd)** |
| 3 | autonomous map + stream observations | observation | Event Consumer | ParDo | — | plain | streaming producers |
| 4 | fuse heterogeneous sensors+methods → one obs | observation | — | **SENSOR FUSION** | — | plain | **NEW compute template** |
| 5 | combine map, proceed on sufficient fraction | map | Aggregator | — | **THRESHOLD = fault tolerance** | plain | **degraded completion; CAP: A over C** |
| 6 | reconcile duplicate landmark sightings | landmark | Aggregator | **ENTITY RESOLUTION** | — | plain | **NEW compute template** |
| 7 | silent drone lost → reassign sectors | sector | Content-Based Router | Aggregate (liveness) | — | breaker | heartbeat (3rd) |
| 8 | out-of-range → buffer, sync on reconnect | observation | — | — | — | plain | **BUFFERING (WCP24 gap, 1st hit); CAP: partition tolerance** |
| 9 | rank deposits by confidence, multi-sighting | deposit | Aggregator | Combine (confidence) | THRESHOLD | plain | fan-in |
| 10 | cross-check landmarks; conflicts → re-survey | landmark | — | — | — | plain | loop/rework |
| 11 | adaptive re-task: map → assignment | sector | — | — | — | plain | **FEEDBACK LOOP (output→input, new)** |
| 12 | transmit only at coverage+confidence threshold | map | — | — | — | plain | quality Milestone |

New here: **sensor fusion** (heterogeneous multi-source → one value; not Combine, which folds
same-type-per-key), **entity resolution** (decide two observations ARE the same landmark, then
merge; not dedup-by-key), **THRESHOLD as fault tolerance** (proceed without all inputs — the AP
choice), **buffering/store-and-forward** (first kata to exercise WCP24), **feedback loop**
(first closed loop; the map re-tasks the drones). **CAP framing:** #5 + #8 are availability +
partition tolerance chosen over strong consistency; #6/#10 are the eventual-consistency repair.

## AegisWatch (insider & intrusion detection) — also CAP-shaped

| # | behaviour | term | tmpl-M | tmpl-C | logic | kind | note |
|---|-----------|------|--------|--------|-------|------|------|
| 1 | assets valued; monitor by value | asset (entity) | — | **value-weighted priority** | — | plain | **priority (3rd, value-computed)** |
| 2 | agents assigned monitoring tasks | assignment | Recipient List | — | — | plain | assign |
| 3 | fuse several signal sources+methods → risk | risk_signal | — | **SENSOR FUSION** | — | plain | **new template (2nd domain — confirms)** |
| 4 | flag only if multiple signals corroborate | alert | — | **QUORUM / CONSENSUS** | THRESHOLD-ish | plain | **NEW: voting, absent from all corpora** |
| 5 | trusted insider deviates baseline → flag | user (entity) | — | Aggregate (baseline) + anomaly | — | plain | **Byzantine-trust; baseline anomaly** |
| 6 | correlate alerts for same incident → 1 case | case | Aggregator | **ENTITY RESOLUTION** | — | plain | **new template (2nd domain — confirms)** |
| 7 | confirmed compromise → isolate, cut access | — | — | — | — | **breaker (quarantine)** | cancel in-flight access |
| 8 | case not triaged in window → escalate lead | notification | Content-Based Router | — | FIRST+window | plain | timeout-choice (5th domain) |
| 9 | alert flood → shed low-value signals | — | Message Filter | — | — | **regulator (value-weighted shed)** | **load shedding** |
| 10 | agent stops reporting → reassign scope | assignment | Content-Based Router | Aggregate (liveness) | — | breaker | heartbeat (4th) |
| 11 | investigation tracked detection→resolution | case (entity) | — | Aggregate | — | plain | long-running |

New here: **quorum/consensus** (the primitive skipped on the drones, now unavoidable — a mole is
a trusted party, so corroboration-before-accusation is voting, not a threshold on one signal),
**value-weighted priority + load shedding** (priority/shedding driven by a *computed* asset
value), **breaker-as-quarantine** (isolate = cut access = a breaker trip used offensively).
Sensor fusion and entity resolution recur here (2nd domain each) — cross-domain confirmation.
**CAP-shaped:** distributed agents, partial info, act on partial corroboration = A over C.

## Granularity calls (batch 2, condensed)
- **UNIFY** where parts co-depend on one axis-role: dockyard #6 (liveness+reassign),
  triage #8 / aegis #11 (the long-running case IS one entity), surveyor #7.
- **SPLIT** where two independently-useful axis-roles are bundled: dockyard #7 (restock vs.
  slot-release are different domains → compensation fan-out), triage #2 (room-lock vs.
  clinician-lock are two resources → two mutual-excl. acquisitions, but must be atomic
  together — a *tension*: granularity says split, atomicity says one transaction; resolve by
  a single gate acquiring both, like encore's inventory_guard), aegis #7 (detect vs. isolate
  are separately useful — detection feeds cases without always isolating).
- **Established-practice override:** surveyor #5+#6 (Scatter-Gather + reconcile is one
  recognized fault-tolerant-aggregation idiom) — keep together, revisit in 2nd pass.
- **Tension noted (new):** triage #2 dual-resource lock is the first case where the
  granularity rule (split independently-useful) and a correctness rule (acquire-both-atomically
  to avoid deadlock/partial-hold) *disagree*. The correctness rule wins — same as encore's
  check+decrement. Pattern: **atomicity overrides the split rule**, just as established practice
  can. Worth adding to the granularity principle as a second explicit override.
