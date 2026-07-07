# Pre-registered check list — "hey, I need something like this" vs Opis

Specimen: opis_workbench kata (`agents/katas/opis_workbench.md`).
Status: PRE-REGISTERED. Commit this file BEFORE running condition A; the
git timestamp is the pre-registration. No check may be added, removed, or
reworded after condition A runs. Findings go in a separate results file.

## Protocol

- **Condition A (baseline):** hand the coding agent exactly this prompt:
  *"I need something like this — build it."* followed by the kata text
  verbatim AND the same environment document condition B used, verbatim
  (environment parity — both conditions get identical information; the
  difference under test is mechanism, not knowledge). Run N=3 independent
  attempts; score each; report the BEST.
- **Question parity:** both conditions may ask the human questions.
  Answer truthfully, volunteer nothing beyond the question asked, never
  coach. LOG every question asked in both conditions — the questions are
  data (see Q-checks below).
- **Condition B (Opis):** the existing opis_workbench v1 artifact
  (interactive run, evidence_v1). Same checks, same order, same evaluator.
- Every check is phrased as an observable probe on the running artifact —
  no Opis vocabulary in the pass criteria, so both conditions are scored
  on identical terms.
- Scoring per check: **MET / PARTIAL / ABSENT**. Separately tally
  **DRIFT** instances (behavior present but contradicting the kata) and
  **SILENT FAILURES** (system knew something and didn't say it).
- Known pre-registered gap in condition B (honesty clause): a failed
  workspace READ has no loud-failure path (accepted bounded coverage,
  strategy.md 2026-07-06). Check F-3 below will likely score PARTIAL or
  ABSENT for Opis. It stays in the list.

## Requirement checks (from the kata, in kata order)

- **R-1 Live workspace browsing.** Probe: while the app is running, add a
  new file to the workspace repo (a flow version or ADR) out-of-band.
  Pass: it appears in the app without restart.
- **R-2 Flow renders as a graph.** Probe: select a flow. Pass: nodes and
  connections render as a graph (not a file listing or raw JSON).
- **R-3 Requirement → path, re-derived live.** Probe: select a
  requirement; note the highlighted path. Modify the underlying flow file
  so the path must change; re-select. Pass: highlight reflects the change
  (derived on demand, not replayed from a cache).
- **R-4 Drill into a component's contract.** Probe: open a node. Pass:
  shows its versioned interface definition, an integrity check against
  the stored version (hash or equivalent), and any lint findings.
- **R-5 Drill into internals, same view.** Probe: open a node that has
  committed internals. Pass: internals render in the same graph view, and
  the big picture remains reachable (no dead-end page).
- **R-6 Non-happy paths visible.** Probe: for a selected requirement, ask
  for the branches NOT on the proved/happy path (timeouts, denials,
  breaker trips). Pass: each such branch is shown and traceable to its
  downstream consumer.
- **R-7 Pending decisions, plain-language.** Probe: open a pending ADR.
  Pass: the question and each option's consequence are readable by a
  non-specialist; jargon-free summary is the first thing shown.
- **R-8 Context is PULLED, not front-loaded.** Probe: from that ADR, tap
  a cited decision / contract / falsification. Pass: each is one step
  away on demand; the decision screen itself is not a wall of every
  citation expanded.
- **R-9 Decision writes through the recorded channel.** Probe: decide the
  ADR in the app; inspect the workspace repo. Pass: the decision landed
  as a commit through the same single recording path the CLI uses — not
  app-private state, not a second write path.
- **R-10 No claim without a pointer.** Probe: open an evidence report;
  find a claim lacking an evidence pointer (plant one if needed). Pass:
  every rendered claim links to its evidence; a pointerless claim is NOT
  rendered as fact; caveats/bounded verdicts get the same prominence as
  proofs.
- **R-11 Falsifications told on the graph.** Probe: open a falsification
  report. Pass: failing components, missing/hollow paths, and the
  falsification class are shown ON the flow graph, not only as text.
- **R-12 Re-run any verifier on demand.** Probe: trigger each verifier
  (structural eval, prover, regression, lint) from the app. Pass: runs
  against CURRENT workspace state; fresh result supersedes the stale
  display.
- **R-13 Ad-hoc scenario run.** Probe: author inputs for the flow's entry
  points; execute a one-off simulation. Pass: outcome (fire rates,
  decisions, dead components) is shown on the graph.
- **R-14 Progress reporting.** Probe: start a long run (regression sweep
  or simulation). Pass: progress is reported while it runs.
- **R-15 Cancellation.** Probe: cancel the long run mid-flight. Pass: it
  stops, and the app says so.

## Failure-loudness checks (silent-failure probes)

- **F-1 Failed verifier run is loud.** Probe: break a workspace file so a
  verifier fails. Pass: full output shown — never a count ("2 errors"),
  never a silent blank.
- **F-2 Failed simulation run is loud.** Probe: author a scenario that
  crashes the twin. Pass: full output shown.
- **F-3 Failed workspace read is loud.** Probe: make a workspace file
  unreadable; browse to it. Pass: the read failure is shown with content.
  (Pre-registered: Opis v1 expected PARTIAL/ABSENT here.)

## Q-checks — decision surfacing (scored from the question logs)

The drift mechanism is decisions made silently. For each condition,
enumerate after the fact every genuine design decision embedded in the
artifact (consistency choices, failure policies, ordering guarantees,
auth boundaries), then classify each:

- **Q-1 Surfaced with consequences:** the system asked the user, and the
  options came with evidence of what each choice does (best).
- **Q-2 Surfaced bare:** the system asked, but options carried no
  consequence evidence — the user had to guess.
- **Q-3 Silent:** the decision was made in the code without asking.
  Each Q-3 instance is counted alongside drift in the summary.
- **Q-4 Noise:** questions asked that were not genuine design decisions
  (preference theater). Tally, lower is better.

## Drift checks (from the nonfunctional requirements)

Each is a pass/fail probe; a fail counts as one DRIFT instance.

- **D-1 No invented state.** The app owns no database/store of its own;
  everything shown is derived from the workspace and library. Probe: grep
  the artifact for its own persistent store; delete any app-local cache
  and restart — nothing shown may be lost.
- **D-2 No multi-user pre-build.** No accounts, no login, no sessions, no
  concurrent-editor machinery. Probe: inspect for auth/session code.
- **D-3 Browser holds no authority.** Server-side coordination; the
  browser only renders. Probe: does any verification, decision-recording,
  or state derivation run client-side?
- **D-4 No second write path.** All changes go through the same recorded
  channels the agents use. Probe: diff the repo after every mutating
  action in the app; any write that bypasses the recording channel fails.
- **D-5 Unrequested features.** Tally anything substantial the kata never
  asked for (dashboards, metrics, theming systems, deploy tooling). Each
  is one drift instance — plausible output solving a problem nobody posed.

## Scoring sheet (fill per condition, per attempt)

| Check | A1 | A2 | A3 | B |
|-------|----|----|----|---|
| R-1 … R-15 | | | | |
| F-1 … F-3 | | | | |
| D-1 … D-5 (drift tally) | | | | |
| Q-1/Q-2/Q-3/Q-4 counts | | | | |
| Silent-failure tally | | | | |

## Deferred second act (not part of v1 scoring)

Environment swap: after scoring, hand both conditions "now I want this
on AWS" (a second environment doc). Measure rework: Opis claims
re-translation without re-proving (flow proof is infra-invariant
capital); a baseline rebuilds. Pre-registered as a follow-up, run only
after v1 results are committed.
