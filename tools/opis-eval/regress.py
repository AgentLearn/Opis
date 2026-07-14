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
OUTPUT_DIR = REPO_ROOT / "workspace"


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
pins_mod = _load("opis_pins", HERE / "pins.py")


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


def pinned_view(spec: dict, gates_dir: Path) -> Path:
    """A pinned flow's proofs must re-run against the EXACT contracts it was
    proved with — not whatever the current files say (an amendment moves the
    current file; the flow doesn't move with it). Build a temp gates dir
    where each pinned template resolves through the archive when needed.
    Flows without pins (legacy) just use the live dir."""
    pins = (spec.get("pins") or {}).get("gates")
    if not pins:
        return gates_dir
    import shutil
    import tempfile
    view = Path(tempfile.mkdtemp(prefix="opis-pinned-view-"))
    for t in pins_mod.flow_templates(spec):
        pin = pins.get(t)
        src = pins_mod.contract_path(gates_dir, t,
                                     pin.get("version") if pin else None)
        if src.exists():
            shutil.copy(src, view / f"{t}.md")
        # a missing resolved contract is verify_pins' error to report
    return view


def check_flow(flow_path: Path, gates_dir: Path) -> tuple[list[str], int]:
    """Run the full success gate against one flow. Returns (issues, n_reqs)."""
    issues: list[str] = []

    if not run_eval(flow_path, gates_dir):
        issues.append("opis-eval reports structural errors (exit 1)")

    spec = eval_mod.load_spec(flow_path)
    proof_gates_dir = pinned_view(spec, gates_dir)

    results = proof_mod.verify_requirements(spec, proof_gates_dir)
    for r in results:
        if r["status"] != "proved":
            detail = "; ".join(r.get("issues", [])) or "unproved"
            issues.append(f"requirement {r['id']} unproved — {detail}")

    for conf in proof_mod.check_gate_conformance(spec, proof_gates_dir):
        issues.append(f"gate conformance — {conf['message']}")

    # pins: a committed flow is only reproducible against the exact contracts
    # + taxonomy it was proved with. Errors (hash/version mismatch, unpinned
    # template) are regressions; warnings (legacy no-pins, stale pin) pass
    # with a notice — same tolerance policy as eval warnings.
    slot_types = gates_dir.parent / "slot_types" / "index.md"
    pin_errors, pin_warnings = pins_mod.verify_pins(spec, gates_dir, slot_types)
    for e in pin_errors:
        issues.append(f"pins — {e}")
    for w in pin_warnings:
        print(warn(f"    pins — {w}"))

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

    # Prompt-skill pins: FA/CA prompts live as repo skills (agents/skills/,
    # `binding:` frontmatter) and are proof machinery like gate contracts —
    # every committed flow was produced THROUGH them. A hash mismatch against
    # agents/skills/pins.json means an agent prompt changed without an
    # explicit re-pin (prompt_pins.py --write) — always a regression.
    print(hdr("Prompt-skill pins (agents/skills vs pins.json)"))
    prompt_pins_mod = _load("opis_prompt_pins", HERE / "prompt_pins.py")
    skills_dir = gates_dir.parent / "skills"
    prompt_errors = prompt_pins_mod.verify_pins(skills_dir)
    if not prompt_errors:
        print(ok("every binding-bearing prompt skill matches the lock"))
    else:
        total_regressions += len(prompt_errors)
        for line in prompt_errors:
            for sub in line.splitlines():
                print(err(f"  {sub}"))

    # Confirmed scenarios: expert-confirmed user stories are kata-keyed
    # fixtures that SURVIVE flow rebuilds — each is re-verified against the
    # CURRENT canonical flow (the pin is provenance, not a freeze). Gates
    # get regenerated every flow version; confirmed scenarios are the
    # behavioral regression suite gates can't be. A flow that breaks one is
    # a regression (or a domain change the expert must re-confirm).
    import json as _json
    print(hdr("Confirmed scenarios (user stories vs canonical flow)"))
    scenario_tool = HERE / "scenario.py"
    n_scen = 0
    for kata_dir in kata_dirs:
        flow_path = canonical_flow(kata_dir)
        scen_dir = kata_dir / "scenarios"
        if not flow_path or not scen_dir.is_dir():
            continue
        for sc_path in sorted(scen_dir.glob("*.json")):
            try:
                sc = _json.loads(sc_path.read_text())
            except (ValueError, OSError):
                continue
            if "confirmed" not in sc:
                continue  # drafts/candidates never gate the board
            n_scen += 1
            r = subprocess.run(
                [sys.executable, str(scenario_tool), "verify",
                 str(sc_path), str(flow_path)],
                capture_output=True, text=True)
            if r.returncode == 0:
                print(ok(f"{kata_dir.name}: '{sc.get('name', sc_path.stem)}' "
                         f"holds vs {flow_path.name}"))
            else:
                total_regressions += 1
                print(err(f"{kata_dir.name}: '{sc.get('name', sc_path.stem)}' "
                          f"BROKEN vs {flow_path.name}"))
                for line in (r.stdout + r.stderr).strip().splitlines():
                    if "✗" in line:
                        print(err(f"  {line.strip()}"))
    if n_scen == 0:
        print(info("no confirmed scenarios found — nothing to verify"))

    # Twin reduction (2026-07-14, multi-admission design): the multi-admission
    # engine must reproduce single-admission-era seeded reports BYTE-IDENTICALLY
    # on flows with at most one arrival per requirement (N=1 reduction — one
    # semantics, no mode flag). Fixtures are pinned by sha256; fixture tamper
    # or a report mismatch = regression. No twin binary on this machine =
    # honest SKIP (warning), never silent green. NOTE: a stale binary can pass
    # this section — rebuild da-twin after touching its source.
    print(hdr("Twin reduction (N=1 must reproduce pinned reports byte-identically)"))
    import hashlib as _hashlib
    import os as _os
    import tempfile as _tempfile
    fixtures_dir = HERE / "fixtures" / "twin_reduction"
    manifest_path = fixtures_dir / "manifest.json"
    twin_bin = None
    for cand in ([Path(_os.environ["DA_TWIN"])] if _os.environ.get("DA_TWIN") else []) + [
        REPO_ROOT / "agents" / "target" / "release" / "da-twin",
        REPO_ROOT / "agents" / "crates" / "da-twin" / "target" / "release" / "da-twin",
    ]:
        if cand.is_file() and _os.access(cand, _os.X_OK):
            twin_bin = cand
            break
    if not manifest_path.is_file():
        print(warn("no reduction fixtures found — nothing to verify"))
    elif twin_bin is None:
        print(warn("da-twin binary not found (set DA_TWIN or build "
                   "agents/crates/da-twin) — reduction NOT verified this run"))
    else:
        manifest = _json.loads(manifest_path.read_text())
        for entry in manifest.get("entries", []):
            label = entry["fixture"]
            fixture = fixtures_dir / entry["fixture"]
            flow = output_dir / entry["flow"]
            if not fixture.is_file() or not flow.is_file():
                total_regressions += 1
                print(err(f"{label}: fixture or flow file missing"))
                continue
            fixture_bytes = fixture.read_bytes()
            if _hashlib.sha256(fixture_bytes).hexdigest() != entry["sha256"]:
                total_regressions += 1
                print(err(f"{label}: fixture bytes do not match pinned sha256 "
                          f"— fixture tampered or edited without re-pin"))
                continue
            with _tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
                tmp_report = Path(tf.name)
            try:
                cmd = [str(twin_bin), "--spec", str(flow),
                       "--runs", str(entry["runs"]), "--seed", str(entry["seed"]),
                       "--report", str(tmp_report)]
                if entry.get("tamper_sigs"):
                    cmd.append("--tamper-sigs")
                r = subprocess.run(cmd, capture_output=True, text=True)
                if r.returncode != 0:
                    total_regressions += 1
                    print(err(f"{label}: twin run failed — {r.stderr.strip()[:200]}"))
                elif tmp_report.read_bytes() == fixture_bytes:
                    print(ok(f"{label}: byte-identical "
                             f"(seed {entry['seed']}, {entry['runs']} runs"
                             f"{', tamper' if entry.get('tamper_sigs') else ''})"))
                else:
                    total_regressions += 1
                    print(err(f"{label}: report DIVERGES from pinned "
                              f"single-admission-era bytes — N=1 reduction broken"))
            finally:
                tmp_report.unlink(missing_ok=True)

    # ADVISORY: prose-exceeds-slots lint over the current library. Heuristic
    # warnings only — NEVER counted as regressions (4/4 CA falsifications to
    # date were this class; the lint shifts it left of CA, but a heuristic
    # must not be able to turn the board red).
    print(hdr("Contract lint (prose-exceeds-slots, advisory)"))
    lint_result = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "contract_lint.py"),
         str(gates_dir), "--quiet"],
        capture_output=True, text=True)
    lint_out = lint_result.stdout.strip()
    if lint_result.returncode == 0 and not lint_out:
        print(ok("no prose-exceeds-slots suspects in the gate library"))
    else:
        for line in lint_out.splitlines():
            print(c(f"  {line}", YELLOW))

    print()
    if total_regressions == 0:
        print(c(f"✓ all {len(flows)} committed flow(s) and {len(internals)} gate "
                f"internal(s) still pass; index consistent", GREEN))
        sys.exit(0)
    print(c(f"✗ {total_regressions} regression(s) detected", RED))
    sys.exit(1)


if __name__ == "__main__":
    main()
