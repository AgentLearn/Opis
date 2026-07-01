#!/usr/bin/env python3
"""
opis-regress — re-verify every committed flow against the CURRENT tools.

Each kata's canonical committed flow passed the full success gate when FA wrote
it (opis-eval clean + every requirement proved + gate conformance). Those flows
are therefore a golden corpus: if any of them now fails, the regression is in
the tooling or the gates library, not the flow. This harness re-runs the whole
gate against each one so a change to eval.py / proof.py / a gate file can't
silently break a previously-verified flow without anyone noticing.

It also runs the gate-index consistency check once (index.md vs the gate files
on disk).

What "canonical committed flow" means per kata: flow/flow_current.json if the
symlink exists, else the highest-numbered flow_vN.json. Scratch (_iterating.json)
and superseded lower versions are ignored — only the latest committed flow must
stay green.

Usage:
  python tools/opis-eval/regress.py [--gates-dir <path>] [--output-dir <path>]

Exit codes:
  0 — every committed flow still passes and the index is consistent
  1 — one or more regressions
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
GATES_DIR = REPO_ROOT / "agents" / "gates"
OUTPUT_DIR = REPO_ROOT / "agents" / "output"


def _load(name: str, path: Path):
    """Load a sibling module by file path (this dir has a hyphen — can't import
    it by name). proof.py transitively loads eval.py the same way."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


proof_mod = _load("opis_proof", HERE / "proof.py")
eval_mod = sys.modules["opis_eval"]  # registered by proof.py's own loader


# ── ANSI (reuse eval.py's helpers) ────────────────────────────────────────────

c, ok, err, warn, info, hdr = (
    eval_mod.c, eval_mod.ok, eval_mod.err, eval_mod.warn, eval_mod.info, eval_mod.hdr
)
GREEN, RED, YELLOW, BOLD = eval_mod.GREEN, eval_mod.RED, eval_mod.YELLOW, eval_mod.BOLD


def canonical_flow(kata_dir: Path) -> Path | None:
    """flow/flow_current.json if present, else the highest flow_vN.json."""
    flow_dir = kata_dir / "flow"
    if not flow_dir.exists():
        return None
    current = flow_dir / "flow_current.json"
    if current.exists():
        return current.resolve()
    versions: list[tuple[int, Path]] = []
    for p in flow_dir.glob("flow_v*.json"):
        m = re.match(r"flow_v(\d+)$", p.stem)
        if m:
            versions.append((int(m.group(1)), p))
    return max(versions)[1] if versions else None


def run_eval(flow_path: Path, gates_dir: Path) -> bool:
    """True unless opis-eval reports structural ERRORS (exit 1). Warnings
    (exit 2) are tolerated — same policy FA's own success gate uses."""
    result = subprocess.run(
        [sys.executable, str(HERE / "eval.py"), str(flow_path)],
        capture_output=True, text=True,
    )
    return result.returncode != 1


def check_flow(flow_path: Path, gates_dir: Path) -> tuple[list[str], int]:
    """Run the full success gate against one flow. Returns (issues, n_reqs)."""
    issues: list[str] = []

    if not run_eval(flow_path, gates_dir):
        issues.append("opis-eval reports structural errors (exit 1)")

    spec = eval_mod.load_spec(flow_path)

    results = proof_mod.verify_requirements(spec, gates_dir)
    for r in results:
        if r["status"] != "proved":
            detail = "; ".join(r.get("issues", [])) or "unproved"
            issues.append(f"requirement {r['id']} unproved — {detail}")

    for conf in proof_mod.check_gate_conformance(spec, gates_dir):
        issues.append(f"gate conformance — {conf['message']}")

    return issues, len(results)


def canonical_internals(gates_dir: Path) -> list[tuple[str, Path]]:
    """Every gate template with committed internals: gates/<template>/internals_vN.json,
    canonical = highest N. These passed gate-proof when written — golden corpus,
    same contract as committed flows."""
    found: list[tuple[str, Path]] = []
    for tdir in sorted(d for d in gates_dir.iterdir() if d.is_dir()):
        versions: list[tuple[int, Path]] = []
        for p in tdir.glob("internals_v*.json"):
            m = re.match(r"internals_v(\d+)$", p.stem)
            if m:
                versions.append((int(m.group(1)), p))
        if versions:
            found.append((tdir.name, max(versions)[1]))
    return found


def check_internals(internals_path: Path, gates_dir: Path) -> list[str]:
    """Re-run the full gate-proof battery against committed gate internals."""
    result = subprocess.run(
        [sys.executable, str(HERE / "gate_proof.py"), str(internals_path),
         "--gates-dir", str(gates_dir)],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return []
    return [
        line.strip() for line in result.stdout.splitlines()
        if "✗" in line and "violation(s)" not in line
    ] or [f"gate-proof failed (exit {result.returncode})"]


def main() -> None:
    gates_dir = GATES_DIR
    output_dir = OUTPUT_DIR
    if "--gates-dir" in sys.argv:
        gates_dir = Path(sys.argv[sys.argv.index("--gates-dir") + 1])
    if "--output-dir" in sys.argv:
        output_dir = Path(sys.argv[sys.argv.index("--output-dir") + 1])

    print(c("\nopis-regress  ", BOLD) + c("re-verifying committed flows", YELLOW))
    print(info(f"gates: {gates_dir}"))
    print(info(f"output: {output_dir}"))

    kata_dirs = sorted(d for d in output_dir.iterdir() if d.is_dir()) if output_dir.exists() else []
    flows = [(d.name, canonical_flow(d)) for d in kata_dirs]
    flows = [(name, fp) for name, fp in flows if fp is not None]

    total_regressions = 0

    print(hdr("Committed flows"))
    if not flows:
        print(warn("no committed flows found — nothing to verify"))
    for name, flow_path in flows:
        issues, n_reqs = check_flow(flow_path, gates_dir)
        if not issues:
            print(ok(f"{name:20s} {flow_path.name}  — {n_reqs}/{n_reqs} requirements proved, conformant"))
        else:
            total_regressions += 1
            print(err(f"{name:20s} {flow_path.name}  — {len(issues)} regression(s)"))
            for line in issues:
                for sub in line.splitlines():
                    print(err(f"    {sub}"))

    internals = canonical_internals(gates_dir)
    print(hdr("Gate internals (gate-proof: contract, coverage, exclusivity, timing)"))
    if not internals:
        print(warn("no committed gate internals found — nothing to verify"))
    for template, ipath in internals:
        issues = check_internals(ipath, gates_dir)
        if not issues:
            print(ok(f"{template:20s} {ipath.name}  — contract honored"))
        else:
            total_regressions += 1
            print(err(f"{template:20s} {ipath.name}  — {len(issues)} regression(s)"))
            for line in issues:
                for sub in line.splitlines():
                    print(err(f"    {sub}"))

    print(hdr("Gate-index consistency (index.md vs gate files)"))
    index_issues = proof_mod.check_index_consistency(gates_dir)
    if not index_issues:
        print(ok("index.md is in sync with every gate file on disk"))
    else:
        total_regressions += len(index_issues)
        for line in index_issues:
            for sub in line.splitlines():
                print(err(f"  {sub}"))

    print()
    if total_regressions == 0:
        print(c(f"✓ all {len(flows)} committed flow(s) and {len(internals)} gate "
                f"internal(s) still pass; index consistent", GREEN))
        sys.exit(0)
    print(c(f"✗ {total_regressions} regression(s) detected", RED))
    sys.exit(1)


if __name__ == "__main__":
    main()
