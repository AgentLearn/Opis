# da-diagram — Architecture

Three layers: browser, server, file system. No database. Files are the source of truth.

---

## Layers

### Browser (`public/index.html`)

Single HTML file, no bundler. Four UI regions:

| Region | Responsibility |
|--------|---------------|
| Graph panel | Cytoscape.js + dagre; renders gates/edges from graph.json; click → detail panel; double-click → gate zoom; visual diff between git commits |
| Left sidebar | ADR cards (toggle active/disabled, gate linking); Kata toggle list + full text editor; History (git log, restore) |
| Right sidebar | Iterations (diary.md parsed into repair-cycle cards); Twin (fire%, p50/p95 per gate, run button) |
| Console + toolbar | Live `da` stdout/stderr via WebSocket; flow selector; rerun options sheet (backend, model, loop count) |

Browser talks to the server via REST (data) and WebSocket (live subprocess output + push updates).

---

### Server (`server.js`)

Node.js + Express + WebSocket + chokidar. Stateless — no in-memory state survives between requests.

**REST API (reads):**

| Endpoint | Reads |
|----------|-------|
| `GET /api/flows` | `ls flows/` |
| `GET /api/flow/:name` | `flows/:name/graph.json`, `gates/*/spec.json`, `flows/:name/diary.md`, `katas/:name.md` |
| `GET /api/adrs` | `adrs/*.md` (skips `*.md.disabled`) |
| `GET /api/history/:name` | `git log --follow flows/:name/graph.json` |
| `GET /api/history/:name/:hash` | `git show hash:flows/:name/graph.json` |

**REST API (writes):**

| Action | Write |
|--------|-------|
| Toggle ADR | rename `adrs/X.md` ↔ `adrs/X.md.disabled` |
| Save kata | overwrite `katas/:name.md` |
| Restore version | `git show hash:flows/:name/graph.json` → overwrite `flows/:name/graph.json` |

**WebSocket hub:**
- Spawns `da` or `da-twin` as a child process on demand
- Streams stdout/stderr to all connected browser tabs in real time
- On process exit, triggers a graph reload

**File watcher (chokidar):**
- Watches `gates/`, `flows/`, `adrs/`
- On any file change → broadcasts `{type: "graph_update"}` to all open tabs
- Browser re-fetches `/api/flow/:name` and re-renders — no manual refresh needed

---

### File system (`agent/`)

All persistent state lives here. Server reads on every request (no caching).

| Path | Written by | Read for |
|------|-----------|---------|
| `gates/*/spec.json` | GA (gate agent) | graph nodes, detail panel |
| `flows/*/graph.json` | FA (flow agent), compose, repair | topology, edges, sources |
| `flows/*/diary.md` | FA | iteration sidebar |
| `adrs/*.md` | da-adr / user | ADR sidebar, FA context |
| `katas/*.md` | user / server (save kata) | kata sidebar |
| `git log` | git | history tab, visual diff |

---

## Data flow — page load

```
Browser                    Server                       Disk
  │                          │                            │
  ├─ GET /api/flow/:name ───▶│                            │
  │                          ├─ read graph.json ─────────▶│
  │                          ├─ read gates/*/spec.json ──▶│
  │                          ├─ read diary.md ───────────▶│
  │                          ├─ read katas/:name.md ─────▶│
  │◀─ JSON response ─────────┤                            │
  │                          │                            │
  ├─ render Cytoscape graph  │                            │
  ├─ populate sidebars       │                            │
```

---

## Data flow — rerun

```
Browser                    Server                       Disk / subprocess
  │                          │                            │
  ├─ WS: {cmd:"run", args}──▶│                            │
  │                          ├─ spawn da [args] ─────────▶│
  │                          │◀─ stdout/stderr (stream) ──│
  │◀─ WS: {type:"log"} ──────┤                            │
  │  (console updates live)  │                            │
  │                          │◀─ process exit ────────────│
  │                          ├─ chokidar detects changes  │
  │◀─ WS:{type:"graph_update"}│                           │
  ├─ GET /api/flow/:name ───▶│                            │
  │◀─ fresh graph ───────────┤                            │
  ├─ re-render graph         │                            │
```

---

## Key decisions

**Node.js** — WebSocket + chokidar + child_process in one runtime, no build step. `npm install; node server.js`.

**Cytoscape.js** — best graph library without a Rust/Python dependency. Dagre layout handles DAGs well. Zoom/highlight/click API is documented.

**Single HTML file** — no bundler, no React, works offline. Paste into any browser.

**Stateless server** — files are the only state. Server restart loses nothing. Concurrent tabs always read fresh data.

**No database** — adds no infrastructure. The agent directory is already the canonical store.

---

## Open questions

1. **Twin integration** — spawn `da-twin` directly or wrap Python `opis-twin`? Two Monte Carlo engines exist; unify or keep both?
2. **Requirement tracing** — map kata sentences → gates? FA doesn't produce this today.
3. **Multi-flow** — one flow at a time (dropdown) vs. side-by-side?
4. **ADR editor** — read-only sidebar or inline edit?
5. **Diagram export** — PNG/SVG for slides/docs?
