/* Domain expert FACE (kata v3 REQ-29..34) — v0.
   Same actions catalog as the architect's console, different rendering:
   no graph, plain-words chrome ("decision", "choice", "running work").
   Deciding here writes through the SAME single decision-recording path;
   the record does not know which face produced it (REQ-32).
   BOUNDED COVERAGE (DDR-004): the chrome is plain-worded, but the
   decision PROSE is shown verbatim and may contain engineer terms —
   true plain-language translation needs the model channel, deferred.
   Scenarios-in-story-terms likewise deferred (same reason). */

const app = document.getElementById("app");
const KATA = new URLSearchParams(location.search).get("kata") || "opis_workbench";

const el = (tag, style, text) => {
  const e = document.createElement(tag);
  if (style) e.style.cssText = style;
  if (text) e.textContent = text;
  return e;
};

const loud = (msg) => {
  const b = el("div",
    "background:#f7e6e4;border:1px solid #e0b4ae;color:#a32d2d;" +
    "border-radius:8px;padding:12px 16px;margin:12px 0;white-space:pre-wrap");
  b.textContent = "Something went wrong — here is exactly what happened:\n\n" + msg;
  app.prepend(b);
};

const api = async (path, opts) => {
  const r = await fetch(path, opts);
  const j = await r.json();
  if (!r.ok || j.error) throw new Error(j.traceback || j.error || r.status);
  return j;
};

const card = () => el("div",
  "background:#fff;border:1px solid #dbd8ce;border-radius:10px;" +
  "padding:16px 20px;margin:14px 0");

const btn = (label) => {
  const b = el("button",
    "margin:4px 8px 4px 0;padding:7px 14px;border:1px solid #c8c5bb;" +
    "border-radius:8px;background:none;font-size:14px;cursor:pointer");
  b.textContent = label;
  b.onmouseenter = () => b.style.background = "#eceade";
  b.onmouseleave = () => b.style.background = "none";
  return b;
};

async function render() {
  app.textContent = "";
  app.append(el("h1", "font-size:20px;font-weight:500;margin:8px 0 2px",
    "Decisions waiting for you"));
  app.append(el("p", "color:#5f5e5a;margin:0 0 8px;font-size:13px",
    "The system asks, you decide, it remembers why."));

  let pending = [];
  try { pending = (await api(`/api/adr_pending?kata=${KATA}`)).pending; }
  catch (e) { loud(e.message); return; }

  if (!pending.length) {
    const c = card();
    c.append(el("p", "margin:0;color:#5f5e5a",
      "Nothing needs a decision right now."));
    app.append(c);
  }

  for (const p of pending) {
    const c = card();
    c.append(el("h2", "font-size:16px;font-weight:500;margin:0 0 8px",
      p.title.replace(/^ADR-\d+:\s*/i, "").replace(/^\w/, ch => ch.toUpperCase())));
    c.append(el("p", "white-space:pre-wrap;font-size:14px;color:#3a3936",
      p.context.slice(0, 600)));
    c.append(el("p", "font-size:13px;color:#5f5e5a",
      "Your choices — open one to read what it would mean:"));
    for (const o of p.options) {
      const d = el("details", "margin:6px 0");
      const s = el("summary", "cursor:pointer;font-size:14px",
        `Choice ${o.label} — ${o.text.split("\n")[0].slice(0, 90)}`);
      d.append(s);
      d.append(el("pre",
        "white-space:pre-wrap;font-size:13px;background:#f1efe8;" +
        "border-radius:6px;padding:10px;font-family:inherit", o.text));
      c.append(d);
    }
    const why = el("input",
      "width:100%;box-sizing:border-box;margin:8px 0 4px;padding:7px 10px;" +
      "border:1px solid #c8c5bb;border-radius:8px;font-size:14px");
    why.placeholder = "Why? (optional — but the system remembers it forever)";
    c.append(why);
    const row = el("div");
    for (const o of p.options) {
      const b = btn(`I choose ${o.label}`);
      b.onclick = async () => {
        b.disabled = true; b.textContent = "recording…";
        try {
          await api("/api/adr_decide", { method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ kata: KATA, file: p.file,
              choice: o.label, rationale: why.value.trim() }) });
          render();
        } catch (e) { loud(e.message); b.disabled = false; b.textContent = `I choose ${o.label}`; }
      };
      row.append(b);
    }
    const rej = btn("None of these");
    rej.onclick = async () => {
      if (!why.value.trim()) {
        loud("Saying no to every choice needs a reason in the 'Why?' box — " +
             "the system never records a silent no.");
        return;
      }
      try {
        await api("/api/adr_decide", { method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ kata: KATA, file: p.file,
            choice: "reject", rationale: why.value.trim() }) });
        render();
      } catch (e) { loud(e.message); }
    };
    row.append(rej);
    c.append(row);
    app.append(c);
  }

  app.append(el("h1", "font-size:20px;font-weight:500;margin:24px 0 8px",
    "Running work"));
  const rc = card();
  try {
    let any = false;
    for (const agent of ["fa", "ca"]) {
      const s = await api(`/api/run/status?kata=${KATA}&agent=${agent}`);
      if (s.running) {
        any = true;
        const sp = s.spend;
        rc.append(el("p", "margin:4px 0",
          `The ${agent === "fa" ? "designer" : "builder"} is working — ` +
          `${sp.calls} step(s) so far. Still running.`));
      }
    }
    if (!any) rc.append(el("p", "margin:4px 0;color:#5f5e5a",
      "Nothing is running right now."));
  } catch (e) { loud(e.message); }
  app.append(rc);

  app.append(el("p", "color:#888780;font-size:12px;margin-top:20px",
    "Trying out a story of your own before deciding is coming — it needs " +
    "the translation layer, and we would rather say 'not yet' than fake it."));
}

render();
setInterval(async () => { /* refresh running-work quietly */
  try { render(); } catch (e) { /* loud already shown by render */ }
}, 20000);
