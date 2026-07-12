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
