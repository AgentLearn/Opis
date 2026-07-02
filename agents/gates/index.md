# Gates Index

Computing-level gate library. FA selects gates by matching domain archetypes to input slot types.

Every gate carries a lifecycle `status` and a `confidence` provenance tag in its
frontmatter. Contracts are promoted only with evidence — grounding in real-life
architectures (`sourced`) or high-quality sandboxed twin runs (`twin-validated`).

Lifecycle: `draft` (ADR only) → `specified` (contract + proved internals) →
`simulated` (twin-validated timing) → `measured` (real CA implementation PDs).
Demotion is possible: evidence from any lower stage can invalidate the stage above.

**Blank-slate reset 2026-07-02:** the library was emptied deliberately — the
previous 14 seed contracts (built by earlier-generation runs) live in git
history. Every gate below this line was proposed from a kata by the current
agent generation, through the binding-ADR process.

| gate | kind | input slot types | output slot types | auth_required |
|------|------|-------------------|-------------------|---------------|
