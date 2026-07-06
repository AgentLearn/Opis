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
