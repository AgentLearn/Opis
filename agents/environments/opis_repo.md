# Environment — Opis repositories and toolchain

Descriptive facts about the infrastructure, not decisions: an environment
that cannot carry a contract is a translation falsification, and the
resulting fork is decided through the ADR channel.

This environment is the world the workbench operates on: the Opis product
repository, the agents' workspace repository, and the verifier/simulator
executables. Every fact below is copied from the artifacts as they exist
on disk (2026-07-08), not described from memory. When reality and this
document diverge, reality wins and this document gets a correcting commit.

## Repositories

- **Product repo** (root): agent code (`agents/fa/`, `agents/ca/`), gate
  contracts (`agents/gates/*.md`, archived versions in
  `agents/gates/archive/<template>_v<N>.md`), katas (`agents/katas/`),
  environments (`agents/environments/`), slot types
  (`agents/slot_types/`), verifiers (`tools/opis-eval/`), twin source
  (`agents/crates/da-twin/`, Rust).
- **Workspace repo** (`workspace/`, its own git, never pushed): one
  directory per kata containing `flow/` (flow_vN.json, evidence_vN.json,
  flow_current symlink), `adrs/`, `logs/`, `taxonomy_vN.json`,
  `fa_defect_history.json`, `ca_defect_history.json`, and ephemeral
  `ca/` (gitignored except falsification reports and evidence).
- Main line is append-only: committed flow versions are immutable, old
  pins stay valid forever, contract amendments archive the outgoing
  version. Branches are the speculative space; merging is approval.

## Artifact shapes (as on disk)

- **flow_vN.json** — top-level keys: `name, version, description,
  archetypes, loci, gates, synapses, requirements, pins`. The pins block:
  `{"gates": {"<template>": {"version": N, "hash": "sha256:…"}},
  "taxonomy": {…}, "kata": {"file": …, "hash": …}}`.
- **evidence_vN.json** — `{opis_evidence: 1, provenance: {kata, flow,
  flow_version, generated_utc, pins, environment, twin}, verdict:
  {overall, requirements, failed, caveats}, claims: [...], gates:
  {"<template>@vN": …}}`. A claim is `{claim, verdict:
  proved|passed|bounded|flagged|failed, evidence, scope:
  static|twin|cosim|sourced}`; requirement claims carry `gate` and
  `evidence.witness_paths`: per required pulse type, a list of `{node,
  pulse_type}` hops from source locus to firing gate.
- **ADR file** — `adrs/NNN_slug.md`, markdown with `## Context`,
  `## Options` (`### Option A` … each with **Tradeoffs**),
  `### Architect's option (optional)`, `## Decision` (e.g. `**Option A**
  (User)`). A sibling `NNN_slug.md.processed` marker means the agent has
  acted on the decision. Undecided = Decision section empty.
- **taxonomy_vN.json** — `terms: {<name>: {extends, kata_phrase,
  description, consumed_by, produced_by}}`, plus loci and `unmappable:
  []` (non-empty unmappable blocks the FA run).
- **twin report (JSON)** — `{flow, runs, seed, e2e_p99_ms, bottleneck:
  {gate, p99_ms}, dead_gates: [], substituted_gates: [], latencies,
  gates: {<InstanceName>: {fire_pct, mean_ms, p50_ms, p95_ms, p99_ms,
  outcomes: {<outcome>: count}, service_source:
  library|window-derived|substituted}}}`.
- **Falsification report** — `workspace/<kata>/ca_falsification_vN.md`,
  prose with named failure class.
- **Defect histories** — JSON maps: fingerprint → `{line, status:
  outstanding|fixed, times_seen, times_fixed, reopened_count, first_seen,
  last_seen, runs_seen}`.

## Executables and invocations

All Python tools run from repo root with Python 3, stdlib only.

- `python3 tools/opis-eval/eval.py <flow.json>` — structural checks;
  exit 0 clean, 1 errors, 2 warnings-only; findings on stdout as
  sectioned human-readable text.
- `python3 tools/opis-eval/proof.py <flow.json> [--gates-dir <path>]` —
  requirement proofs with witness paths, gate conformance.
- `python3 tools/opis-eval/regress.py` — re-verifies every kata's latest
  committed flow against PINNED contract versions (archive-aware);
  advisory sections for lint and kata-pin movement.
- `python3 tools/opis-eval/contract_lint.py` — advisory only, exit 0/2.
- `python3 tools/opis-eval/pins.py` — compute/verify pin blocks,
  `--write` to embed.
- `tools/opis-eval/{schema_check.py, gate_harness.py, dep_check.py}` —
  CA-loop verifiers (schemas vs flow, gate probing via substitution
  manifest, wasm dependency allowlist).
- **da-twin** — build: `cargo build -p da-twin --release` (workspace copy
  outside any restricted mount; wasm gates need `--target
  wasm32-wasip1` + wasmtime). Run flags observed: `--report <out.json>`,
  `--substitutions <manifest.json>`, `--tamper-sigs`; report shape above.
- **Agents** — `python -m agents.fa.runner agents/katas/<kata>.md` (FA:
  taxonomy → flow iterations → commit; pauses by proposing ADRs and
  exiting), `python -m agents.ca.runner <kata>` (CA: schemas → codegen →
  harness → co-sim → evidence), `python -m agents.fa.adr <kata>`
  (interactive decision loop; every decision is a workspace commit).

## Facts with operational weight

- Agent runs stream nothing: progress exists only as files persisted per
  iteration (`logs/`, `response_iterN.txt`, defect histories). Anything
  that wants live progress must poll the filesystem or wrap the
  invocation and own its stdout.
- An FA "run" ends at ADR proposals; continuation after decisions is a
  new invocation. The loop across invocations is held together entirely
  by workspace state (markers, decided ADRs, defect history).
- Token spend IS persisted (2026-07-11): both agents append one line per
  LLM call to `workspace/<kata>/spend_ledger.jsonl` — shape
  `{ts, agent: fa|ca, run_id, kata, stage, iteration, model,
  input_tokens, output_tokens, stop_reason}`. `run_id` matches the FA log
  dir name. Append-only, best-effort (a failed write warns, never kills a
  run). Live spend = poll this file; defects/retries live separately in
  `fa_defect_history.json` / `ca_defect_history.json`, joinable by run.
- FA iterations take minutes each; taxonomy stage is silent while it
  runs.
- One human, one machine: the architect's workstation runs everything;
  concurrent actors coordinate only through commits.
