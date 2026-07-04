# Opis, a Dynamic Architecture System

**Opis** is a framework that allows Stakeholders, Domain Experts and Software Architects to describe any system guided by data and control flows as a dynamic network. The purpose of this description is to start with a set of requirements in terms of some knowledge domain and creates a network and flows through it that satisfy functional and nonfunctional requirements expressed in terms of the same domain taxonomy. We refer to the described system as System and the knowledge or business domain as Domain.

## Taxonomies

### Kata

We stole the notion of a training problems from the software architecture to represent a requirements for the system. What distinguishes an architectural kata from a usual requirements for a system is that a kata is software infrastructure agnostic, which is what Opis requires as its input.

### Domain Representation

Opis builds a minimal Domain taxonomy required to define all the entity needed to describe the System. This information needs to be specific enough for an coding agent to create the actual system's software.

### Gates

All Opis operators are represented as _gates_.  A gate has input and output flows and in the Opis it has two level of details. The top level is called *flow* and inputs and outputs of a gate are expressed in the terms of the Domain.

The detail level is defined in a terms of a computing domain. For example, an order processing gate will call one of it input streams "orders", while in the domain specific flow, say a sandwich shop, the same input could be referred as "sandwich_order" and had a type of "order" so that the architect can correctly choose a gate that processes orders.



## Properties of Opis

1. **Complete**: all the entities and operations of the System are represented.
2. **Implementation Agnostic**: Opis network describes system only in terms of the Domain and data flow abstractions.


## Agents

Opis is built by a hierarchy of three agents. Each agent iterates at its own level until all problems are resolved, then descends to the next level. If a problem is unsolvable at the current level, the agent escalates to the agent above it with a structured interface describing what is missing. If a decision requires a trade-off or has competing approaches, the agent creates an ADR with multiple proposals for the User to approve.

All three agents produce ADRs. The User is the final authority on decisions.

### Two Vocabularies

Opis operates with two distinct type vocabularies that must never be mixed:

**Slot types** — computing-level action types defined by the gates layer. Examples: `order`, `payment`, `auth_request`, `notification`. These describe what a gate does in computing terms. Slot types form their own IS-A hierarchy (e.g. `accepted_order` IS-A `order`).

**Domain terms** — kata-specific concepts defined by the Domain. Examples: `sandwich_order`, `online_payment`, `customer_alert`. Domain terms extend slot types: `sandwich_order` IS-A `order`. This is the bridge between domain language and computing language.

The flow's spike trains carry domain-typed pulses. Gates speak slot types. FA resolves the mapping by walking the archetype DAG upward from the domain term to its slot type, then selecting the gate whose input slot matches.

### Gates Repository

The gates repository is a library of computing-level gate templates. Each gate is a structured Markdown file with YAML frontmatter defining its slots (typed connection points) and defaults, and a prose body explaining its behavior. An `index.md` lists all available gates.

The repository starts empty. FA proposes new gates as it encounters slot types that no existing gate covers. Every proposed gate requires User approval before it is added to the repository and before FA can use it in a flow.

**Gate lifecycle and provenance.** A gate entering the repository this way is a *draft*, not an authoritative primitive — FA's mid-run `gate_needed` ADR is a trigger, deliberately weak evidence that is never traced as the contract's justification. Each gate's frontmatter carries a lifecycle `status` (`draft` → `specified` → `simulated` → `measured`) and a `confidence` tag (`llm-estimate` | `twin-validated` | `sourced`). Contracts are promoted only with evidence: grounding in real-life architectures or high-quality sandboxed twin runs. Refinement is iterative — ADR → specs → implementation — and evidence from any stage can demote the stage above it. Building good gate descriptions and the process that refines them is a core, open research thread of Opis.

**Gates are kata-agnostic.** A gate file contains no domain-specific concepts — no mention of the kata, the domain name, or any domain entity. A `payment_processor` gate processes any payment from any domain. Domain meaning lives in the flow spec (archetypes), not in the gate definition. This is what makes gates reusable across katas.

