# da-diagram — Tool 3 Design

Interactive topology viewer and control panel for Dynamic Architecture flows.

---

## What it is

A local web app that reads the live agent workspace and lets a human inspect, annotate,
and steer the pipeline. Target users: domain experts, architects, stakeholders who need
to understand what the system produced and why — without reading JSON or logs.

---

## Architecture

```
agent/                     ← workspace (files on disk)
tools/da-diagram/
  server.js                ← Express + WebSocket server
  public/index.html        ← Single-page app (Cytoscape.js)
```

Run from agent/:
```
node ../tools/da-diagram/server.js [--port 7070]
```

Opens at http://localhost:7070.

The server reads files directly from the agent directory — no database, no sync step.
WebSocket streams live `da` subprocess output to the browser.
File watcher (chokidar) pushes graph updates to all open tabs automatically.

---

## Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│  toolbar: flow selector · status · history · twin · rerun           │
├──────────────┬───────────────────────────────────┬──────────────────┤
│ LEFT SIDEBAR │                                   │  RIGHT SIDEBAR   │
│              │        GRAPH (Cytoscape.js)        │                  │
│  ADRs        │                                   │  Iterations      │
│  Kata        │   [gate] ──pulse──▶ [gate]        │  Twin runs       │
│  History     │                                   │                  │
│              │   click gate → detail panel       │                  │
├──────────────┴───────────────────────────────────┴──────────────────┤
│  console: live `da` output (collapsible)                            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Features

### 1. Interactive graph

**Technology:** Cytoscape.js + dagre layout (top-to-bottom flow).

**Nodes** = gates (from graph.json). Visual encoding:

| kind     | colour       | shape        | source                            |
|----------|--------------|--------------|-----------------------------------|
| sentinel | blue         | round-rect   | TransactionCoordination, no 2PC   |
| sync     | red          | round-rect   | TransactionCoordination + 2PC     |
| gate     | dark gray    | round-rect   | everything else                   |
| pending  | dashed       | —            | gate in graph but no spec.json yet|

Guard gates added by repair loop: sentinel colour + thin label "(guard)".
ADR-linked gates: thicker border, orange dot.

**Edges** = connections from graph.json, labelled with pulse_type.

**Interactions:**
- Pan / zoom (wheel or trackpad)
- Click gate → detail panel: kind, archetype, inputs[], outputs[], pending flag, rerun button
- Click edge → highlight that pulse chain end-to-end
- Click background → deselect
- Toolbar button "fit" → reset zoom

**Zoom levels:**
- Default: full flow (all gates)
- Double-click gate: zoom to gate + immediate neighbours + mechanism sub-topology if present
- Breadcrumb trail back to full view

### 2. ADR sidebar (left panel, "ADRs" tab)

Each ADR shown as a card with:
- ID + title
- Status badge (active / draft / superseded)
- Gate tags: gate names extracted from ADR markdown body
- Toggle switch: disable/enable this ADR for the next run (renames file to .md.disabled)

**Click ADR card** → highlights those gates on the graph (orange glow).
**Toggle off** → gates no longer highlighted, toggle persists to disk so next `da` run skips it.

ADR-gate linkage: server scans ADR markdown for backtick-quoted kebab-case tokens that match gate names in the current graph.

### 3. Kata sidebar (left panel, "Kata" tab)

Shows kata requirements as a toggle list. Each bullet point from the kata markdown is:
- Displayed as a clickable row
- Click → strikes through (marks as disabled for next run)
- "Edit kata" button → opens full text editor overlay
- "Save + rerun" → saves and immediately fires a new `da` run

**Why per-requirement toggles:** lets you model "what if this feature is out of scope?"
without editing the file. The server rebuilds an effective kata from active requirements
before spawning `da`.

### 4. Iteration sidebar (right panel, "Iterations" tab)

