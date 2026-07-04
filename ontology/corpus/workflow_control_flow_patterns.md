# Seed corpus: Workflow Control-Flow Patterns

Source (authoritative): Russell, ter Hofstede, van der Aalst, Mulyar,
"Workflow Control-Flow Patterns: A Revised View", BPM Center Report BPM-06-22, 2006.
Catalog: http://www.workflowpatterns.com/patterns/control/
Original paper: van der Aalst, ter Hofstede, Kiepuszewski, Barros,
"Workflow Patterns", Distributed and Parallel Databases 14(3):5-51, 2003.

This file is the hand-curated seed corpus for the OG-RAG-style ontology induction.
It is the golden-recipe INPUT: the induced ontology is derived from it, then diffed
against Opis's existing slot_types / gate kinds / gate logic vocabulary.

Scope note: the 43 patterns cover the CONTROL-FLOW perspective (branching, merging,
synchronization, iteration, cancellation, triggers). This is exactly the layer where
Opis gate `logic` and `kind` live. The Data, Resource, and Exception perspectives are
out of scope for this first run (they map to CA schemas and twin/co-sim, not gate logic).

Each entry: WCP id | name | category | control-flow semantics | Opis relevance.

---

## Basic Control-Flow Patterns
Elementary process control (WfMC-level constructs).

- **WCP1 Sequence** — an activity is enabled after the completion of a preceding
  activity in the same process. The fundamental building block; a directed edge.
  Opis: a synapse from one gate's outcome to another gate's input.

- **WCP2 Parallel Split (AND-split)** — a single thread of control splits into
  multiple threads that execute concurrently. All outgoing branches are activated.
  Opis: a gate emitting to multiple downstream synapses (fan-out).

- **WCP3 Synchronization (AND-join)** — multiple concurrent branches converge into
  one; the outgoing branch is enabled only after ALL incoming branches complete.
  Assumes each incoming branch fires exactly once. Opis: `logic: AND`.

- **WCP4 Exclusive Choice (XOR-split)** — one of several outgoing branches is chosen
  based on a condition/decision; exactly one branch is activated. Opis: a gate whose
  distinct outcomes route to different downstream gates (outcome-based routing).

- **WCP5 Simple Merge (XOR-join)** — two or more branches converge without
  synchronization; the outgoing branch is enabled every time an incoming branch
  completes. Assumes only one incoming branch is ever active. Opis: `logic: OR`
  (earliest-arrival join, no synchronization).

## Advanced Branching and Synchronization Patterns
Complex branch/merge behaviours; often unsupported in commercial tools.

- **WCP6 Multi-Choice (OR-split)** — one or more outgoing branches are chosen based on
  conditions; between one and all branches activate. Opis: conditional fan-out.

- **WCP7 Structured Synchronizing Merge** — merges the branches activated by a
  preceding Multi-Choice; waits for exactly the branches that were activated (knows
  how many to expect because it is structurally paired with the split). Opis: relates
  to `logic: AND` but with a dynamic, run-determined arrival count.

- **WCP8 Multi-Merge** — multiple incoming branches converge WITHOUT synchronization;
  the subsequent activity is triggered once PER incoming branch completion (so it can
  run multiple times). Opis: no clean equivalent — Opis gates fire per satisfied
  input bundle; multiple firings = repeated pulses, not a distinct join type.

- **WCP9 Structured Discriminator** — waits for ONE of several incoming branches to
  complete, activates the subsequent activity, then IGNORES the other branches until
  all have completed (after which it resets). First-to-arrive wins. Opis: `logic: FIRST`.

- **WCP28 Blocking Discriminator** — as Structured Discriminator, but handles multiple
  concurrent cases: it blocks subsequent triggerings on the same branch until reset.
  Opis: `logic: FIRST` combined with refractory / one-in-flight semantics.

- **WCP29 Cancelling Discriminator** — on the first branch completing, the remaining
  incoming branches are actively CANCELLED (not just ignored). Opis: `logic: FIRST` +
  a cancellation side-effect on the losing branches (no direct Opis equivalent today).