If multiple candidate gates exist for a slot type, FA creates an ADR listing each option for the User to approve before proceeding.

ADR options are genuine design alternatives — exactly as many as credibly exist. One option is legitimate when no credible alternative does (the ADR must say why); invented filler options are forbidden — they waste the architect's review and hide the real decision. Every ADR leaves space for the architect to add their own option before deciding.

**Gate file format** — structured Markdown with YAML frontmatter:

```markdown
---
name: order_processor
input_slots:
  - name: order
    type: order
    required: true
output_slots:
  - name: accepted_order
    type: accepted_order
  - name: rejected_order
    type: rejected_order
window_ms: 5000
refractory_ms: 500
auth_required: false
medium: lan
---

Receives an order flow, validates it, and emits accepted or rejected.
When wired into a flow, slot types map to domain archetypes by IS-A resolution.
```

### Slot Types

Slot types are the computing-level type vocabulary of the gates layer. They live in a single `slot_types/index.md` — one file, no individual files — so FA loads the full type hierarchy in one read with minimal context cost.

```markdown
| type             | extends | description                              |
|------------------|---------|------------------------------------------|
| order            | —       | a request to process or fulfill          |
| accepted_order   | order   | an order that passed validation          |
| rejected_order   | order   | an order that failed validation          |
| payment          | —       | a financial transaction request          |
| payment_confirmed| payment | a payment that was authorized            |
| payment_failed   | payment | a payment that was declined              |
| auth_request     | —       | an authentication or authorization check |
| auth_token       | —       | a credential granting access             |
| notification     | —       | an outbound message to an actor          |
```

New slot types are proposed by FA alongside new gate proposals, and require User approval.

### Sentinels

A sentinel is an authZ enforcement gate. Any gate whose slot type requires authorization must have a sentinel as an upstream `requires` in the flow. FA is responsible for placing sentinels — opis-eval errors if a protected gate has no sentinel upstream. Sentinels are defined in the gates repository like any other gate.

### FA — Flow Architect

FA takes a kata and produces the versioned flow spec: loci, synapses, and gate selections drawn from the gates repository. Gates are matched by resolving domain terms up the archetype DAG to their slot type, then finding the gate in the repository whose input slot matches.

If a required gate does not exist, FA proposes it (with slot type definitions) and waits for User approval before continuing. If multiple candidate gates exist, FA creates an ADR. FA places sentinels on all protected gates.

FA iterates, producing a new versioned flow spec (`flow_vN.json`) each pass, until the flow is structurally complete and passes opis-eval with zero errors. The domain taxonomy (archetypes and their slot type mappings) lives inside `flow_vN.json` — it is not a separate file. FA also proposes tests for its own output and for all agents below it in the hierarchy (GA, CA).

### GA — Gate Architect

GA is the contract loop — the loop that tightens the Opis description itself. GA solely owns the gate library: every contract has exactly one owner. GA takes each gate selected by FA, designs and verifies its internals, and runs Monte Carlo simulations (the twin) to produce probability distributions (PDs) for gate behavior — latency, throughput, failure rates. GA promotes or demotes each contract's lifecycle `status` as evidence accumulates. When CA has produced sandbox measurements, GA weighs those measured PDs against the simulated ones.

GA iterates until all gates are fully parameterized and their PDs are within the bounds required by the flow. GA proposes tests for its own output and for CA runs.

GA's ADR context excludes gate-needed ADRs (the `NNN_gate_needed_*.md` proposals already resolved at the flow level) regardless of who raised them. All other ADRs — from FA or directly from the User — are in scope for GA.

### CA — Coding Agent (Dev Lead)

CA is not a peer loop — it is the dev lead serving GA, and its unit of work is a **flow**, not a gate. Measured behavior is a reaction of the whole software system: per-gate PDs don't compose by formula, because one gate's decision logic changes every distribution downstream of it. Testing a gate in isolation is therefore of limited use; the proof of an Opis flow is the full implementation running in the co-simulation twin.

