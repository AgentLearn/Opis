#!/usr/bin/env python3
"""
tools/ui/actions.py — the shared ACTIONS CATALOG (2026-07-12 boundary
decision): pure functions, typed-ish inputs, JSON-serializable outputs.
No HTTP, no rendering, no vocabulary. Every face (workbench, CLI, later
MCP) calls THESE; a face needing logic this catalog lacks means a new
action here, never face-side logic.

Every action is a thin wrapper over the EXISTING verifiers and workspace
files — no duplicated logic, no new state (2026-07-06 decision). All
truth stays in workspace git; every read happens at call time.

PROVENANCE: hand-built golden recipe (first-principle: agents build Opis
artifacts; this is the recipe a future CA translation reproduces). Built
in the 2026-07-12 interactive session against flow_v4 / kata v3 — the
proved actions catalog this module implements is flow_v4's gate surface.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = REPO_ROOT / "workspace"
GATES_DIR = REPO_ROOT / "agents" / "gates"
EVAL_DIR = REPO_ROOT / "tools" / "opis-eval"


def _load(name: str):
    """Import a module from tools/opis-eval (hyphenated dir, no package)."""
    path = EVAL_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"opis_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"opis_{name}"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _flow_path(kata: str) -> Path:
    flow_dir = WORKSPACE / kata / "flow"
    current = flow_dir / "flow_current.json"
    if current.exists():
        return current.resolve()
    versions = sorted(
        (int(m.group(1)), p)
        for p in flow_dir.glob("flow_v*.json")
        if (m := re.match(r"flow_v(\d+)$", p.stem))
    )
    if not versions:
        raise FileNotFoundError(f"no committed flow for kata '{kata}'")
    return versions[-1][1]


# ── queries ────────────────────────────────────────────────────────────────

def list_katas() -> dict:
    out = []
    if WORKSPACE.exists():
        for d in sorted(WORKSPACE.iterdir()):
            if d.is_dir() and (d / "flow").exists():
                try:
                    p = _flow_path(d.name)
                    spec = json.loads(p.read_text())
                    out.append({"kata": d.name, "flow_file": p.name,
                                "version": spec.get("version"),
                                "requirements": len(spec.get("requirements", []))})
                except FileNotFoundError:
                    continue
    return {"katas": out}


def flow(kata: str) -> dict:
    p = _flow_path(kata)
    spec = json.loads(p.read_text())
    return {"kata": kata, "flow_file": p.name, "spec": spec}


def witness(kata: str, req_id: str | None = None) -> dict:
    """Witness paths RE-DERIVED by the requirement prover at call time —
    never replayed from a cached claim (kata v2 REQ-4)."""
    p = _flow_path(kata)
    spec = json.loads(p.read_text())
    proof_mod = _load("proof")
    results = proof_mod.verify_requirements(spec, GATES_DIR)
    if req_id:
        results = [r for r in results if r.get("id") == req_id]
    return {"kata": kata, "flow_file": p.name, "derived_at_call": True,
            "results": results}


def gate(kata: str, name: str) -> dict:
    """Gate instance + its PINNED contract text, hash verification, and
    advisory lint findings — all resolved at call time."""
    p = _flow_path(kata)
    spec = json.loads(p.read_text())
    gspec = spec.get("gates", {}).get(name)
    if gspec is None:
        return {"error": f"gate '{name}' not in {p.name}", "loud": True}
    template = gspec.get("gate_template")
    pin = spec.get("pins", {}).get("gates", {}).get(template, {})
    pins_mod = _load("pins")

    contract_file = GATES_DIR / f"{template}.md"
    if hasattr(pins_mod, "contract_path"):
        try:
            contract_file = pins_mod.contract_path(template, pin.get("version"),
                                                   GATES_DIR)
        except TypeError:
            pass  # signature drift — fall back to current file
    text = contract_file.read_text() if contract_file.exists() else ""
    hash_ok = None
    if pin.get("hash") and hasattr(pins_mod, "file_hash") and contract_file.exists():
        hash_ok = pins_mod.file_hash(contract_file) == pin["hash"]

    lint = subprocess.run(
        [sys.executable, str(EVAL_DIR / "contract_lint.py"), str(contract_file)],
        capture_output=True, text=True, cwd=REPO_ROOT)
    return {"kata": kata, "gate": name, "template": template,
            "instance": gspec, "pin": pin, "pin_hash_verified": hash_ok,
            "contract_file": str(contract_file.relative_to(REPO_ROOT)),
            "contract_text": text,
            "lint": {"exit": lint.returncode,
                     "output": (lint.stdout + lint.stderr).strip()}}


def evidence(kata: str) -> dict:
    flow_dir = WORKSPACE / kata / "flow"
    versions = sorted(
        (int(m.group(1)), p)
        for p in flow_dir.glob("evidence_v*.json")
        if (m := re.match(r"evidence_v(\d+)$", p.stem)))
    if not versions:
        return {"kata": kata, "evidence": None}
    return {"kata": kata, "file": versions[-1][1].name,
            "evidence": json.loads(versions[-1][1].read_text())}


def adrs(kata: str) -> dict:
    adr_dir = WORKSPACE / kata / "adrs"
    out = []
    if adr_dir.exists():
        for f in sorted(adr_dir.glob("*.md")):
            text = f.read_text()
            decided = bool(re.search(r"^##\s*Decision\b", text, re.M)) and \
                bool(re.search(r"^##\s*Decision\s*\n+\s*\S", text, re.M))
            out.append({"file": f.name,
                        "processed": (f.parent / (f.name + ".processed")).exists(),
                        "decided": decided,
                        "title": (re.search(r"^#\s*(.+)$", text, re.M) or
                                  [None, f.stem])[1],
                        "text": text})
    return {"kata": kata, "adrs": out}


# ── commands (verifier runs — subprocess, full output, LOUD) ──────────────

def _run(cmd: list[str], timeout: int = 300) -> dict:
    r = subprocess.run(cmd, capture_output=True, text=True,
                       cwd=REPO_ROOT, timeout=timeout)
    return {"cmd": " ".join(cmd[1:]), "exit": r.returncode,
            "output": (r.stdout + ("\n" + r.stderr if r.stderr.strip() else ""))
            .strip()}  # full output, never a count — loud by doctrine


def run_eval(kata: str) -> dict:
    return _run([sys.executable, str(EVAL_DIR / "eval.py"), str(_flow_path(kata))])


def run_proof(kata: str) -> dict:
    return _run([sys.executable, str(EVAL_DIR / "proof.py"), str(_flow_path(kata))])


def run_regress(kata: str | None = None) -> dict:
    return _run([sys.executable, str(EVAL_DIR / "regress.py")])


def run_lint(kata: str | None = None) -> dict:
    return _run([sys.executable, str(EVAL_DIR / "contract_lint.py"),
                 str(GATES_DIR)])


# ── flow versions + diff (2026-07-12 complexity-gauge design note) ─────────

def flow_versions(kata: str) -> dict:
    flow_dir = WORKSPACE / kata / "flow"
    versions = sorted(
        int(m.group(1)) for p in flow_dir.glob("flow_v*.json")
        if (m := re.match(r"flow_v(\d+)$", p.stem)))
    return {"kata": kata, "versions": versions}


def flow_diff(kata: str, v_from: str, v_to: str) -> dict:
    """Element-level diff between two committed flow versions — the
    complexity gauge made explicit. Read-only, derived at call time."""
    flow_dir = WORKSPACE / kata / "flow"
    a = json.loads((flow_dir / f"flow_v{v_from}.json").read_text())
    b = json.loads((flow_dir / f"flow_v{v_to}.json").read_text())

    def syn_key(s):
        return f"{s['from']} -> {s['to']} [{s['pulse_type']}]"

    def diff_names(da, db):
        return {"added": sorted(set(db) - set(da)),
                "removed": sorted(set(da) - set(db))}

    changed_gates = sorted(
        n for n in set(a["gates"]) & set(b["gates"])
        if a["gates"][n] != b["gates"][n])
    ra = {r["id"]: r for r in a.get("requirements", [])}
    rb = {r["id"]: r for r in b.get("requirements", [])}
    return {
        "kata": kata, "from": int(v_from), "to": int(v_to),
        "loci": diff_names(a["loci"], b["loci"]),
        "gates": {**diff_names(a["gates"], b["gates"]), "changed": changed_gates},
        "synapses": diff_names([syn_key(s) for s in a["synapses"]],
                               [syn_key(s) for s in b["synapses"]]),
        "requirements": diff_names(ra, rb),
        "counts": {"from": {"gates": len(a["gates"]), "loci": len(a["loci"]),
                            "synapses": len(a["synapses"]), "reqs": len(ra)},
                   "to": {"gates": len(b["gates"]), "loci": len(b["loci"]),
                          "synapses": len(b["synapses"]), "reqs": len(rb)}},
    }


# ── ADR decide-in-UI — the SAME single decision-recording path the CLI
#    uses (REQ-10): agents/fa/adr.py write_decision + commit, verbatim. ──────

def _adr_mod():
    path = REPO_ROOT / "agents" / "fa" / "adr.py"
    spec = importlib.util.spec_from_file_location("fa_adr", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["fa_adr"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def adr_pending(kata: str) -> dict:
    """Pending ADRs parsed into decision cards: question, options,
    citations. The full text stays one pull away (adrs action)."""
    adr = _adr_mod()
    cards = []
    for p in adr.pending_adrs(kata):
        text = p.read_text()
        title = (re.search(r"^#\s*(.+)$", text, re.M) or [None, p.stem])[1]
        body_to_options = text.split("### Option")[0]
        context = re.sub(r"^#.*$", "", body_to_options, count=1, flags=re.M).strip()
        options = [{"label": m.group(1),
                    "text": m.group(2).strip()}
                   for m in re.finditer(
                       r"^### Option (\w+)\s*\n(.*?)(?=^### Option|\Z|^## Decision)",
                       text, re.M | re.DOTALL)]
        cites = sorted(set(re.findall(r"ADR-\d+", text)) - {title.split(":")[0]})
        cards.append({"file": p.name, "title": title, "context": context,
                      "options": options, "cites": cites})
    return {"kata": kata, "pending": cards}


def adr_decide(kata: str, file: str, choice: str,
               rationale: str = "") -> dict:
    """choice = an option label, 'reject', or 'own' (rationale = the
    architect's own option text). Decision text formats are the CLI's,
    verbatim — the record does not know which face produced it."""
    adr = _adr_mod()
    p = WORKSPACE / kata / "adrs" / file
    if p not in adr.pending_adrs(kata):
        return {"error": f"{file} is not a pending ADR for {kata}", "loud": True}
    labels = [l.lower() for l in adr.option_labels(p.read_text())]
    c = choice.strip().lower()
    if c == "reject":
        if not rationale.strip():
            return {"error": "rejection needs a reason", "loud": True}
        adr.write_decision(p, f"**Rejected.** (User)\n\n{rationale.strip()}")
        adr.commit(kata, f"ADR {p.stem}: rejected")
    elif c == "own":
        if not rationale.strip():
            return {"error": "own option needs its text", "loud": True}
        adr.write_decision(p, f"**Architect's option.** (User)\n\n{rationale.strip()}")
        adr.commit(kata, f"ADR {p.stem}: decided — architect's own option")
    elif c in labels:
        d = f"**Option {c.upper()}** (User)"
        if rationale.strip():
            d += f"\n\n{rationale.strip()}"
        adr.write_decision(p, d)
        adr.commit(kata, f"ADR {p.stem}: decided — Option {c.upper()}")
    else:
        return {"error": f"choice '{choice}' not in {labels} / reject / own",
                "loud": True}
    return {"kata": kata, "file": file, "decided": choice,
            "note": "recorded through agents/fa/adr.py write_decision + commit "
                    "— same path as the CLI; re-run FA to process."}


# ── speculative what-if: verifiers only, on a SCRATCH COPY (2026-07-08:
#    ephemeral, never touching the recorded workspace) ─────────────────────

def speculative_run(kata: str, spec: dict, label: str = "A") -> dict:
    """Run eval + prover against a caller-supplied flow spec variant.
    The spec is written to a temp file OUTSIDE the workspace and deleted
    with the temp dir; nothing recorded. Rollback is not an operation —
    this never touched the main line to begin with."""
    import tempfile
    with tempfile.TemporaryDirectory(prefix="opis_whatif_") as td:
        tmp = Path(td) / f"whatif_{label}.json"
        tmp.write_text(json.dumps(spec))
        ev = _run([sys.executable, str(EVAL_DIR / "eval.py"), str(tmp)])
        pr = _run([sys.executable, str(EVAL_DIR / "proof.py"), str(tmp)])
    m = re.search(r"(\d+) proved, (\d+) unproved", pr["output"])
    return {"kata": kata, "label": label, "ephemeral": True,
            "eval": ev, "proof": pr,
            "summary": {"eval_exit": ev["exit"], "proof_exit": pr["exit"],
                        "proved": int(m.group(1)) if m else None,
                        "unproved": int(m.group(2)) if m else None,
                        "gates": len(spec.get("gates", {})),
                        "synapses": len(spec.get("synapses", []))}}


# ── agent run control (start / status / stop) ─────────────────────────────
# A run is a subprocess writing to a log file; spend is read from the
# ledger the agents already append to (2026-07-11 REQ-20 bridge). PAUSE
# is NOT offered: FA has no iteration-boundary pause hook yet — offering
# a pause button that kills mid-iteration would be an invented promise
# (honest-status doctrine). Agent-side hook = candidate work.

_RUNS: dict[str, dict] = {}  # process handles live only while the server does


def agent_run_start(kata: str, agent: str = "fa") -> dict:
    import subprocess as sp
    import time
    if agent not in ("fa", "ca"):
        return {"error": f"agent must be fa|ca, got '{agent}'", "loud": True}
    key = f"{kata}:{agent}"
    if key in _RUNS and _RUNS[key]["proc"].poll() is None:
        return {"error": f"{key} already running (pid {_RUNS[key]['proc'].pid})",
                "loud": True}
    log_dir = WORKSPACE / kata / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    log = log_dir / f"ui_run_{agent}_{stamp}.log"
    arg = (str(REPO_ROOT / "agents" / "katas" / f"{kata}.md")
           if agent == "fa" else kata)
    fh = open(log, "w")
    proc = sp.Popen([sys.executable, "-u", "-m", f"agents.{agent}.runner", arg],
                    stdout=fh, stderr=sp.STDOUT, cwd=REPO_ROOT)
    _RUNS[key] = {"proc": proc, "log": str(log), "started": time.time(),
                  "stamp": stamp}
    return {"kata": kata, "agent": agent, "pid": proc.pid,
            "log": str(log.relative_to(REPO_ROOT)),
            "note": "pause not offered — FA lacks an iteration-boundary "
                    "hook; stop kills the process (branch untouched on "
                    "the main line by doctrine)."}


def agent_run_status(kata: str, agent: str = "fa") -> dict:
    key = f"{kata}:{agent}"
    r = _RUNS.get(key)
    ledger = WORKSPACE / kata / "spend_ledger.jsonl"
    spend = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "by_stage": {}}
    since = r["started"] if r else 0
    if ledger.exists():
        import datetime
        for line in ledger.read_text().splitlines():
            try:
                e = json.loads(line)
                ts = datetime.datetime.fromisoformat(e["ts"]).timestamp()
            except (ValueError, KeyError):
                continue
            if ts >= since and e.get("agent") == agent:
                spend["calls"] += 1
                spend["input_tokens"] += e.get("input_tokens") or 0
                spend["output_tokens"] += e.get("output_tokens") or 0
                st = e.get("stage") or "?"
                spend["by_stage"][st] = spend["by_stage"].get(st, 0) + 1
    if r is None:
        return {"kata": kata, "agent": agent, "running": False,
                "note": "no run started from this server session",
                "spend_all_time" if not since else "spend": spend}
    alive = r["proc"].poll() is None
    tail = ""
    if Path(r["log"]).exists():
        tail = "\n".join(Path(r["log"]).read_text().splitlines()[-25:])
    return {"kata": kata, "agent": agent, "running": alive,
            "pid": r["proc"].pid, "exit": r["proc"].poll(),
            "log": r["log"], "log_tail": tail, "spend": spend}


def agent_run_stop(kata: str, agent: str = "fa") -> dict:
    key = f"{kata}:{agent}"
    r = _RUNS.get(key)
    if r is None or r["proc"].poll() is not None:
        return {"error": f"no live run for {key}", "loud": True}
    r["proc"].terminate()
    try:
        r["proc"].wait(timeout=10)
    except Exception:
        r["proc"].kill()
    return {"kata": kata, "agent": agent, "stopped": True,
            "exit": r["proc"].poll(),
            "note": "stopped run leaves the main line untouched; "
                    "committed work on its branch stays for review."}
