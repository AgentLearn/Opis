# Design decision records (DDR) — opis workbench face

Face-scoped decisions for THIS artifact. Append-only, dated, newest
first — the same discipline as strategy.md and decided ADRs, but a
separate channel with a routing test:

- changes a contract, requirement, or traveling fact → NOT here:
  kata amendment + ADR, FA re-proves (the only door to the graph);
- changes an environment fact → NOT here: env doc correcting commit;
- changes only how a face renders the same recorded facts → DDR, here.

DDRs live beside the artifact they govern because the artifact is a
golden recipe: an agent rebuilding this face must honor decided DDRs
exactly as FA honors decided ADRs. A DDR may never contradict the
kata; if it wants to, it is misrouted — it is an ADR trying to hide.
Product-face vocabulary: these are just "choices about how it looks."

## DDR-004 — domain-expert face v0 scope (2026-07-12)

`/expert.html` — plain-words chrome ("decision", "choice", "why",
"running work"; FA/CA rendered as "the designer"/"the builder"), no
graph, question cards with drill-down option details, decide + reject
through the SAME adr_decide action (REQ-32: the record does not know
which face produced it). BOUNDED COVERAGE, stated on the face's own
code: (a) decision PROSE is shown verbatim and may contain engineer
terms — true plain-language reading needs the model channel (2026-07-06
two-faces decision), deferred; (b) scenarios-in-story-terms deferred
for the same reason — the face says "not yet" rather than faking it.
Rejecting requires a written reason: the system never records a
silent no.

## DDR-003 — architect face grows panes, graph stays home (2026-07-12)

View switcher in the rail (graph / evidence / decisions / diff /
what-if / runs); graph remains the default view — the complexity gauge.
Evidence pane renders caveats with the SAME prominence as proofs and
refuses to render pointerless claims as fact (doctrine). Decisions pane
writes through agents/fa/adr.py verbatim (REQ-10). Diff pane defaults
to the latest two versions; "show on graph" highlights added elements
in green over a dimmed graph. What-if pane is verifier-only on scratch
copies, ephemeral (2026-07-08); results side-by-side A/B. Runs pane
offers start/stop + ledger-derived spend ONLY — pause deliberately NOT
offered: the agents have no iteration-boundary hook, and a pause button
that kills mid-iteration would be an invented promise (honest-status
doctrine); agent-side hook = candidate work, recorded in strategy.

## DDR-002 — dark and light theme, user-toggled (2026-07-12, Zarko)

One toggle in the rail; dark stays the default. Palettes are named
token sets (`PALETTES.dark/.light`) covering both CSS and the
Cytoscape graph style, so any future face reuses them instead of
hardcoding colors. The chosen theme is VIEW-STATE, not domain state:
persisted in the browser's localStorage only, never written to the
workspace — "the face holds no state" means no DOMAIN state; view
preferences stay on the client. Graph re-styles in place on toggle.

## DDR-001 — this record exists (2026-07-12, Zarko)

Charter above. Origin: first change-of-mind on the built face (theme
toggle) had no honest home — flow-ADR too heavy, silence forbidden by
the golden-recipe principle. Sibling precedent: strategy.md for the
project, decided ADRs for the flow; this is the same shape scoped to
one face artifact.
