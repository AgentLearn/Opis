# Opis Workbench — Architect's Console

Opis Workbench is the control panel a software architect uses to inspect,
verify, and steer Opis's own agents. The architect works in a browser. The
system's world contains the workspace repository (flows, ADRs, evidence,
falsification reports, defect histories — written concurrently by the FA
and CA agents), the gate library with its pinned contract versions, the
verifier executables (structural eval, requirement prover, regression
suite, contract lint), and the twin simulator. The workbench owns no state
of its own: everything it shows is derived from the workspace and the
library, and everything it changes goes through the same recorded channels
the agents use.

## Definitions — the existing system's vocabulary

The workbench is added onto an existing system, Opis. The requirements
below use that system's terms with exactly these meanings. (These define
the domain the workbench operates ON; the facts that travel through the
workbench itself are derived from the requirements as usual.)

- **Flow** — an architecture description: a directed graph of loci,
  gates, and synapses showing how facts move through a system. Flows are
  versioned (`flow_v1`, `flow_v2`, …); a committed version is immutable.
- **Locus** — a place where something acts or is stored: a person, an
  external service, a repository. Loci route facts; they never transform
  them.
- **Gate** — the only transforming element: it waits for its required
  inputs to coincide within a time window, fires once, and emits one
  outcome. Every gate instance claims a versioned contract.
- **Synapse** — a directed connection carrying one type of fact between
  two elements.
- **Pulse** — a single fact traveling a synapse at a moment in time: an
  order placed, a query answered, a command acknowledged.
- **Gate contract** — the document defining what a gate template
  requires, emits, and promises. Contracts are append-only: amending one
  archives the old version and bumps the version number.
- **Pins** — a lock block inside a committed flow naming the exact
  contract versions, taxonomy, and kata it was proved against, each with
  a content hash. Pins make a proof reproducible.
- **Gate internals** — a gate's own inner pulse-network, expressed in the
  same graph format as a flow.
- **Witness path** — the proof of a requirement: an actual reconstructed
  path through the graph from source to target. No path, no proof.
- **Verifier** — an executable checker. Four exist: structural eval
  (graph well-formedness), requirement prover (witness paths), regression
  suite (all committed flows still hold), contract lint (contract prose
  vs. declared slots).
- **Twin** — a simulator that executes a flow in virtual time and reports
  fire rates, latencies, and dead gates.
- **ADR** — architecture decision record: a question with genuine
  options, decided by the architect; decisions are binding on all future
  agent runs.
- **Evidence report** — the per-flow-version record of claims, each a
  tuple {claim, verdict, evidence pointer, scope} with verdicts
  proved/passed/bounded/flagged/failed. No claim without a pointer.
- **Falsification report** — the record of a flow or contract failing
  translation or simulation: the failing gates, the missing paths, and
  the named failure class.
- **Parameter** — a declared number in a flow: cardinality count,
  coincidence window, refractory period, synapse timing. Its provenance
  is either declared (an assumption) or measured (fed back from a running
  implementation).
- **Agent** — an autonomous worker that produces the system's artifacts.
  Two exist: **FA** (flow architect — turns a kata into a proved,
  versioned flow, proposing ADRs when it hits a decision it cannot make)
  and **CA** (dev lead — translates a committed flow's contracts into
  schemas and running gate code, and falsifies contracts that cannot be
  translated). Agents act only through workspace commits; the workbench
  observes their work, it never contains them.
- **Workspace repository** — the git repository where the agents commit
  flows, ADRs, evidence, and falsification reports.
- **Branch** — a speculative line of workspace history. Runs and what-ifs
  happen on branches; approval merges a branch to the main line; the main
  line is append-only and never rewritten.
- **Kata** — a problem statement, like this document.

## Requirements

- The architect browses katas, flow versions, and their histories directly
  from the workspace repository; when an agent commits new work (a flow
  version, a pending ADR, an evidence report), it appears without restarting
  the workbench.
