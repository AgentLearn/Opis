# Opis — system outline

Design decisions → the specification language → the moving parts → a tour of the
silicon specimen. Companion to [FLOW_LIFECYCLE_GUIDE.md](FLOW_LIFECYCLE_GUIDE.md)
(which covers the *process*; this covers the *system*). Canonical source:
[OpisDescription.md](OpisDescription.md). Links relative to repo root.

---

## 1. Design decisions (the load-bearing ones, in dependency order)

**D1 — We build agents and verifiers, never artifacts.** Value lives in the
process; every gate, flow, and taxonomy must be regenerable from a kata. The
2026-07-02 blank-slate reset (delete all 14 gates, re-derive from katas alone)
was this principle enforced. Hand-built work survives only as golden recipes.

**D2 — Dynamic Architecture: topology is the output.** Static architecture
describes what you built; Opis describes what the system *becomes*. Gates that
never fire get pruned; recurring coincidence patterns crystallise into new
archetypes. Structural plasticity, not parameter tuning
([OpisDescription.md](OpisDescription.md) §The core insight).

**D3 — Neuromorphic, not ECS.** No main loop imposing total order. Gates fire
when charge accumulates (integrate → threshold → spike → refractory), a partial
order matching a concurrent world. Petri net + SNN timing + ontology.

**D4 — Nodes are topology, not data; pulses carry everything.** Loci and
archetypes hold no properties. Payload lives on the pulse. Corollary (the
ontology rule, verbatim in FA's prompt): *things that act are loci; facts that
travel are terms; matter never flows — only descriptions of it.*

**D5 — Security is structural.** AuthN/AuthZ = sentinel gates wired as upstream
`requires` of protected gates, not code paths. Falsifiable: tamper runs must
visibly change behavior or the auth isn't real (proven in v4: 1000/1000 denials).

**D6 — Proofs, not prose.** A requirement is `{gate, outcome}` target; coverage
is an AND-join fixed-point reachability proof with witness paths. FA's own
report is never trusted — everything re-verifiable by running the verifiers.
Polarity matters: a bootstrap deadlock (force-fired cycle) is a *disproof*.

**D7 — Falsification is the product.** CA's translation step (contracts → typed
schemas → real code) exists to falsify gate contracts *before* code. All 5
silicon falsification classes (hollow wiring, prose-exceeds-slots ×3,
self-attestation, silent rejection, bootstrap deadlock) fed back as ADRs or new
static checks. Failures displayed as proudly as proofs.

**D8 — ADRs are the only decision channel.** FA proposes with genuine options;
you decide (`adr.py` CLI or terse user directives); decisions are binding
context injected into every subsequent LLM call, forever — rejections included.
Two classes: FA-proposed (full format) vs user directive (one-liner, binding).

**D9 — Append-only versioning + pins.** A committed flow pins exact gate
contract versions + hashes + taxonomy. Amendments archive the old contract
verbatim and bump `version:`; old pins stay valid forever; upgrade = explicit
re-prove → new flow version. No silent drift, ever.

**D10 — Evidence with a claim grammar.** `{claim, verdict, evidence-pointer,
scope}`; verdicts `proved|passed|bounded|flagged|failed`; no assertion without
a pointer; dynamic (sandbox) evidence caps at `bounded` — falsify confidently,
validate weakly.

**D11 — Two-repo split.** Product repo (agents, verifiers, gate library,
katas) vs [workspace/](workspace/) (agents' own git repo: flows, ADRs, logs,
defect histories). CA outputs are ephemeral except evidence.

**D12 — wasm-first execution.** CA-generated code runs as wasm32-wasip1 under
wasmtime: capability denial by construction, no containers.
[dep_check.py](tools/opis-eval/dep_check.py) closes the compile-time hole.

**D13 — Katas are the tests.** Requirements-only prose briefs
([agents/katas/](agents/katas/), 12 of them) are the falsification harness for
the whole machine. Timing lives in gate contracts + latency norms (advisory),
never in katas.

**D14 — Environments are documents, not decisions.** Infra is descriptive fact
files ([agents/environments/](agents/environments/)); flows stay infra-blind;
one flow × N environments = N translations. Env-can't-carry-contract is a
falsification class.

---

## 2. The specification language ([OpisDescription.md](OpisDescription.md) §Opis)

A system = pulse network: **loci** connected by **synapses**, data traveling as
typed, timestamped **pulses**.

### Node kinds