CA's task, per flow:

1. **Translate** gates + ADRs into shared message schemas — one schema per archetype, subtype-extends-parent, both synapse endpoints agree. A contract that cannot be translated into usable messages is falsified before any code runs.
2. **Implement** each gate in Rust against those schemas (gates are the computational path; agents stay Python).
3. **Emulate** non-software subsystems (kitchens, drivers, customers, external services) statistically — payload generators producing schema-conformant content with latency-library timing.
4. **Run** the flow in the one co-sim twin environment with progressive substitution: real gate code plugged in place of simulated stand-ins (subprocess, JSON over stdio; the twin keeps the virtual clock, sends inputs at fire time, receives the actual outcome + payloads + measured service time, and propagates the real decision instead of a sampled one).

Sandbox measurements falsify contracts confidently but validate them only weakly — `measured` status means sandbox-measured lower bounds, never production validation.

### Iteration Loop

```
Kata
  │
  ▼
FA  ──iterates──► flow clean?  ──yes──► GA ──iterates──► gates clean?
  ▲                                    ▲ │
  │                            evidence│ │contract
  │                             (PDs,  │ │
  │                          bounds,   │ ▼
  │                        infeasible) CA (schemas → Rust gates → co-sim runs)
  │                                      │
  │◄── unsolvable / contract demoted ◄───┘
```

GA drives; CA is engaged per flow and reports back. Evidence that falsifies a contract demotes the gate, which invalidates flows relying on it — the signal propagates up to FA, which re-designs.

When any agent cannot resolve a problem: it notifies the agent above with a structured description of what is missing. When any agent faces a decision: it creates an ADR with proposals and waits for User approval before continuing.

**Trigger:** command line for now; the UI (designed in Opis — dogfood) when ready.

## UI

The user-facing editor is designed using Opis itself. Users interact with their own context through it — browsing the flow, reviewing gate parameters, approving ADRs. Designing the UI in Opis is the primary dogfood exercise.


---

## The core insight

Static architecture describes what you built. Dynamic Architecture describes what the system *becomes*.

- A gate that never fires gets pruned.
- A bottleneck gate sprouts a parallel path.
- A recurring coincidence pattern crystallises into a new archetype in the gates repository.
- Topology is the *output* of running the system, not just the input.

This is structural plasticity, not parameter tuning. Nature grows neurons; SGD adjusts scalars.

**Not TSP.** TSP finds the optimal route through fixed nodes. Dynamic Architecture changes the nodes themselves.

---

## Opis — the specification language

Opis models any dynamic system as a pulse network: nodes connected by synapses, data travelling as typed, timestamped pulses.

### Nodes

| Kind | Role |
|------|------|
| `locus` | Persistent element (service, warehouse, device, role). Routes pulses through. Optional `source: true` marks external actors/APIs/sensors that inject pulses from the real world. |
| `archetype` | Type declaration. Defines the schema of one concept. Forms an IS-A DAG via `extends`. Not a graph node — never appears as `from`/`to` in synapses. |
| `gate` | Operator. Fires (spikes) when coincidence threshold is met; emits one outcome bundle. Parameters: `requires`, `count`, `correlation_key`, `correlated`, `window_ms`, `refractory_ms`, `emits`. |
| `sentinel` | Special gate: AuthN/AuthZ. Must fire as upstream `requires` for any protected gate. |
| `regulator` | Special gate: rate limiter / circuit breaker. |

### Cardinality

A locus may declare a `cardinality` block to express that N instances run in parallel and to name which sub-loci are replicated vs. shared:

```json
"shop_location": {
  "cardinality": {
    "count": 10,
    "per_instance": ["local_queue", "local_inventory"],
    "shared":       ["payment_gateway", "national_menu"]
  }
}
```