- A selected flow renders as its graph — loci, gates, synapses — and
  selecting a requirement highlights its witness path on that graph. The
  path shown is re-derived by the requirement prover on demand, never
  replayed from a cached claim.
- The architect drills down without losing the big picture: a gate opens
  into its contract (pinned version, content hash verification, lint
  findings), and a gate with committed internals opens into its internal
  pulse-network rendered by the same graph view.
- A non-happy-path view shows, for a selected requirement, the outcome
  branches not on the proved path — timeouts, denials, breaker trips — each
  traceable to its downstream consumer.
- Pending ADRs are presented for decision with a plain-language reading of
  the question and each option's consequence; the full technical text and
  every cited decision, contract, and falsification is one step away, pulled
  by the architect rather than front-loaded.
- The architect decides a pending ADR from the workbench; the decision is
  written through the same single decision-recording path the CLI uses and
  committed to the workspace repository.
- Before deciding, the architect opens a pending ADR's options as
  side-by-side speculative branches: each option applied on its own
  workspace branch and run through the structural eval and the requirement
  prover, results rendered next to each other. A speculative branch never
  touches the main line; deciding still goes through the single
  decision-recording path.
- Evidence reports render with every claim linked to its evidence pointer;
  a claim with no pointer is not rendered as fact. Caveats and bounded
  verdicts are displayed with the same prominence as proofs.
- Falsification reports are told on the flow graph itself: the failing
  gates, the missing or hollow paths, and the class the falsification
  belongs to.
- The architect re-runs any verifier — structural eval, prover, regression
  suite, contract lint — against the current workspace state on demand, and
  the fresh result supersedes anything previously displayed.
- The architect authors an ad-hoc scenario — chosen inputs from the flow's
  source loci — and executes it as a one-off twin run; the outcome
  (fire rates, decisions, dead gates) is shown on the graph.
- Every declared parameter of the selected flow — cardinality counts,
  coincidence windows, refractory periods, synapse timing — is adjustable
  from the graph view. Each parameter carries its provenance: declared (an
  architect's stated assumption) or measured (fed back periodically from a
  running implementation). No measured values exist yet; the empty measured
  slot is displayed, not hidden — a declared value pretending to be
  knowledge is the failure mode this view exists to prevent.
- An adjusted parameter set is a what-if: it lives on a workspace branch,
  drives a twin re-run against the modified flow, and the outcome is shown
  beside the main-line baseline. Approval is a merge: promoting a what-if
  into the main line merges its branch and triggers re-proof through the
  existing recorded channel. A branch never merged leaves the main line
  untouched — rollback is not an operation, it is declining to merge.
- The architect starts an agent run from the workbench — FA against a
  kata, CA against a committed flow — on a workspace branch. A run is a
  loop, not a command: the workbench shows each iteration as it happens —
  the defects found, the retries, the agent's persisted reasoning
  artifacts — and the spend accrued so far, not just a final verdict.
- The architect pauses a run between iterations and resumes it later, or
  stops it outright; no further iteration starts once told, and spend
  stops with it. When a run pauses itself on proposed ADRs, the workbench
  presents them for decision and the decision resumes the loop — decide,
  run, observe, decide is the workbench's working cycle.
- A run that ends well concludes with committed work on its branch; the
  architect approves by merging to the main line. A stopped or abandoned
  run leaves the main line untouched.
- Every failure is loud: a failed verifier run, twin run, or workspace read
  is shown with its full output, never summarized to a count or a silent
  blank.
- Long-running work (a twin run, a regression sweep) reports progress while
  it runs and can be cancelled by the architect.

## Nonfunctional requirements

- The workbench is a multiagent system, not a page: it coordinates the
  workspace repository, the verifier executables, the twin, and the agents'
  concurrent output. A server-side deployment is expected; the browser is
  only the rendering surface and holds no authority.
- One user. Version 1 serves a single architect on their own machine
  against their own workspace — no accounts, no sessions, no concurrent
  editors. If that ever changes, the change arrives as a new kata
  requirement and the flow is re-proved and re-implemented for it; nothing
  in v1 should pre-build for the multi-user case.
