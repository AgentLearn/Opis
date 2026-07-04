# Domain→SA mapping: sentrygrid_monitoring (Phase-1, 4th kata — generality probe)

The first **non-commerce** kata (new, written for this test — industrial sensor monitoring,
no order/payment/inventory/loyalty). Purpose: does the SA taxonomy generalize, or is it
commerce-shaped? Mapped against 5-axis `sa_taxonomy_v1.json` with the granularity lens.

## The mapping

| # | kata behaviour | term | movement tmpl | compute tmpl | logic | kind | resolves? |
|---|----------------|------|---------------|--------------|-------|------|-----------|
| 1 | Sensors stream telemetry (id, timestamp) | telemetry_reading (event) | Event-driven Consumer (intake) | — | — | plain | clean |
| 2 | Aggregate per sensor over rolling windows → health metrics | health_metric (value object) | — | **windowed aggregate (Combine+Windowing, per sensor)** | — | plain | clean |
| 3 | Anomaly flagged only if threshold crossed sustained over a window (not a spike) | anomaly (event) | — | **windowed aggregate + threshold** | — | plain | clean |
| 4 | Suppress duplicate/flapping alerts per sensor within cooldown | alert | Message Filter (dedup) | — | — | **regulator** (per-sensor cooldown) | clean |
| 5 | Critical anomaly → on-call; if unacked in window → escalate to next tier | notification, ack | Content-Based Router (escalate) | — | **FIRST + window** (ack vs timeout) | plain | **friction: timeout-escalation** |
| 6 | Operators update thresholds / calibration independently | config_update | Content Filter (scoped write) | — | — | protected by sentinel | clean |
| 7 | Sensor silent for a period → mark offline, freeze last state | sensor_state (entity) | — | Aggregate (last-state) | — | **regulator/breaker** (staleness) | **friction: absence/timeout trigger** |
| 8 | Daily rollup: anomaly counts + uptime per zone | rollup (value object) | — | **Combine+Windowing (batch, per zone)** | — | plain | clean |

**6 of 8 resolve cleanly** — on a domain with zero commerce vocabulary. The taxonomy is
**not commerce-shaped**; the axes are domain-neutral. This is the key generality result.

## The two frictions are BOTH already-known gaps — and neither is commerce-specific
- **#5 timeout-escalation** = the same **FIRST + window + re-route** shape as ripple's
  timeout-reassignment (ripple #3). "Ack within window else escalate" ≡ "accept within
  window else reassign." The **deferred-choice-on-timeout** gap is domain-independent — it
  showed up in ride-hailing and now in monitoring. Strong signal it's a real missing
  primitive, not a commerce quirk.
- **#7 absence/timeout trigger** — "sensor stops reporting for a period → offline." This is
  triggering on the **ABSENCE** of input within a window. Neither WCP triggers (transient/
  persistent are about *presence*) nor Opis `input_timeout_ms` (a per-firing budget) models
  a standing "nothing arrived for T → fire" watchdog. **NEW gap surfaced only by the
  non-commerce kata:** a *dead-man's-switch / heartbeat-timeout* construct. Relates to WCP18
  Milestone (state-based enabling) but inverted (enabled by *inactivity*).

## What the generality probe confirmed
- **The computation axis is domain-neutral and central.** 5 of 8 behaviours (#2, #3, #7, #8,
  and #4's dedup) are computation/state, mostly **windowed aggregation** — the Dataflow
  half of the axis. Commerce katas leaned on movement (routing/joins); monitoring leans on
  computation. Adding the computation axis was not commerce-driven padding — it is what
  makes a *stream* domain expressible at all. Best justification yet for that axis.
- **Windowing is now grounded a THIRD time and exercised heavily** — here it is the core of
  the domain (rolling metrics, sustained-threshold, daily rollup), not an edge case.
- **Kind axis generalizes:** regulator (cooldown #4, staleness #7) and sentinel (#6) appear
  with no commerce meaning — throttling alerts, guarding config. The resilience grounding
  holds outside its origin domain.
- **Term axis generalizes:** entity (sensor_state — identity + lifecycle: reporting→offline)
  vs. value object (health_metric, rollup — computed) predicts statefulness exactly as in
  encore, with no commerce terms.

## Granularity calls (sentrygrid)
- **#2 + #3 SPLIT (established-practice/second-pass caveat).** Windowed metric computation
  (#2) and anomaly detection (#3) are adjacent, but the metrics are independently useful
  (dashboards, rollup #8 consume them without anomaly logic) → SPLIT: a `windowed_metric`
  gate feeding an `anomaly_detector`. Independent usefulness = split, textbook.
- **#4 UNIFY** — dedup-detection + cooldown-suppression are mutually dependent (the dedup
  *is* the cooldown) → one `alert_throttle` (regulator). 
- **#5 SPLIT** — escalation routing vs. the ack/timeout wait: the on-call routing is useful
  without tiered escalation; the timeout-escalation is the extra. But this needs the
  timeout primitive (friction) → revisit with the gap.
- **#7 UNIFY** — staleness-detection + freeze-last-state co-depend → one `sensor_watchdog`.

## Cross-kata synthesis update (now 4 katas, 3 commerce + 1 monitoring)
### Axis generality — CONFIRMED
Every axis was exercised by the non-commerce kata with no commerce vocabulary. The taxonomy
describes *how gates coordinate and compute*, independent of domain. Phase-1's central
hypothesis (a domain-neutral SA taxonomy that business terms map onto) holds across 4 domains.

### Domain shape shifts the axis MIX (a finding in itself)
- commerce (silicon/ripple/encore): movement-heavy (routing, joins, scatter-gather) + state
  for money/inventory/loyalty.
- monitoring (sentrygrid): computation-heavy (windowed aggregation dominates), movement thin.
The taxonomy's axes stay fixed; their *proportion* is a fingerprint of the domain. Useful:
the domain→SA mapping's axis histogram characterizes a domain.

### Gap list — now with a non-commerce entry
- **cancellation family** — ripple×2, encore. (commerce so far)
- **mutual exclusion / critical section** — encore. (commerce)
- **timeout deferred-choice** (reassign/escalate) — ripple AND sentrygrid. **Cross-domain** —
  promote priority; it is the most broadly-attested gap.
- **absence/heartbeat-timeout (dead-man's switch)** — sentrygrid. **NEW**, non-commerce-only.

### Candidate taxonomy v2 edits (updated)
1. Split `stateful reducer` → accumulate | enforce-invariant (ripple | encore).
2. Record kind ∘ computation ∘ timing composition (breaker/regulator trips = windowed
   reduction per entity) — now seen in ripple AND sentrygrid (#4, #7).
3. Add **mutual-exclusion / critical-section** construct.
4. Add **timeout deferred-choice** construct (cross-domain, highest evidence).
5. Add **absence/heartbeat-timeout** construct (new from monitoring).

## Next
1. Phase-1 breadth is now well-attested (4 domains, axes generalize, gap list stable and
   cross-validated). Reasonable to **declare breadth sufficient** and (a) fold v2 edits,
   (b) load taxonomy + 4 mappings into Neo4j so the synthesis becomes queryable.
2. Or one more contrasting domain (human-approval workflow) if you want a 5th data point on
   the deferred-choice / mutual-exclusion gaps specifically.