- **WCP30 Structured Partial Join (N-out-of-M join)** — waits for N of M incoming
  branches to complete, then activates the output; remaining M-N are ignored until
  all complete, then resets. Opis: `logic: THRESHOLD` (n). Discriminator = the N=1 case.

- **WCP31 Blocking Partial Join** — N-out-of-M join that supports multiple concurrent
  cases by blocking further input on completed branches. Opis: `THRESHOLD` + refractory.

- **WCP32 Cancelling Partial Join** — once N of M complete, the remaining incoming
  branches are CANCELLED. Opis: `THRESHOLD` + cancellation side-effect.

- **WCP33 Generalised AND-Join** — an AND-join that does not assume structured
  pairing; it synchronizes multiple branches even in unstructured/concurrent process
  regions, firing once all expected inputs arrive regardless of ordering. Opis:
  `logic: AND` in the general (non-tree) flow graph — the AND-join fixed point in proof.py.

- **WCP37 Local (Acyclic) Synchronizing Merge** — synchronizing merge decided using
  only local, acyclic information about which branches can still arrive. Opis: the
  reachability analysis that decides whether a required input can still be produced.

- **WCP38 General Synchronizing Merge** — synchronizing merge in the presence of
  cycles/arbitrary topology; requires global lookahead to know whether more inputs may
  yet arrive. Opis: the hardest case for the AND-join fixed point over cyclic flows.

- **WCP41 Thread Merge** — a nominated number of execution threads on a single branch
  merge into one. Opis: aggregation of multiple pulses of the same type.

- **WCP42 Thread Split** — a single thread on a branch splits into a nominated number
  of threads. Opis: emitting multiple pulses of the same type.

## Multiple Instance Patterns
Multiple concurrent instances of the same activity/sub-process.

- **WCP12 Multiple Instances without Synchronization** — an activity spawns multiple
  independent instances that do not need to be synchronized afterward. Opis: fan-out of
  independent pulses.

- **WCP13 MI with a Priori Design-Time Knowledge** — number of instances known when
  the model is designed. Opis: a fixed fan-out declared in the flow.

- **WCP14 MI with a Priori Run-Time Knowledge** — number of instances known at runtime
  before instances are created (e.g. one per line item). Opis: data-determined fan-out.

- **WCP15 MI without a Priori Run-Time Knowledge** — instances created dynamically;
  the total is not known until the last one completes. Opis: no equivalent — Opis flows
  are statically typed; dynamic instance counts live in CA payload/body layer.

- **WCP34 Static Partial Join for MI** — of N known instances, proceed once M complete.
  Opis: `THRESHOLD` over multiple instances of one activity.

- **WCP35 Cancelling Partial Join for MI** — as WCP34, then cancel remaining instances.
  Opis: `THRESHOLD` + cancellation.

- **WCP36 Dynamic Partial Join for MI** — partial join where instance count is dynamic.
  Opis: no equivalent (dynamic instances).

## State-Based Patterns
Behaviour determined by process state / environment interaction.

- **WCP16 Deferred Choice** — like Exclusive Choice, but the branch is selected by
  INTERACTION WITH THE ENVIRONMENT (a race between external events), not by an internal
  decision. The choice is deferred until one event actually occurs. Opis: a gate whose
  outcome is decided by which external locus/pulse arrives first — closely related to
  `kind: sentinel`/external triggers and to `logic: FIRST` on external inputs.

- **WCP17 Interleaved Parallel Routing** — a set of activities executes in an order not
  known in advance, but no two run simultaneously (mutual exclusion, partial order).
  Opis: no direct equivalent; relates to serialization constraints.

- **WCP18 Milestone** — an activity is enabled only when the process is in a specific
  state (a milestone has been reached and not yet passed). A gating precondition on
  external state. Opis: closely related to `kind: regulator` and to a gate whose firing
  is conditioned on a state window being open. Also relates to `kind: breaker` recovery.

- **WCP39 Critical Section** — prevents concurrent execution of designated process
  regions (mutual exclusion over a shared resource). Opis: relates to throttle/regulator
  gates guarding a shared downstream.

- **WCP40 Interleaved Routing** — a group of activities executed sequentially in any
  order, one at a time. Opis: serialization; no direct equivalent.