`per_instance` loci are multiplied N times — no cross-instance contention. `shared` loci are held once across all instances — they are scaling ceilings. Throughput of N instances is bounded by the shared loci, not by N × single-instance capacity. opis-eval (check 8) flags each shared locus as a bottleneck and errors on per_instance/shared overlap.

### Topology groups (zoom levels)

A `topology_group` unfolds a locus into its internal slot structure without changing the locus's external interface. The top-level view treats the locus as opaque; the detail view exposes concurrent processing slots.

```json
"topology_groups": {
  "shop_detail": {
    "slots":       ["slot_active", "slot_stalled", "slot_next"],
    "shared_loci": ["prep_station"],
    "loci":   { ... },
    "gates":  { ... },
    "synapses": [ ... ]
  }
}
```

**Slots** are role-based, not ID-based. Items (orders, drivers) flow *through* roles — slot_active holds whatever is currently being processed. Identity is the slot, not the item. Slot count = max concurrency, declared statically.

**Slot isolation rule:** no direct synapse between two slots is permitted; all transitions must go through a gate. opis-eval (check 9) enforces this and warns when a locus is reachable from multiple slots without being declared in `shared_loci`.

A locus opts into a group with `"detail": "group_name"` — opis-eval errors if the group doesn't exist.

### Signals

| Term | Meaning |
|------|---------|
| `pulse` | Typed, timestamped, ephemeral. Carries payload. Travels synapses. |
| `charge` | Pulses accumulated in a gate's integration window (not yet fired). |
| `spike` | Firing event: threshold met, charge clears, downstream pulses emitted. |

### Edges

| Term | Meaning |
|------|---------|
| `synapse` | Directed signal route (`from → to`). Optional pulse type filter, latency parameters, and `medium` preset. |
| `inhibitor` | Suppressing synapse: arrival prevents gate from firing, clears charge. |

### Synapse latency — `medium` presets

Synapses carry pulses with log-normal latency. Declare latency with `medium` (a named preset) or explicit `p50_ms`/`p99_ms`. Explicit values take priority over `medium`.

| `medium` | p50 (ms) | p99 (ms) | Use for |
|----------|----------|----------|---------|
| `"local"` | 0.1 | 1 | Same-process / shared memory |
| `"lan"` | 0.5 | 5 | Same datacenter / local network |
| `"internet"` | 80 | 600 | Public internet API calls |
| `"satellite"` | 500 | 2000 | Satellite links |
| *(none)* | 1 | 10 | Default intra-service |

```json
{"from": "PaymentGate", "to": "StripeAPI",   "pulse_type": "ChargeRequest", "medium": "internet"},
{"from": "OrderGate",   "to": "LocalCache",   "pulse_type": "CacheWrite",    "medium": "local"},
{"from": "Warehouse",   "to": "Driver",        "pulse_type": "PickupReady",   "medium": "lan"}
```

**Auto-inference:** any synapse whose destination is a `source: true` locus automatically gets `medium: "internet"` unless overridden. External actors live outside the system — crossing that boundary always has internet-class latency unless you know better.

---

### Consistency — sync gates

Consistency is **structural**, not annotated. A `kind: "sync"` gate is an explicit synchronization point: it gathers from all N upstream sources and fans out a consistent snapshot. The gate has cardinality 1 — one convergence point for all N feeds.

```json
"InventoryCoordinator": {
  "description": "gathers stock updates from all 3 warehouses",
  "kind": "sync",
  "requires": ["StockUpdate"],
  "count": { "StockUpdate": 3 },
  "window_ms": 200,
  "emits": [{ "outcome": "synced", "flows": ["ConsistentStockView"] }]
}
```

Everything downstream of `InventoryCoordinator` sees a consistent snapshot. Between sync gate firings — eventual.

**Patterns:**

- **N warehouses, each shop binds to one** — correlation_key creates exclusive groups; each warehouse is its own sync point for its group. Strong consistency per group.
- **N warehouses, any shop uses any** + sync gate gathering from all N — one global sync point. Strong globally.
- **N warehouses, any shop uses any**, no sync gate — eventual. opis-eval (check 12) flags this.

