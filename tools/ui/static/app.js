/* opis workbench — Lit front end over the actions catalog.
   FACE only: renders recorded facts, decides nothing itself, holds no
   DOMAIN state (actions/faces boundary, 2026-07-12). View-state (theme,
   pane) is client-local per DDR-002. See tools/ui/DECISIONS.md.
   PRIME principle: every claim shown is a door into its evidence.
   Hand-built golden recipe; provenance: 2026-07-12 interactive session. */

import { LitElement, html, css } from "https://cdn.jsdelivr.net/gh/lit/dist@3/core/lit-core.min.js";

const api = async (path, opts) => {
  const r = await fetch(path, opts);
  const j = await r.json();
  if (!r.ok) throw new Error(j.traceback || j.error || r.status);
  if (j.error) throw new Error(j.error);
  return j;
};
const post = (path, body) => api(path, { method: "POST",
  headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

/* DDR-002: named palette tokens — one source for CSS and graph style. */
const PALETTES = {
  dark: {
    bg: "#141413", text: "#e8e6e0", mutetext: "#b8b5ad", dimtext: "#8a877e",
    border: "#333", chipborder: "#3a3a38", panel: "#1b1b1a", panelborder: "#2e2e2c",
    selbg: "#1d2a25", selborder: "#6a9c89", okbg: "#1d2a25", oktext: "#8fc7a6",
    okborder: "#2e5c46", badbg: "#2a1d1d", badtext: "#d99", badborder: "#5c2e2e",
    gatefill: "#26262a", gateborder: "#4a4a52", locusfill: "#1d2530",
    locusborder: "#3d5a73", srcborder: "#6a8caf", edge: "#3a3a3e",
    edgehidden: "#2c2c2e", edgefail: "#a95a52", pathfill: "#1d3a2d",
    pathborder: "#4f9e78", edgelabel: "#8a877e", hoverbg: "#222",
    addfill: "#1d3a2d", addborder: "#4f9e78",
  },
  light: {
    bg: "#faf9f5", text: "#1f1e1b", mutetext: "#5f5e5a", dimtext: "#888780",
    border: "#d5d2c8", chipborder: "#c8c5bb", panel: "#f1efe8", panelborder: "#dbd8ce",
    selbg: "#e1f0e8", selborder: "#2e7d5b", okbg: "#e1f0e8", oktext: "#0f6e4d",
    okborder: "#9ccdb5", badbg: "#f7e6e4", badtext: "#a32d2d", badborder: "#e0b4ae",
    gatefill: "#ffffff", gateborder: "#b4b2a9", locusfill: "#e6f0f8",
    locusborder: "#7ba7c9", srcborder: "#2f6b9e", edge: "#c0bdb3",
    edgehidden: "#e7e4da", edgefail: "#c2604f", pathfill: "#d7ecdd",
    pathborder: "#1d7a4f", edgelabel: "#5f5e5a", hoverbg: "#eceade",
    addfill: "#d7ecdd", addborder: "#1d7a4f",
  },
};

const VERDICT_CLASS = { proved: "ok", passed: "ok", bounded: "warn",
  flagged: "bad", failed: "bad" };

class OpisWorkbench extends LitElement {
  static properties = {
    katas: { state: true }, kata: { state: true }, spec: { state: true },
    selReq: { state: true }, witness: { state: true }, gateInfo: { state: true },
    nonHappy: { state: true }, console_: { state: true }, busy: { state: true },
    theme: { state: true }, mode: { state: true },
    evidenceData: { state: true }, pendingAdrs: { state: true },
    decidedAdrs: { state: true }, diffData: { state: true },
    versions: { state: true }, whatif: { state: true },
    runStatus: { state: true }, whatifText: { state: true },
  };

  static styles = css`
    :host{display:grid;height:100vh;
      background:var(--bg);color:var(--text);
      grid-template-columns:290px 1fr 360px;
      grid-template-rows:1fr 180px;
      grid-template-areas:"rail center drawer" "rail console drawer"}
    .rail{grid-area:rail;overflow-y:auto;border-right:1px solid var(--border);
      padding:12px;box-sizing:border-box}
    .center{grid-area:center;position:relative;overflow-y:auto}
    #cy{position:absolute;inset:0}
    .pane{padding:14px 18px;box-sizing:border-box}
    .drawer{grid-area:drawer;overflow-y:auto;border-left:1px solid var(--border);
      padding:12px;box-sizing:border-box}
    .console{grid-area:console;overflow-y:auto;border-top:1px solid var(--border);
      padding:8px 12px;box-sizing:border-box;font:12px/1.45 ui-monospace,monospace;
      white-space:pre-wrap;color:var(--mutetext)}
    h1{font-size:15px;font-weight:500;margin:0 0 10px}
    h2{font-size:13px;font-weight:500;margin:14px 0 6px;color:var(--mutetext)}
    .req,.nav{display:block;width:100%;text-align:left;margin:2px 0;padding:4px 8px;
      background:none;border:1px solid var(--chipborder);border-radius:6px;
      color:var(--text);font-size:12px;cursor:pointer}
    .req:hover,.nav:hover{border-color:var(--dimtext)}
    .req.sel,.nav.sel{border-color:var(--selborder);background:var(--selbg)}
    button.run,button.theme,button.act{margin:2px 4px 2px 0;padding:4px 10px;
      background:none;border:1px solid var(--chipborder);border-radius:6px;
      color:var(--text);cursor:pointer;font-size:12px}
    button.run:hover,button.theme:hover,button.act:hover{background:var(--hoverbg)}
    label{font-size:12px;color:var(--mutetext);display:block;margin:8px 0}
    pre{white-space:pre-wrap;font:11px/1.4 ui-monospace,monospace;
      background:var(--panel);border:1px solid var(--panelborder);
      border-radius:6px;padding:8px}
    textarea,input[type=text]{width:100%;box-sizing:border-box;
      background:var(--panel);color:var(--text);font:11px/1.4 ui-monospace,monospace;
      border:1px solid var(--chipborder);border-radius:6px;padding:6px}
    .pill{display:inline-block;font-size:11px;padding:1px 8px;border-radius:8px;
      margin:0 6px 4px 0}
    .ok{background:var(--okbg);color:var(--oktext);border:1px solid var(--okborder)}
    .bad{background:var(--badbg);color:var(--badtext);border:1px solid var(--badborder)}
    .warn{background:var(--panel);color:var(--mutetext);border:1px solid var(--chipborder)}
    select{background:var(--panel);color:var(--text);
      border:1px solid var(--chipborder);border-radius:6px;padding:4px}
    select.kata{width:100%}
    .card{border:1px solid var(--panelborder);border-radius:8px;
      padding:10px 12px;margin:8px 0;background:var(--panel)}
    .claim{border-bottom:1px solid var(--panelborder);padding:6px 0;font-size:12px}
    .cols{display:grid;grid-template-columns:1fr 1fr;gap:12px}
    .added{color:var(--oktext)}
    .removed{color:var(--badtext)}
    details{font-size:12px;margin:4px 0}
    summary{cursor:pointer;color:var(--mutetext)}
  `;

  constructor() {
    super();
    Object.assign(this, {
      katas: [], kata: null, spec: null, selReq: null, witness: null,
      gateInfo: null, nonHappy: false, busy: false, mode: "graph",
      evidenceData: null, pendingAdrs: null, decidedAdrs: null,
      diffData: null, versions: [], whatif: {}, runStatus: {},
      whatifText: "",
      console_: "workbench ready — all reads happen at click time.",
    });
    this.theme = localStorage.getItem("opis-ui-theme") || "dark";
  }

  get pal() { return PALETTES[this.theme]; }

  applyTheme() {
    for (const [k, v] of Object.entries(this.pal))
      this.style.setProperty(`--${k}`, v);
    document.body.style.background = this.pal.bg;
    localStorage.setItem("opis-ui-theme", this.theme);
  }

  toggleTheme() {
    this.theme = this.theme === "dark" ? "light" : "dark";
    this.applyTheme();
    if (this.cy) this.cy.style(this.cyStyle());
  }

  async firstUpdated() {
    this.applyTheme();
    cytoscape.use(cytoscapeDagre);
    const k = await api("/api/katas");
    this.katas = k.katas;
    if (this.katas.length) this.loadKata(this.katas[this.katas.length - 1].kata);
  }

  async loadKata(name) {
    this.kata = name; this.selReq = null; this.gateInfo = null;
    this.witness = null; this.diffData = null; this.evidenceData = null;
    this.pendingAdrs = null;
    const f = await api(`/api/flow?kata=${name}`);
    this.spec = f.spec;
    this.versions = (await api(`/api/flow_versions?kata=${name}`)).versions;
    if (this.mode === "graph") this.updateComplete.then(() => this.drawGraph());
    else this.setMode(this.mode, true);
  }

  async setMode(m, force = false) {
    if (m === this.mode && !force && m !== "graph") return;
    this.mode = m;
    this.stopPoll();
    if (m === "graph") {
      this.updateComplete.then(() => this.drawGraph());
    } else if (m === "evidence") {
      this.evidenceData = (await api(`/api/evidence?kata=${this.kata}`));
    } else if (m === "decisions") {
      this.pendingAdrs = (await api(`/api/adr_pending?kata=${this.kata}`)).pending;
      const all = (await api(`/api/adrs?kata=${this.kata}`)).adrs;
      this.decidedAdrs = all.filter(a =>
        !this.pendingAdrs.some(p => p.file === a.file));
    } else if (m === "diff") {
      if (this.versions.length >= 2) {
        const [a, b] = this.versions.slice(-2);
        await this.loadDiff(a, b);
      }
    } else if (m === "whatif") {
      if (!this.whatifText)
        this.whatifText = JSON.stringify(this.spec, null, 1);
    } else if (m === "runs") {
      this.pollRuns();
      this.pollTimer = setInterval(() => this.pollRuns(), 4000);
    }
  }

  stopPoll() { if (this.pollTimer) { clearInterval(this.pollTimer); this.pollTimer = null; } }

  /* ── graph ─────────────────────────────────────────────────────────── */

  cyStyle() {
    const p = this.pal;
    return [
      { selector: "node", style: { label: "data(label)", "font-size": 9,
        color: p.text, "text-valign": "center", "text-halign": "center",
        "text-wrap": "wrap", "text-max-width": 90, width: 100, height: 34,
        shape: "round-rectangle", "background-color": p.gatefill,
        "border-width": 1, "border-color": p.gateborder } },
      { selector: "node[kind != 'gate']", style: { shape: "ellipse",
        "background-color": p.locusfill, "border-color": p.locusborder,
        width: 84, height: 44 } },
      { selector: "node[?src]", style: { "border-width": 2, "border-color": p.srcborder } },
      { selector: "edge", style: { width: 1, "curve-style": "bezier",
        "line-color": p.edge, "target-arrow-color": p.edge,
        "target-arrow-shape": "triangle", "arrow-scale": 0.7,
        "font-size": 7, color: p.edgelabel } },
      { selector: "edge[?failure]", style: { "line-style": "dashed",
        "line-color": this.nonHappy ? p.edgefail : p.edgehidden,
        "target-arrow-color": this.nonHappy ? p.edgefail : p.edgehidden } },
      { selector: ".onpath", style: { "background-color": p.pathfill,
        "border-color": p.pathborder, "border-width": 2 } },
      { selector: "edge.onpath", style: { "line-color": p.pathborder,
        "target-arrow-color": p.pathborder, width: 2.5 } },
      { selector: ".vadded", style: { "background-color": p.addfill,
        "border-color": p.addborder, "border-width": 3 } },
      { selector: "edge.vadded", style: { "line-color": p.addborder,
        "target-arrow-color": p.addborder, width: 2.5, "line-style": "solid" } },
      { selector: ".dim", style: { opacity: 0.18 } },
    ];
  }

  drawGraph() {
    const container = this.renderRoot.getElementById("cy");
    if (!container || !this.spec) return;
    const s = this.spec, els = [];
    for (const [n, l] of Object.entries(s.loci))
      els.push({ data: { id: n, label: n, kind: l.kind || "locus", src: !!l.source } });
    for (const [n, g] of Object.entries(s.gates))
      els.push({ data: { id: n, label: n, kind: "gate", template: g.gate_template } });
    s.synapses.forEach((sy, i) => els.push({
      data: { id: `e${i}`, source: sy.from, target: sy.to, label: sy.pulse_type,
              synkey: `${sy.from} -> ${sy.to} [${sy.pulse_type}]`,
              failure: /failure|notification/.test(sy.pulse_type) ? 1 : 0 } }));
    this.cy = cytoscape({
      container, elements: els, wheelSensitivity: 0.2,
      layout: { name: "dagre", rankDir: "LR", nodeSep: 18, rankSep: 90 },
      style: this.cyStyle(),
    });
    this.cy.on("zoom", () => {
      const show = this.cy.zoom() > 1.1;
      this.cy.edges().forEach(e => e.style("label", show ? e.data("label") : ""));
    });
    this.cy.on("tap", "node[kind = 'gate']", ev => this.openGate(ev.target.id()));
    this.cy.on("tap", ev => { if (ev.target === this.cy) this.clearPath(); });
    if (this.pendingDiffHighlight) { this.highlightDiff(); }
  }

  clearPath() {
    this.selReq = null; this.witness = null;
    this.cy.elements().removeClass("onpath dim vadded");
  }

  async selectReq(r) {
    if (this.mode !== "graph") await this.setMode("graph");
    this.selReq = r.id;
    this.log(`prover re-deriving ${r.id} (never cached)…`);
    const w = await api(`/api/witness?kata=${this.kata}&req_id=${r.id}`);
    this.witness = w.results[0];
    const nodes = new Set(), edges = [];
    for (const path of Object.values(this.witness?.proofs || {})) {
      let prev = null;
      for (const hop of path) {
        const n = hop.node || hop;
        nodes.add(n);
        if (prev) edges.push([prev, n]);
        prev = n;
      }
      const tgt = r.target?.gate;
      if (prev && tgt) { edges.push([prev, tgt]); nodes.add(tgt); }
    }
    this.cy.elements().addClass("dim").removeClass("onpath");
    nodes.forEach(n => this.cy.getElementById(n).removeClass("dim").addClass("onpath"));
    edges.forEach(([a, b]) => this.cy.edges(`[source = "${a}"][target = "${b}"]`)
      .removeClass("dim").addClass("onpath"));
    const issues = this.witness?.issues || [];
    this.log(issues.length
      ? `${r.id} UNPROVED:\n` + issues.join("\n")
      : `${r.id} proved — ${Object.keys(this.witness?.proofs || {}).length} input path(s) drawn.`);
  }

  async openGate(name) {
    this.gateInfo = { loading: name };
    this.gateInfo = await api(`/api/gate?kata=${this.kata}&name=${name}`);
  }

  async runVerifier(which) {
    this.busy = which;
    this.log(`running ${which} against current workspace state…`);
    try {
      const r = await post(`/api/run/${which}?kata=${this.kata}`, {});
      this.log(`$ ${r.cmd}\n[exit ${r.exit}]\n${r.output}`);
    } catch (e) { this.log(`FAILED (loud):\n${e.message}`); }
    this.busy = false;
  }

  toggleNonHappy(e) {
    this.nonHappy = e.target.checked;
    if (this.cy) this.cy.style(this.cyStyle());
  }

  log(t) { this.console_ = t; }

  /* ── diff ──────────────────────────────────────────────────────────── */

  async loadDiff(a, b) {
    this.diffData = await api(
      `/api/flow_diff?kata=${this.kata}&v_from=${a}&v_to=${b}`);
  }

  highlightDiff() {
    this.pendingDiffHighlight = false;
    const d = this.diffData;
    if (!d || !this.cy) return;
    this.cy.elements().addClass("dim").removeClass("vadded onpath");
    [...d.gates.added, ...d.loci.added].forEach(n =>
      this.cy.getElementById(n).removeClass("dim").addClass("vadded"));
    d.synapses.added.forEach(k => {
      const e = this.cy.edges(`[synkey = "${k}"]`);
      e.removeClass("dim").addClass("vadded");
      e.connectedNodes().removeClass("dim");
    });
    this.log(`diff v${d.from} → v${d.to} on graph: ` +
      `+${d.gates.added.length} gates, +${d.loci.added.length} loci, ` +
      `+${d.synapses.added.length} synapses (green). Tap background to clear.`);
  }

  showDiffOnGraph() {
    if (this.diffData?.to !== this.spec?.version) {
      this.log("on-graph highlight needs the diff target to be the current version.");
      return;
    }
    this.pendingDiffHighlight = true;
    this.setMode("graph");
  }

  /* ── decisions ─────────────────────────────────────────────────────── */

  async decide(card, choice) {
    const box = this.renderRoot.getElementById(`rat-${card.file}`);
    const rationale = box ? box.value.trim() : "";
    if ((choice === "reject" || choice === "own") && !rationale) {
      this.log(`'${choice}' needs text in the rationale box — nothing recorded.`);
      return;
    }
    try {
      const r = await post("/api/adr_decide", {
        kata: this.kata, file: card.file, choice, rationale });
      this.log(`${card.file}: ${r.decided} recorded.\n${r.note}`);
      await this.setMode("decisions", true);
    } catch (e) { this.log(`decide FAILED (loud):\n${e.message}`); }
  }

  /* ── what-if ───────────────────────────────────────────────────────── */

  async runWhatif(label) {
    let spec;
    try { spec = JSON.parse(this.renderRoot.getElementById("whatif-src").value); }
    catch (e) { this.log(`what-if ${label}: spec is not valid JSON — ${e.message}`); return; }
    this.busy = `whatif${label}`;
    this.log(`what-if ${label}: eval + prover on a scratch copy (ephemeral)…`);
    try {
      const r = await post("/api/whatif", { kata: this.kata, spec, label });
      this.whatif = { ...this.whatif, [label]: r };
      this.log(`what-if ${label} done — eval exit ${r.summary.eval_exit}, ` +
        `${r.summary.proved}/${r.summary.proved + r.summary.unproved} proved.\n\n` +
        `${r.proof.output.split("\n").slice(-6).join("\n")}`);
    } catch (e) { this.log(`what-if ${label} FAILED (loud):\n${e.message}`); }
    this.busy = false;
  }

  /* ── runs ──────────────────────────────────────────────────────────── */

  async pollRuns() {
    for (const agent of ["fa", "ca"]) {
      try {
        this.runStatus = { ...this.runStatus,
          [agent]: await api(`/api/run/status?kata=${this.kata}&agent=${agent}`) };
      } catch (e) { /* status poll failures land in console on demand */ }
    }
  }

  async startRun(agent) {
    try {
      const r = await post("/api/run/start", { kata: this.kata, agent });
      this.log(`${agent} run started (pid ${r.pid}) → ${r.log}\n${r.note}`);
      this.pollRuns();
    } catch (e) { this.log(`start FAILED (loud):\n${e.message}`); }
  }

  async stopRun(agent) {
    try {
      const r = await post("/api/run/stop", { kata: this.kata, agent });
      this.log(`${agent} run stopped (exit ${r.exit}).\n${r.note}`);
      this.pollRuns();
    } catch (e) { this.log(`stop FAILED (loud):\n${e.message}`); }
  }

  /* ── render ────────────────────────────────────────────────────────── */

  render() {
    const reqs = this.spec?.requirements || [];
    const modes = ["graph", "evidence", "decisions", "diff", "whatif", "runs"];
    return html`
      <div class="rail">
        <h1>opis workbench</h1>
        <select class="kata" @change=${e => this.loadKata(e.target.value)}>
          ${this.katas.map(k => html`<option ?selected=${k.kata === this.kata}>${k.kata}</option>`)}
        </select>
        <button class="theme" @click=${this.toggleTheme}
          title="view-state only — stays in this browser (DDR-002)">
          ${this.theme === "dark" ? "light" : "dark"} theme</button>
        <h2>view</h2>
        ${modes.map(m => html`
          <button class="nav ${this.mode === m ? "sel" : ""}"
            @click=${() => this.setMode(m)}>${m}</button>`)}
        <h2>flow ${this.spec ? `v${this.spec.version}` : ""} — ${reqs.length} requirements</h2>
        <label><input type="checkbox" .checked=${this.nonHappy}
          @change=${this.toggleNonHappy}> show non-happy branches</label>
        ${reqs.map(r => html`
          <button class="req ${this.selReq === r.id ? "sel" : ""}"
            title=${r.text} @click=${() => this.selectReq(r)}>
            ${r.id} — ${r.text.slice(0, 52)}…</button>`)}
        <h2>verifiers (fresh result supersedes display)</h2>
        ${["eval", "proof", "regress", "lint"].map(v => html`
          <button class="run" ?disabled=${this.busy}
            @click=${() => this.runVerifier(v)}>${this.busy === v ? "…" : v}</button>`)}
      </div>

      <div class="center">${this.renderCenter()}</div>

      <div class="drawer">
        ${this.gateInfo ? this.renderGate() : html`
          <h2>drill-down</h2>
          <p style="font-size:12px;color:var(--dimtext)">Tap a gate for its
          pinned contract, hash verification, and lint state. Select a
          requirement to draw its witness path — re-derived by the prover
          at click time, never replayed from a cached claim.</p>`}
      </div>

      <div class="console">${this.console_}</div>`;
  }

  renderCenter() {
    switch (this.mode) {
      case "evidence": return this.renderEvidence();
      case "decisions": return this.renderDecisions();
      case "diff": return this.renderDiff();
      case "whatif": return this.renderWhatif();
      case "runs": return this.renderRuns();
      default: return html`<div id="cy"></div>`;
    }
  }

  renderEvidence() {
    const e = this.evidenceData;
    if (!e) return html`<div class="pane">loading…</div>`;
    if (!e.evidence) return html`<div class="pane"><h1>no evidence report yet</h1></div>`;
    const ev = e.evidence;
    const claims = [];
    for (const layer of ["static", "twin", "cosim"])
      for (const c of ev[layer]?.claims || ev[layer] || [])
        if (c.claim) claims.push({ ...c, layer });
    const flat = claims.length ? claims : (ev.claims || []);
    const caveats = ev.caveats || ev.verdict?.caveats || [];
    return html`<div class="pane">
      <h1>${e.file} — ${ev.provenance?.flow} </h1>
      ${caveats.length ? html`<div class="card">
        <h2 style="margin-top:0">caveats (same prominence as proofs — doctrine)</h2>
        ${caveats.map(c => html`<div class="claim">${typeof c === "string" ? c : JSON.stringify(c)}</div>`)}
      </div>` : ""}
      <h2>claims — every one a pointer, pointerless claims are not rendered as fact</h2>
      ${flat.map(c => html`
        <div class="claim">
          <span class="pill ${VERDICT_CLASS[c.verdict] || "warn"}">${c.verdict}</span>
          <span class="pill warn">${c.scope || c.layer || "?"}</span>
          ${c.claim}
          ${c.evidence ? html`<details><summary>evidence pointer</summary>
            <pre>${typeof c.evidence === "string" ? c.evidence : JSON.stringify(c.evidence, null, 1)}</pre>
          </details>` : html`<span class="pill bad">NO POINTER — not fact</span>`}
        </div>`)}
      <h2>provenance</h2>
      <pre>${JSON.stringify(ev.provenance, null, 1)}</pre>
    </div>`;
  }

  renderDecisions() {
    const pend = this.pendingAdrs;
    if (pend === null) return html`<div class="pane">loading…</div>`;
    return html`<div class="pane">
      <h1>decisions</h1>
      ${pend.length === 0 ? html`<p style="font-size:13px;color:var(--dimtext)">
        No pending decisions. Decided records below — append-only, never dropped.</p>` : ""}
      ${pend.map(card => html`
        <div class="card">
          <h2 style="margin-top:0">${card.title}</h2>
          <pre style="white-space:pre-wrap">${card.context.slice(0, 800)}</pre>
          ${card.cites.length ? html`<div>cites:
            ${card.cites.map(c => html`<span class="pill warn">${c}</span>`)}
            <span style="font-size:11px;color:var(--dimtext)">(full text one pull away — decided list below)</span>
          </div>` : ""}
          ${card.options.map(o => html`
            <details><summary>Option ${o.label}</summary><pre>${o.text}</pre></details>`)}
          <input type="text" id="rat-${card.file}"
            placeholder="rationale (required for reject / own option)">
          <div style="margin-top:6px">
            ${card.options.map(o => html`
              <button class="act" @click=${() => this.decide(card, o.label)}>
                decide ${o.label}</button>`)}
            <button class="act" @click=${() => this.decide(card, "own")}>own option</button>
            <button class="act" @click=${() => this.decide(card, "reject")}>reject</button>
          </div>
          <p style="font-size:11px;color:var(--dimtext)">writes through
            agents/fa/adr.py — the same single path the CLI uses; the record
            does not know which face produced it (REQ-10/32).</p>
        </div>`)}
      <h2>decided (${(this.decidedAdrs || []).length})</h2>
      ${(this.decidedAdrs || []).map(a => html`
        <details><summary>${a.title} ${a.processed ? "· processed" : ""}</summary>
          <pre>${a.text}</pre></details>`)}
    </div>`;
  }

  renderDiff() {
    const d = this.diffData;
    const vs = this.versions;
    if (vs.length < 2) return html`<div class="pane">
      <h1>flow diff</h1><p style="font-size:13px">only one committed version — nothing to compare yet.</p></div>`;
    const sel = (id, def) => html`
      <select id=${id} @change=${() => this.loadDiff(
        this.renderRoot.getElementById("dv-a").value,
        this.renderRoot.getElementById("dv-b").value)}>
        ${vs.map(v => html`<option ?selected=${v === def}>${v}</option>`)}</select>`;
    const list = (title, obj) => html`
      <div class="card"><h2 style="margin-top:0">${title}
        <span class="added">+${obj.added.length}</span> /
        <span class="removed">−${obj.removed.length}</span>
        ${obj.changed ? html` / ~${obj.changed.length}` : ""}</h2>
      ${obj.added.map(x => html`<div class="claim added">+ ${x}</div>`)}
      ${obj.removed.map(x => html`<div class="claim removed">− ${x}</div>`)}
      ${(obj.changed || []).map(x => html`<div class="claim">~ ${x}</div>`)}
      </div>`;
    return html`<div class="pane">
      <h1>flow diff — the complexity gauge, explicit</h1>
      <div>from v${sel("dv-a", d ? d.from : vs[vs.length - 2])}
        to v${sel("dv-b", d ? d.to : vs[vs.length - 1])}
        <button class="act" @click=${this.showDiffOnGraph}>show on graph</button></div>
      ${d ? html`
        <p style="font-size:12px;color:var(--mutetext)">
          v${d.from}: ${d.counts.from.gates} gates / ${d.counts.from.synapses} synapses /
          ${d.counts.from.reqs} reqs → v${d.to}: ${d.counts.to.gates} gates /
          ${d.counts.to.synapses} synapses / ${d.counts.to.reqs} reqs</p>
        ${list("gates", d.gates)}
        ${list("loci", d.loci)}
        ${list("synapses", d.synapses)}
        ${list("requirements", d.requirements)}` : "pick versions"}
    </div>`;
  }

  renderWhatif() {
    const res = ["A", "B"].map(l => this.whatif[l]);
    return html`<div class="pane">
      <h1>what-if — verifiers only, scratch copy, ephemeral</h1>
      <p style="font-size:12px;color:var(--mutetext)">Edit the spec (preloaded
        with the current flow) and run it as A or B. Nothing here touches the
        recorded workspace — promotion stays the recorded channel (2026-07-08).</p>
      <textarea id="whatif-src" rows="14" .value=${this.whatifText}
        @input=${e => { this.whatifText = e.target.value; }}></textarea>
      <div style="margin:8px 0">
        <button class="act" ?disabled=${this.busy} @click=${() => this.runWhatif("A")}>
          ${this.busy === "whatifA" ? "…" : "run as A"}</button>
        <button class="act" ?disabled=${this.busy} @click=${() => this.runWhatif("B")}>
          ${this.busy === "whatifB" ? "…" : "run as B"}</button>
      </div>
      <div class="cols">
        ${["A", "B"].map((l, i) => html`<div class="card">
          <h2 style="margin-top:0">${l}</h2>
          ${res[i] ? html`
            <span class="pill ${res[i].summary.eval_exit ? "warn" : "ok"}">eval exit ${res[i].summary.eval_exit}</span>
            <span class="pill ${res[i].summary.unproved ? "bad" : "ok"}">
              ${res[i].summary.proved}/${res[i].summary.proved + res[i].summary.unproved} proved</span>
            <span class="pill warn">${res[i].summary.gates} gates / ${res[i].summary.synapses} synapses</span>
            <details><summary>full prover output (loud)</summary><pre>${res[i].proof.output}</pre></details>
            <details><summary>full eval output</summary><pre>${res[i].eval.output}</pre></details>`
          : html`<p style="font-size:12px;color:var(--dimtext)">not run</p>`}
        </div>`)}
      </div>
    </div>`;
  }

  renderRuns() {
    return html`<div class="pane">
      <h1>agent runs</h1>
      <p style="font-size:12px;color:var(--mutetext)">A run is a loop —
        iterations and spend shown as they land in the ledger. Pause is not
        offered: the agents have no iteration-boundary hook yet, and a button
        that kills mid-iteration would be an invented promise. Stop kills the
        process; the main line stays untouched.</p>
      ${["fa", "ca"].map(agent => {
        const s = this.runStatus[agent];
        return html`<div class="card">
          <h2 style="margin-top:0">${agent.toUpperCase()}
            ${s?.running ? html`<span class="pill ok">running · pid ${s.pid}</span>`
              : html`<span class="pill warn">idle${s?.exit != null ? ` · last exit ${s.exit}` : ""}</span>`}</h2>
          <button class="act" ?disabled=${s?.running}
            @click=${() => this.startRun(agent)}>start</button>
          <button class="act" ?disabled=${!s?.running}
            @click=${() => this.stopRun(agent)}>stop</button>
          ${s?.spend ? html`<p style="font-size:12px">
            spend since start: ${s.spend.calls} calls ·
            ${s.spend.input_tokens.toLocaleString()} in /
            ${s.spend.output_tokens.toLocaleString()} out
            ${Object.entries(s.spend.by_stage).map(([k, v]) =>
              html`<span class="pill warn">${k}×${v}</span>`)}</p>` : ""}
          ${s?.log_tail ? html`<details open><summary>log tail (live)</summary>
            <pre>${s.log_tail}</pre></details>` : ""}
        </div>`;
      })}
    </div>`;
  }

  renderGate() {
    const g = this.gateInfo;
    if (g.loading) return html`<h2>${g.loading}…</h2>`;
    if (g.error) return html`<h2>error</h2><pre>${g.error}</pre>`;
    return html`
      <h1>${g.gate}</h1>
      <div>
        <span class="pill ok">template ${g.template} v${g.pin?.version ?? "?"}</span>
        <span class="pill ${g.pin_hash_verified === false ? "bad" : "ok"}">
          pin ${g.pin_hash_verified === false ? "HASH MISMATCH" :
               g.pin_hash_verified ? "verified" : "unverified"}</span>
        <span class="pill ${g.lint.exit === 2 ? "bad" : "ok"}">
          lint ${g.lint.exit === 2 ? "findings" : "clean"}</span>
      </div>
      <h2>instance</h2><pre>${JSON.stringify(g.instance, null, 1)}</pre>
      ${g.lint.exit === 2 ? html`<h2>lint (advisory)</h2><pre>${g.lint.output}</pre>` : ""}
      <h2>contract — ${g.contract_file}</h2><pre>${g.contract_text}</pre>`;
  }
}

customElements.define("opis-workbench", OpisWorkbench);
