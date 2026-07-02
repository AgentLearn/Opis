# GA — Gate Architect: implementation plan

The second and final agent loop (FA = topology loop; GA = contract loop; CA is
not a peer loop but the dev lead serving GA — flow-scoped, ephemeral outputs).
FA proved a flow's topology satisfies its requirements; GA proves each gate's
*internals* honor the timing and behavior the flow-level contract claims —
structurally (eval/proof) and dynamically (Monte Carlo twin + an optimization
loop over timing parameters). GA solely owns the gate library: it promotes and
demotes each contract's lifecycle `status` as evidence accumulates.

**Goal:** a committed flow is not just *correct* (requirements proved, contracts
honored) but *performant* — end-to-end deadlines met at p95 under realistic
latencies and load, bottlenecks identified, timing parameters defensible. Today a
flow can pass every structural check and still be unusably slow; GA closes that gap.

**Core premise (settled):** a gate's internals are a recursive pulse-network — the
same loci/synapses/gates schema as a flow. The gate's contract (frontmatter:
`input_slots`, `output_slots`, `window_ms`, `refractory_ms`) plays the role the
kata played for FA. opis-eval and opis-proof are reused, not rewritten.

---

## Phase 1 — Gate-internals schema

- `agents/gates/<name>/internals_v1.json`: same flow JSON schema, plus a
  `contract` header naming the parent gate.
- Binding convention: each `input_slot` becomes an internal source locus; each
  `output_slot` must be emitted by some internal gate reachable from those sources.
- Hand-write one golden example first — `payment_processor` (2-in / 2-out,
  exclusive outcomes, timing-rich) — before any agent touches it.

## Phase 2 — Verifier extensions (pure Python, regress-able)

Three new checks in `tools/opis-eval/`, reusing proof.py's AND-join fixed point:

1. **Contract conformance (inner):** every input_slot is consumed by some internal
   path; every output_slot has a real witness path from the inputs. The gate-level
   analog of requirement coverage.
2. **Outcome exclusivity:** for exclusive-outcome gates, prove no single pulse
   admission can reach two outcome emissions (structural mutual exclusion).
3. **Static timing budget:** critical-path sum of internal `window_ms` upper bounds
   along every witness path ≤ parent `window_ms`. Coarse, but catches impossible
   contracts before simulation.

Wire all three into `regress.py` so gate internals join the golden corpus.

## Phase 3 — Restore da-twin (MC timing validation)

`agents/crates/da-twin` exists (Rust, ~700 lines, event-driven MC over topo order)
but was never finished into the pipeline:

- **Compose step:** it consumes a `composed.json`; add a Python composer (or revive
  `da-core::compose`) that inlines a gate's internals into the parent flow so the
  twin sees one flat topology. Current `flow_vN.json` → composed spec.
- **Real distributions:** replace `uniform[refractory_ms, window_ms]` service times
  with per-synapse/per-gate latency distributions (lognormal default) drawn from
  the latency library (Phase 4).
- **Output contract:** `twin_report.json` — per gate: fire%, p50/p95/p99 vs its
  window (p95 ≤ window_ms or timing defect); per flow: end-to-end latency along
  each requirement's witness path, saturation under load sweep, bottleneck ranking
  (the sync-gate choke point OpisDescription predicts should fall out of this).
- **No timing requirements in katas** (explicitly decided): performance targets
  live in the gate contracts (`window_ms`, `refractory_ms`), not in kata text.
  End-to-end expectations instead come from **norms** — real-life expectation
  entries in the latency library ("payment confirmation: seconds, not minutes";
  "ride matching: tens of seconds"), sourced or LLM-estimated like any other
  entry. The twin annotates each requirement's witness path with its simulated
  end-to-end latency and flags paths **unusually slow against the applicable
  norm** — an advisory flag for the architect, not a hard failure. Norms are
  acknowledged to be rough; the value is surfacing outliers, not enforcing SLAs.
- Build constraint: cargo cannot build inside the synced folder — build from a
  copy in `/tmp` (sandbox) or locally.

## Phase 4 — Latency library (the "search the data" piece, finally implemented)

`agents/latencies/` — one file per medium/operation class (payment-provider call,
mobile RTT, geo-dispatch, db write...), frontmatter:

```yaml
name: payment_provider_response
distribution: lognormal
p50_ms: 300
p95_ms: 1800
source: web            # URL + date of the benchmark found
confidence: sourced    # sourced | llm-estimate (unverified)
```

Population order: GA web-searches published benchmark figures first; where nothing
credible is found, the LLM proposes an estimate explicitly tagged
`llm-estimate` — never silently mixed with sourced numbers. When CA later measures
real implementations in the co-sim twin, those numbers enter as *lower bounds*:
they falsify estimates confidently but validate only weakly (`measured` =
sandbox-measured, never production-validated).

## Phase 5 — RL timing-tuning loop

The twin is the environment; the policy tunes timing parameters.

- **State/action:** per-gate `window_ms`, `refractory_ms`, THRESHOLD counts.
- **Reward:** requirements' end-to-end deadlines met at p95, minus penalties for
  slack (over-wide windows) and starvation (fire% below threshold).
- **Start simple, honestly labeled:** cross-entropy / hill-climb over batched twin
  runs (thousands of runs are cheap in Rust) before any policy network. The
  interface is RL-shaped (state, action, reward, episodes) so a real policy can
  drop in later without rework.
- **Output:** proposed timing params + evidence (before/after fire%, p95 vs
  window), surfaced as an ADR-style proposal — the User accepts it and GA (sole
  contract owner) applies it; the tuner never silently rewrites a contract.
- **Role in the lifecycle:** the tuner is the *promotion mechanism* — its
  converged, re-verified params are what earn a contract `twin-validated`
  confidence. Proposals target gate *templates*; the katas are the blank-slate
  falsification harness a proposal must survive (all flows using the template
  stay green).

## Phase 6 — GA agent

Copy-adapt FA's run loop first (unify into a shared core only once both loops'
needs are known): iterate against a scratch internals file → opis-eval →
contract-proof → twin timing pass → commit `internals_vN.json`. Same three-layer
defect feedback (error_history, persisted defect history, recurrence ADR nudge).

---

## Order & first milestone

1 → 2 land together (schema + checks + golden payment_processor internals,
verified by regress). 3 next; 4 feeds 3. 5 only once the twin is trusted. 6 wraps.

**First milestone:** hand-written `payment_processor/internals_v1.json` passing
all three Phase-2 checks under regress.py — no agent, no Rust, no LLM in the
verification path. Same discipline as FA: build the verifier before the generator.