**The sync gate is also the choke point.** It will show the highest p99 in the twin — all N feeds must arrive within `window_ms`. That's intentional architecture. The twin flags it as a bottleneck so the architect decides: shard it (per-group sync) or widen the window.

opis-eval check 12 verifies `count` matches upstream cardinality. If a 3-warehouse system declares `count: {StockUpdate: 1}`, it's not actually gathering from all warehouses — flagged as a warning.

---

### Source loci (external injection points)

A locus declared `source: true` represents something in the real world that initiates events autonomously — a human actor, an external API, a sensor, a physical device. Source loci can emit any pulse type regardless of what arrives on their incoming synapses. They are the boundary between the model and the outside world.

```json
"Customer":          { "description": "End user placing orders", "source": true },
"Driver":            { "description": "Delivery driver",         "source": true },
"GoogleMapsProvider":{ "description": "External mapping API",    "source": true }
```

This is a semantic declaration, not a topological one. A source locus often has BOTH incoming edges (feedback from the system: order status, ETA updates) AND outgoing edges (new requests it originates). The `source: true` field tells opis-eval to treat its outgoing types as externally injected regardless of what arrives on its inputs.

Internal services that only process what the graph feeds them must NOT be declared `source: true` — if they transform types, they must be gates.

### Type hierarchy (IS-A DAG)

Archetypes form a shallow DAG via `extends`. A `sandwich` IS-A `food` IS-A `consumable`. A gate requiring `food` accepts any subtype — `sandwich`, `pizza`, `salad`. opis-eval (check 1) resolves subtype satisfaction automatically.

```json
"archetypes": {
  "consumable": { "description": "anything perishable" },
  "food":       { "description": "edible consumable", "extends": "consumable" },
  "sandwich":   { "description": "a sandwich order",  "extends": "food" }
}
```

Archetypes are type labels on pulses, not graph nodes. They appear only in `pulse_type`/`pulse_types` fields on synapses and in `requires`/`emits` on gates.

---

### Two levels of detail

Opis specs are authored at two levels:

**Flow level** — the happy path. Source loci, main gates, outcome exits named but not expanded. Human-readable in one glance. Inconsistencies at this level are structural (dead gates, unreachable types). opis-eval checks 1–12 operate here.

**Mechanism level** — zoom into a gate. Declared in a `mechanism` block on the gate, keyed by outcome name. Shows:
- The conditional downstream sub-topology for each outcome
- Whether each input is pushed (upstream decides when) or pulled (gate initiates query, synapse carries response)
- Round-trip synapses for pull interactions

```json
"PaymentGate": {
  "requires": ["OrderRequest", "PaymentDetails"],
  "emits": [
    {"outcome": "credit_approved", "flows": ["PaymentConfirmed"]},
    {"outcome": "credit_declined", "flows": ["PaymentFailed"]}
  ],
  "mechanism": {
    "credit_approved": {
      "description": "kitchen receives order, loyalty triggered, customer notified",
      "loci":     { "LoyaltyStore": {} },
      "gates":    { "KitchenDispatch": { "requires": ["PaymentConfirmed"], "emits": [{"outcome": "dispatched", "flows": ["KitchenOrder"]}] } },
      "synapses": [
        {"from": "PaymentGate",    "to": "KitchenDispatch", "pulse_type": "PaymentConfirmed", "interaction": "push"},
        {"from": "KitchenDispatch","to": "LoyaltyStore",    "pulse_type": "KitchenOrder",     "interaction": "push"}
      ]
    },
    "credit_declined": {
      "description": "order cancelled, customer notified, nothing reaches kitchen",
      "loci":     {},
      "gates":    {},
      "synapses": [
        {"from": "PaymentGate", "to": "Customer", "pulse_type": "PaymentFailed", "interaction": "push"}
      ]
    }
  }
}
```

