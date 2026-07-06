# Environment — Mac workstation

Descriptive facts about the infrastructure, not decisions: an environment
that cannot carry a contract is a translation falsification, and the
resulting fork is decided through the ADR channel.

## Host

- One developer machine (macOS), one user — the architect who owns the
  workspace. No accounts, no remote access.
- The product repository and the workspace repository are on local disk;
  full read/write, git available, processes may run as long as the
  architect keeps them.

## Runtimes available

- Python 3.12 with the standard library. Third-party Python packages are
  not available at runtime (no pip install assumed).
- A modern evergreen browser as the rendering surface. Frontend libraries
  may load from public CDNs at page load; the tool must remain usable if
  that is the only network access it ever gets.
- Rust toolchain with the wasm32-wasip1 target, wasmtime, and the compiled
  verifier and simulator executables in the repository (opis-eval suite,
  da-twin) — invokable as subprocesses.

## Boundaries

- Network: localhost only, plus CDN fetches by the browser at load.
- Subprocesses: only the repository's own verifier/twin executables, never
  arbitrary commands.
- No containers, no daemons, no installation step beyond cloning the
  repository: starting a tool is one command, stopping it is Ctrl-C, and
  it leaves nothing running behind.
- Long-running work must not block the architect; agent commits arrive in
  the workspace concurrently.