| Kind | Role |
|---|---|
| `locus` | Persistent actor/place; routes pulses. `source: true` = external world injection point (only source loci *originate*; plain loci only route) |
| `archetype` | Type declaration; IS-A DAG via `extends`; never a graph node |
| `gate` | Operator: fires on coincidence, emits one outcome bundle |
| `sentinel` | Gate specialization: AuthN/AuthZ, upstream `requires` of protected gates |
| `regulator` | Gate specialization: rate limiter / breaker (`trips_on`, `recovery_ms`) |

### Signals & edges

`pulse` (typed, ephemeral, carries payload) → accumulates as `charge` in a
gate's `window_ms` → `spike` on threshold, then `refractory_ms`. Edges:
`synapse` (`from → to`, one `pulse_type`, `medium` latency preset or explicit
p50/p99, `interaction: push|pull`) and `inhibitor` (arrival suppresses firing).

### Gate anatomy (flow-spec JSON, the shape FA emits)

```json
"PaymentAuthorizer": {
  "gate_template": "payment_authorizer",     // claims a library contract
  "kind": "regulator",                       // gate | sentinel | regulator | breaker
  "requires": ["payment_request"],           // input slot types (subtype-aware)
  "optional": ["loyalty_reward"],
  "logic": {"op": "AND"},                    // AND | OR | FIRST | THRESHOLD{n}
  "emits": [{"outcome": "confirmed", "flows": ["payment_confirmation"]},
            {"outcome": "failed",    "flows": ["payment_failure"]}],
  "window_ms": 10000, "input_timeout_ms": 2000,
  "auth_required": false
}
```

Logic = the join semantics (AND = all requires, OR/FIRST = earliest,
THRESHOLD = n-th earliest); the ontology pass confirmed this is a faithful
subset of the van der Aalst control-flow canon, and Opis's timing constructs
(windows, refractory, probabilistic outcomes, breakers) are orthogonal
additions the untimed literature lacks ([ontology/](ontology/)).

Other constructs: `cardinality` (per_instance vs shared loci — shared = scaling
ceilings), `topology_groups` (zoom levels; role-based slots, slot-isolation
rule), sync gates for consistency, no-pass-through semantics (gates forward
only what they emit).

### Two vocabularies, bridged per kata

1. **Slot types** ([agents/slot_types/](agents/slot_types/)) — the computing
   base ontology (query, command, event, ack, location, ...).
2. **Gate contracts** ([agents/gates/](agents/gates/), 15 contracts) — .md
   files with frontmatter: `version`, typed input/output slots,
   `status: draft|specified|simulated|measured`,
   `confidence: llm-estimate|twin-validated|sourced`. The library is
   append-only-versioned; the index is derived, never hand-written.
3. **Per-kata taxonomy** — the binding bridge: domain term → `extends`
   slot-type, with kata-phrase provenance. Flows may only speak taxonomy terms.

### Requirements

```json
{"id": "REQ-1", "text": "...", "target": {"gate": "PaymentAuthorizer", "outcome": "confirmed"}}
```

Provable by construction: the target gate must have witness paths for its full
required-input bundle.

---

## 3. The moving parts

| Part | What it owns |
|---|---|
| **FA** ([agents/fa/](agents/fa/)) | kata → taxonomy → flow iterations → ADR proposals → committed, pinned, proved flows. Fable-5 for design, Sonnet-5 for transcription |
| **You (via ADRs)** | every contract decision; the only non-agent in the loop |
| **CA** ([agents/ca/](agents/ca/)) | dev-lead role: contracts → schemas → real Rust/wasm gates → harness → co-sim → tamper. Translation failure = falsified contract |
| **Static verifiers** ([tools/opis-eval/](tools/opis-eval/)) | eval (14 structural checks), proof (coverage+conformance), contract_lint (advisory), schema_check, dep_check, pins, evidence, regress |
| **da-twin** ([agents/crates/da-twin/](agents/crates/da-twin/)) | the Monte Carlo: virtual clock, logic-aware joins, lognormal latencies, progressive substitution, forge-on-the-wire tamper |
| **Workspace** ([workspace/](workspace/)) | agents' own repo: flows, ADR registers, defect histories, evidence, CA ephemerals |

(GA as a peer agent loop was ruled OFF 2026-07-04 — evidence consumers are you,
via the same ADR channel. gate_proof.py survives as a verifier for gate
internals.)

---

## 4. Tour of the specimen — silicon_sandwiches v4