**`interaction`** on a synapse:
- `"push"` — upstream decides when to send. Event-driven. Gate accumulates and fires when its window closes.
- `"pull"` — gate initiates a query; this synapse carries the response back. Implies a round-trip: an outbound query synapse must exist in the main topology.

opis-eval check 13 warns when a gate has multiple outcomes but no mechanism declared, and errors when a mechanism references an outcome not in `emits`.

**Rule of thumb:** if a human reading the spec would assume the downstream flow as obvious, leave it implicit. If an inconsistency can hide there (order confirmed before payment authorised), declare the mechanism.

---

### Flows

A **flow** is one typed thing travelling the network — a `sandwich_order`, a `payment_request`, a `driver_assignment`. It is not a tag set. A `sandwich_order` is a single concept, not `["sandwich", "order"]`.

Flows are typed by their archetype. The archetype hierarchy applies: a locus or gate that handles `food` handles any `food` subtype automatically.

---

### Gate as operator (outcome algebra)

A gate is an **operator**: it consumes its input flows and emits a bundle of output flows. Opis declares the possible outcome space; the implementation decides which outcome fires. Exactly one outcome fires per spike.

```json
"PaymentGate": {
  "requires": ["OrderRequest", "PaymentDetails"],
  "window_ms": 5000,
  "emits": [
    { "outcome": "payment_ok",     "flows": ["PaymentConfirmed", "LoyaltyTrigger"] },
    { "outcome": "payment_failed", "flows": ["PaymentFailed",    "CustomerAlert"]  },
    { "outcome": "order_invalid",  "flows": ["OrderInvalid"]                       }
  ]
}
```

Each outcome is a **bundle** — one or more flows emitted simultaneously. Downstream topology routes each flow type via synapses with `pulse_type` filters. opis-eval (check 10) errors if any flow in any outcome has no consuming synapse.

Value predicates (e.g. `threat_score < threshold`) are not encoded in the gate — they are evaluated by an upstream locus that emits a typed result pulse (`ThreatClear`). The gate requires `ThreatClear`, not a raw numeric score. This keeps Opis a wiring language, not a programming language.

---

### Choreography — correlation key and quorum

When multiple independent actors must all act on the same entity before a gate fires (saga pattern, multi-party approval, quorum), use `correlation_key` + `count`:

```json
"AuthorizationGate": {
  "requires":        ["AdminApproval", "ThreatClear"],
  "count":           { "AdminApproval": 2 },
  "correlation_key": "request_id",
  "correlated":      ["AdminApproval"],
  "window_ms":       300000,
  "emits": [
    { "outcome": "authorized",   "flows": ["AuthorizedRequest"] },
    { "outcome": "unauthorized", "flows": ["AccessDenied"]      }
  ]
}
```

`correlated` lists which pulse types must share the same `correlation_key` value. `ThreatClear` is uncorrelated — it just needs to be present in the window. `count` expresses quorum: 2 `AdminApproval` pulses with the same `request_id` required.

---

## Gate firing — coincidence detection

A gate fires only when **all** types in `requires` arrive within `window_ms`. AND-coincidence detection is the core mechanism.

- **Security is topology, not code.** A protected gate must list sentinel gates in `requires`.
- **Cardinality is shape.** Redundancy, fan-out, and quorum are expressed as synapse counts and `count`.
- **Dead gates are structural.** Unreachable coincidence is caught by opis-eval before runtime.
- **Refractory is physical reality.** Derivable from profiling the real system.

---

## Design principles

**Nodes are topology, not data.** Loci and archetypes hold no properties.

**Pulses carry everything.** Payload fields live on the pulse, not the node.

**Security is structural.** AuthN/AuthZ sentinels are upstream `requires` — not code paths.

**Cardinality is shape.** Redundancy, fan-out, and quorum are expressed as synapse counts, not configuration.

**Topology is the output.** The network restructures itself in response to what it cannot express or sustain.

---

## Why neuromorphic, not ECS