Parses `flows/<name>/diary.md` into one card per phase:
- Initial pass: gates identified, missing flows
- Repair cycle N: gaps in → synthesized / discarded / new gates → gaps out
- Eval loop iter N: findings → repairs applied
- Final status: converged / kata_incomplete

Cards are clickable: clicking a repair cycle highlights the gates that changed in that cycle on the graph.

### 5. Twin sidebar (right panel, "Twin" tab)

After a `da-twin` run, shows:
- Fire% per gate as horizontal bar
- Latency p50/p95 per gate
- Anti-pattern findings from `--diagnose`
- "Run twin" button → spawns `da-twin` via WebSocket, streams output to console

### 6. Version control (left panel, "History" tab)

Reads `git log --follow flows/<name>/graph.json` and shows each commit as a row:
hash · message · relative time.

**Click commit → restore view:** loads that version of graph.json into the graph display
(read-only visual diff, does not overwrite disk).
"Apply" button → writes that version to disk and triggers rerun.

Visual diff between two selected commits: added gates green, removed gates red, changed edges orange.

---

## Ability a: rerun with ADRs modified

Toolbar "⟳ rerun" opens a small options sheet:
- Backend selector (ollama / anthropic)
- Model field
- ADR directory override
- Loop count (N iterations of eval-repair)
- Extra flags textarea

"Run" spawns `da` with those args, streams to console, auto-reloads graph when done.

Individual ADR toggles in the sidebar also persist so the next rerun reflects the state.

---

## Ability b: kata requirements

Kata tab toggle list + full editor overlay covers this.

Future: drag-and-drop requirement reordering, requirement-to-gate tracing (which gates
exist because of which requirement).

---

## Data reads (server → disk)

| Endpoint               | File(s) read                                          |
|------------------------|-------------------------------------------------------|
| GET /api/flows         | ls flows/                                             |
| GET /api/flow/:name    | flows/:name/graph.json, gates/*/spec.json, flows/:name/diary.md, katas/:name.md |
| GET /api/adrs          | adrs/*.md                                             |
| GET /api/history/:name | git log flows/:name/graph.json                        |
| GET /api/history/:name/:hash | git show hash:flows/:name/graph.json            |

---

## Data writes

| Action            | Write                                         |
|-------------------|-----------------------------------------------|
| Toggle ADR        | rename adrs/X.md ↔ adrs/X.md.disabled        |
| Save kata         | overwrite katas/:name.md                      |
| Restore version   | overwrite flows/:name/graph.json (with git show) |
| Run `da`          | subprocess — writes to gates/, flows/         |

---

## Tech decisions

**Why Node.js + Express?**
- WebSocket + file watch + child_process in one runtime, no build step
- npm install; node server.js — zero friction

**Why Cytoscape.js?**
- Best Rust/Python-independent graph library
- Dagre layout works well for DAGs (flow graphs)
- Click/zoom/highlight API is well-documented

**Why single HTML file?**
- No bundler, no React, no build step
- Paste into any browser, works offline

**No database.** Files are the source of truth. Server is stateless.

---

## Open questions (decisions needed before building)

1. **Twin integration**: spawn `da-twin` directly or call Python `opis-twin/server.py`?
   Currently two separate Monte Carlo engines exist. Unify or keep both?

2. **Requirement tracing**: should the server try to map kata requirements → gates
   (which gate exists because of which sentence)? FA doesn't produce this today.

3. **Multi-flow view**: show multiple flows side-by-side or one at a time?
   Current design is one flow at a time with a dropdown.

4. **ADR editor**: read-only in the sidebar (click-through to file), or editable inline?

5. **Diagram export**: PNG/SVG export of the graph for slides/docs?

---

## Build order

1. Server (file reads + WebSocket spawn)
2. Graph rendering (Cytoscape, dagre, node colours)
3. Gate detail panel + edge highlight
4. ADR sidebar + gate linking
5. Iteration diary rendering
6. Kata toggle + edit overlay
7. History tab + visual restore
8. Twin sidebar
9. Run options sheet
10. Visual diff between versions