Kata: [agents/input/silicon_sandwiches.md](agents/input/silicon_sandwiches.md)
(franchise sandwich ordering: orders, payment+loyalty, pickup estimates,
delivery routing, kitchen submission, driver tracking, owner menu updates).
Flow: [flow_v4.json](workspace/silicon_sandwiches/flow/flow_v4.json) — 6 source
loci, 14 gates (11 templates), 40 synapses, 22 archetypes, 8 requirements.

### The cast

Source loci = the world: Customer, PaymentProcessor, Kitchen, MappingProvider,
Driver, FranchiseOwner. Gates = the system (every one gets real code in co-sim).

### Thread 1 — order & payment (REQ-1, REQ-2)

```
Customer ─customer_order→ OrderValidator ─validated_order→ KitchenDispatcher
                              └─invalid_order→ Customer
Customer ─payment_request→ PaymentProcessor → PaymentAuthorizer (regulator)
LoyaltyAccumulator ─loyalty_reward→ PaymentAuthorizer   (optional input)
PaymentAuthorizer ─confirmed→ payment_confirmation → Customer
```

### Thread 2 — the pull idiom made honest (REQ-3; ADRs 010/012)

```
Customer ─queue_length_query→ KitchenQueueResolver (provider_query_resolver)
KitchenQueueResolver ─queue_length_response→ QueueEstimator ─estimate→ Customer
```

The original `queue_based_estimator` internalized its pull ("pulls queue depth
from the stateful locus") — CA falsification #1. The fix (ADR-012): estimator
*consumes* a response; the boundary pull lives in a dedicated resolver instance.
This resolver pattern repeats 4× in the flow (queue + 2 map resolvers + kitchen).

### Thread 3 — routing fan-in and the deadlock that died (REQ-4/5)

```
Customer ─directions_request→ RoutingAggregator → MappingProvider
MappingProvider → MapResolverA ┐
MappingProvider → MapResolverB ┴─delivery_directions_response→ RoutingAggregator
RoutingAggregator ─delivery_routing_decision→ KitchenDispatcher ─command→ Kitchen
```

v3 wired the resolvers' query source from RoutingAggregator's own fan-out —
bootstrap deadlock (nobody can go first); proof.py force-fired 5/8 requirements,
twin showed 0%. Now the query originates at Customer, and fallback = disproof.

### Thread 4 — ack supervision (REQ-5/6; ADRs 011/014/016)

```
KitchenDispatcher ─command→ KitchenCompletionRecorder ←kitchen_order_ack─ Kitchen
KitchenDispatcher ─command→ DriverCompletionRecorder  ←driver_dispatch_ack─ Driver
recorders ─loyalty_point_event→ LoyaltyAccumulator ; ─notification→ Customer
Driver ─driver_position→ DriverTracker ─tracking_update→ Customer  (position optional, ADR-015)
```

The dispatcher was demoted to pure join-and-dispatch (ADR-014: its ack logic
duplicated the recorder's); the recorder's own ack input only became real in
ADR-016 (prose-exceeds-slots caught *statically* by contract_lint, no CA needed).

### Thread 5 — structural auth (REQ-7; ADRs 017/019)

```
FranchiseOwner ─auth_request→ MenuAuthSentinel (claims_issuing_sentinel)
MenuAuthSentinel ─auth_token→ MenuWriter (auth_required: true)
FranchiseOwner ─menu_update→ MenuWriter ─event→ Kitchen
```

Sentinel embeds signed short-TTL scope claims (HMAC over
`principal|scope|expires_ms`); MenuWriter verifies locally. Replaced v1's
resolvers-bound-to-FranchiseOwner (self-attestation falsification: the subject
vouched for itself). v3's version verified correctly but had no rejection
outcome — silent-rejection class; v4 rejects visibly, which is what the tamper
run measures.

### The verdict

[evidence_v4.md](workspace/silicon_sandwiches/flow/evidence_v4.md): **proved
(static) / bounded (dynamic)** — 8/8 requirements with witness paths, zero
fallbacks, conformant, pinned; co-sim 14/14 real gates alive; forge-on-the-wire
tamper → 1000/1000 denials, outcome Δ3000. Cost of getting here: 22 ADRs, 5
falsification classes, ~6 agent bugs found and fixed — all of which is the
point (D1: the machine, not the artifact, is the product). The before/after
experiment ([experiments/silicon_results_v1.md](experiments/silicon_results_v1.md))
scores this against three unaided baseline builds.