ECS imposes a total order (main loop) on a concurrent world. Opis replaces it with a partial order: gates fire when charge accumulates, not on a clock tick.

```
Petri net:  preconditions → fire → postconditions
SNN adds:   integrate(window) → threshold → spike → refractory(measured)
Opis adds:  ontology (archetypes) + typed pulse routing + coincidence detection
```

The architect thinks in topology (shapes). The tools count (cardinality, timing, dead gates). Division of labour matches how humans actually think about systems.

---

## Topology growth (learning)

Kata gaps are not errors to minimize — they are signals to grow new topology:

- Dead gate → prune the synapse or replace with new topology
- `MISSING_PRIMITIVE` gap → grow a new locus/archetype/gate to express it
- Pattern recurs across domains → crystallise into a reusable archetype

Each domain (fintech, logistics, healthcare) the system processes is training data for topology growth. When the topology stabilises on a domain, the network has learned that domain's architecture structurally, not statistically.

---

## Folder Structure

```
agents/
  fa/                              ← FA agent code (Python)
  ga/                              ← GA agent code (Python, later)
  ca/                              ← CA dev-lead agent code (Python, later); CA *outputs*
                                     (schemas, Rust gate crates, docker compose, the whole
                                     runnable stack) are EPHEMERAL — regenerated per run,
                                     never checked in; only evidence reports persist

  input/                          ← drop kata .md here to trigger FA

  gates/                          ← gates repository (shared across all katas)
    index.md                      ← list of all available gates
    order_processor.md            ← one structured .md file per gate
    payment.md
    sentinel_auth.md
    ...

  slot_types/
    index.md                      ← single file: full slot type hierarchy

  domains/                        ← shared domain archetype libraries
    food_service/
      archetypes.md
    logistics/
      archetypes.md

  (repo root)/workspace/          ← agents' LOCAL workspace — its own git repo,
    <kata_name>/                    never pushed; agents commit their runs here;
      flow/                         flows are regression baselines, no authority
        flow_v1.json              ← first clean passing spec (internal iterations are not versioned)
        flow_v2.json              ← new version only on: kata change, ADR approval, explicit re-run
        flow_current -> flow_v2   ← symlink to latest passing version
      adrs/
        001_<topic>.md            ← one ADR per decision or gate proposal
      tests/
        fa_tests.md               ← tests FA proposes for FA, GA, CA

      ga/
        flow_v1/
          gates_v1.json           ← parameterized gates for this flow version
          pds/
            order_processor.json  ← probability distributions per gate
          logs/
            <timestamp>/
              run.log
              twin_report.json

      ca/
        python/
          flow_v1/
            order_processor/      ← generated code per gate
            payment/
            logs/
              <timestamp>/run.log
        go/
          flow_v1/...
        rust/
          flow_v1/...
```

Key rules:
- One kata = one `output/<kata_name>/` subtree.
- FA versioned flow specs accumulate; `flow_current` always points to the latest passing version.
- GA and CA outputs are keyed by flow version so a new FA iteration triggers fresh GA/CA runs.
- Multiple CA language targets coexist under `ca/<language>/`.
- The gates repository and slot types are shared across all katas — new entries require User approval.

## Implementation Languages

**Python** — all agent orchestration: FA, GA, CA. LLM calls, file I/O, prompt iteration. Chosen for accessibility and fast iteration on agent logic.

**Rust** — simulation only: `opis-twin` Monte Carlo engine and `da-core` data model it consumes. Chosen for performance (thousands of gate firings per simulation run). Not needed until the sim milestone.

The two layers communicate through files — agents write specs, the sim reads them. No in-process coupling.

## Tooling