## Cancellation and Force-Completion Patterns

- **WCP19 Cancel Task** — an enabled/running activity instance is withdrawn (disabled).
  Opis: relates to `kind: breaker` tripping (suppressing a gate).

- **WCP20 Cancel Case** — an entire process instance is removed. Opis: aborting a flow
  run; relates to breaker cascades.

- **WCP25 Cancel Region** — a defined set of activities is withdrawn together (a
  cancellation region). Opis: a breaker tripping a whole downstream region.

- **WCP26 Cancel Multiple Instance Activity** — all instances of an MI activity are
  withdrawn. Opis: cancellation over fan-out.

- **WCP27 Complete Multiple Instance Activity** — force an MI activity to complete
  early, treating remaining instances as done. Opis: `THRESHOLD`-like forced completion.

## Iteration Patterns

- **WCP10 Arbitrary Cycles** — unstructured loops with more than one entry or exit
  point (goto-style). Opis: cyclic flow topology (the twin handles cycles via
  fixed-point iteration; proof.py over cyclic flows).

- **WCP21 Structured Loop** — a loop with a single entry and exit and a pre- or
  post-test condition (while/repeat). Opis: a controlled feedback synapse.

- **WCP22 Recursion** — an activity invokes itself (directly or indirectly). Opis:
  a gate whose internals recursively reuse the gate composition format (GA internals).

## Termination Patterns

- **WCP11 Implicit Termination** — a process instance terminates when there is no
  remaining work to do (nothing enabled, nothing running). Opis: a flow completes when
  all pulses drain (proof.py drain reaches a fixed point).

- **WCP43 Explicit Termination** — the process terminates when a designated end node is
  reached, regardless of remaining work. Opis: a terminal locus/sink reached.

## Trigger Patterns
External signals required to start tasks.

- **WCP23 Transient Trigger** — an activity is triggered by a signal that is LOST if the
  activity is not ready to accept it (no buffering). Opis: a fire-and-forget event pulse
  that is dropped if no gate is waiting; relates to `input_timeout_ms` and event slot type.

- **WCP24 Persistent Trigger** — a triggering signal is RETAINED (buffered) until the
  activity is ready to process it. Opis: a queued/buffered input; relates to
  queue-based estimator gates and durable event handling.

---

## Cross-reference table: WCP -> Opis vocabulary (curator's mapping, to be tested by induction)

| WCP | pattern | Opis construct |
|-----|---------|----------------|
| WCP3 | Synchronization (AND-join) | `logic: AND` |
| WCP5 | Simple Merge (XOR-join) | `logic: OR` |
| WCP9 | Structured Discriminator | `logic: FIRST` |
| WCP30 | Structured Partial Join (N-of-M) | `logic: THRESHOLD` (n) |
| WCP33 | Generalised AND-Join | `logic: AND` over general graph |
| WCP4 | Exclusive Choice | outcome-based routing (distinct outcomes -> synapses) |
| WCP16 | Deferred Choice | external-input FIRST / `kind: sentinel` |
| WCP18 | Milestone | `kind: regulator`, state-window gating |
| WCP19/25 | Cancel Task/Region | `kind: breaker` trip |
| WCP23 | Transient Trigger | fire-and-forget event + `input_timeout_ms` |
| WCP24 | Persistent Trigger | buffered/queued input |
| WCP21/22 | Structured Loop / Recursion | feedback synapse / GA gate internals |

## Opis constructs with NO WCP counterpart (candidate Opis-original contributions)
To be confirmed by the induction diff, not asserted here:
- **refractory period** (`recovery_ms`) — time-based suppression after firing.
- **windows** (`input_timeout_ms` as a time budget, sliding windows) — temporal join scoping.
- **probabilistic outcomes** — gates emit outcomes with probabilities (twin sampling).
- **breaker as first-class kind** (`trips_on`/`recovery_ms`) — WCP has Cancel patterns
  but not a self-resetting circuit-breaker with a recovery timer.
- **latency budgets / timing contracts** — WCP is untimed (Petri-net token semantics);
  Opis gates carry p50/p95 timing.
