# Environment — AI dev tool sandbox

Descriptive facts about the infrastructure, not decisions: an environment
that cannot carry a contract is a translation falsification, and the
resulting fork is decided through the ADR channel.

This environment is an agentic development tool (a cloud or local AI
sandbox: Cowork, Claude Code, or similar). The primary operator is an AI
agent acting for the architect; the human sees the tool through the
agent's conversation, not through a browser pointed at the tool.

## Host

- An ephemeral Linux sandbox. Nothing survives between sessions except
  the mounted repositories; any built or installed tooling vanishes and
  must be reconstructible by recipe.
- The product and workspace repositories are mounted from the architect's
  machine. The mount may be restricted (observed today: create and modify
  allowed, delete and git-index writes must happen on the architect's
  side) — the tool must degrade honestly when a write channel is missing,
  and say so loudly.

## Runtimes available

- Python 3 with the standard library; common toolchains (Node, Rust) are
  installable per session but not assumed.
- No browser rendering surface. The consumer of any interface is an AI
  agent or a human reading text: surfaces must be available as plain
  files, JSON on stdout, or a line protocol — the same information the
  browser UI would render, without the pixels.
- The repository's verifier and simulator sources are present; compiled
  executables may need a per-session rebuild from the documented recipe.

## Boundaries

- Network: outbound access is restricted and allowlisted by the tool;
  assume none beyond what package installation needs.
- Subprocesses: only the repository's own verifier/twin executables and
  standard build tools.
- Sessions end without warning: any long-running work must checkpoint its
  progress into the workspace so a following session (or the architect's
  machine) can resume from artifacts, not from memory.
- Concurrent actors are normal: the architect's machine and the sandbox
  may both touch the workspace in one day; recorded channels (commits,
  decision writer) are the only coordination.