| Tool | Language | Path | Purpose |
|------|----------|------|---------|
| `opis-eval` | Python | `tools/opis-eval/eval.py` | Static structural analysis: reachability, dead gates, cycles, sentinel coverage, cascade timing, cardinality ceilings, slot isolation |
| `fa` | Python | `agents/fa/` | FA agent: kata → versioned flow spec, gate selection and proposal |
| `ga` | Python | `agents/ga/` | GA agent: gate parameterization, PD management (later) |
| `ca` | Python | `agents/ca/` | CA dev-lead agent: schema translation + Rust gate generation + co-sim runs; outputs ephemeral (later) |
| `opis-twin` | Rust | `agents/crates/da-twin/` | Monte Carlo simulation: p50/p95/p99 per gate (later) |
| `da-core` | Rust | `agents/crates/da-core/` | Core Opis data model consumed by sim (later) |
| `katas/` | — | `agents/katas/` | Architectural katas as inputs |

Run eval: `python tools/opis-eval/eval.py <spec.json>`

---

## opis-twin

Monte Carlo simulation with realistic latency distributions on synapses. Models slow wifi, rush-hour traffic, domain-specific variability. Output: p50/p95/p99 per gate, saturation curves, weak-link identification. GA uses twin output to validate that parameterized gates meet the flow's timing requirements.

When CA has implemented a gate, sandbox-measured PDs supplement MC estimates as lower bounds — the twin switches from pure simulation to instrumentation-grounded simulation for those gates (progressive substitution: real code where code will exist, statistical emulation where the world is). Sandbox numbers falsify contracts confidently but validate them only weakly; production-grade PDs come only from the real-use outer loop.

Synapse latency is log-normal by default (matches both local and network latency empirically). Parameters: `p50` and `p99` measured from real traffic or MC.

Not just for software — a logistics company uses this to find which warehouse is the bottleneck and what happens if they add a sorting hub. Same model, same tools.

---

## Vocabulary (canonical)

`kata` · `domain` · `locus` · `source` · `archetype` · `extends` · `gate` · `flow` (level) · `detail` (level) · `sentinel` · `regulator` · `pulse` · `charge` · `spike` · `synapse` · `inhibitor` · `medium` · `p50_ms` · `p99_ms` · `requires` · `count` · `correlation_key` · `correlated` · `window_ms` · `refractory_ms` · `emits` · `outcome` · `flows` · `cardinality` · `per_instance` · `shared` · `topology_group` · `slots` · `shared_loci` · `mechanism` · `interaction` · `push` · `pull` · `PD` · `ADR` · `FA` · `GA` · `CA`

---

## Known gaps (empirical, 2026-06-30)

1. Offline / partition semantics — sync gate models the coordination point; optimistic vs. pessimistic behavior during partition is not yet expressible.
2. SLA/latency contracts on loci.
3. Event/pub-sub primitive (pub-sub as a first-class synapse medium).
4. Workflow state machine (multi-step ticket lifecycle).
5. ADR schema — structure of `decisions/` folder not yet defined.
6. Flow context key — correlation across pulses within one end-to-end flow not yet validated by opis-eval.
7. `correlation_key` / `correlated` / `count` parsed but not yet enforced by opis-eval.
8. Domain gate libraries — computing-level gates glossary exists; domain-specific layers (food, delivery, fintech) not yet built.

---

## Future: neuromorphic hardware

```
today:  Opis spec → Python simulator → gap report (seconds)
next:   Opis spec → compiled pulse graph → Loihi (microseconds)
later:  topology grows autonomously from domain traffic → self-organising architecture
```

Intel Loihi / IBM TrueNorth execute pulse graphs natively. Validation that takes seconds in Python could run in microseconds on dedicated silicon.

---

## Strategic context

Opis is a platform in its own right. The specification language plus opis-eval plus opis-twin form a complete platform for designing, validating, and evolving any system whose structure should respond to its own usage — software services, logistics networks, hospital triage, financial workflows.

The two agent loops (FA for topology, GA for contracts) plus CA as dev lead mean a domain expert can describe what the system must do (kata) and the agents produce a validated, simulated, and feasibility-tested system — with every decision traceable to an ADR the User approved.

Dog-food product: the **Opis UI editor**, designed and built using Opis itself.
