#!/usr/bin/env python3
"""
opis-twin-check — flow performance validation via the Monte Carlo twin
(GA_PLAN Phase 3/4: "correct is not enough — is it performant?")

Runs da-twin against a flow with the latency library, then joins the
simulated per-gate fire-time distributions with the flow's requirements:

  - Each requirement's target gate has a fire-time distribution; since source
    loci inject at t=0, the target's fire time IS the end-to-end latency of
    that requirement's path through the flow.
  - Each requirement is matched to a *norm* (agents/latencies/latencies.json
    `norms`, keyed by base slot type) via the target gate's emitted outcome
    types, walking archetype `extends` chains — subtype-aware, same rule as
    opis-proof.
  - A requirement whose simulated p95 exceeds its norm's expected_p95_ms is
    flagged UNUSUALLY SLOW. Per Zarko's decision (2026-07-01) this is
    advisory — a flag for the architect, never a hard failure. Norms are
    rough real-life expectations; the value is surfacing outliers.

Hard failures (exit 1) are reserved for things that are wrong, not slow:
the twin binary failing, or gates that never fire in any run (dead gates —
the dynamic counterpart of an unreachable gate).

The da-twin binary is located via --twin-bin, $DA_TWIN_BIN, or common target
dirs. Note: cargo cannot build inside the synced repo folder — build from a
copy (e.g. /tmp/da-build) and point --twin-bin/$DA_TWIN_BIN at it.

Usage:
  python tools/opis-eval/twin_check.py <flow.json>
      [--latencies <latencies.json>] [--runs N] [--seed N]
      [--twin-bin <path>] [--report-out <path>]

Exit codes:
  0 — twin ran; any norm flags are advisory only
  1 — twin failed to run, or dead gates found
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]

_spec = importlib.util.spec_from_file_location("opis_eval", HERE / "eval.py")
eval_mod = importlib.util.module_from_spec(_spec)
sys.modules["opis_eval"] = eval_mod
_spec.loader.exec_module(eval_mod)  # type: ignore[union-attr]

c, ok, err, warn, info, hdr = (
    eval_mod.c, eval_mod.ok, eval_mod.err, eval_mod.warn, eval_mod.info, eval_mod.hdr,
)
GREEN, RED, YELLOW, CYAN, BOLD = (
    eval_mod.GREEN, eval_mod.RED, eval_mod.YELLOW, eval_mod.CYAN, eval_mod.BOLD,
)

DEFAULT_LATENCIES = REPO_ROOT / "agents" / "latencies" / "latencies.json"

TWIN_CANDIDATES = [
    REPO_ROOT / "agents" / "target" / "release" / "da-twin",
    REPO_ROOT / "agents" / "target" / "debug" / "da-twin",
    Path("/tmp/da-build/target/release/da-twin"),
]


def find_twin_bin(cli: str | None) -> Path | None:
    if cli:
        p = Path(cli)
        return p if p.exists() else None
    if os.environ.get("DA_TWIN_BIN"):
        p = Path(os.environ["DA_TWIN_BIN"])
        return p if p.exists() else None
    for p in TWIN_CANDIDATES:
        if p.exists():
            return p
    return None


def ancestor_chain(t: str, spec: dict) -> list[str]:
    """[t, parent, grandparent, ...] via archetype extends (cycle-guarded)."""
    arch = spec.get("archetypes", {})
    chain = [t]
    seen = {t}
    cur = t
    while True:
        parent = arch.get(cur, {}).get("extends") if isinstance(arch.get(cur), dict) else None
        if not parent or parent in seen:
            return chain
        chain.append(parent)
        seen.add(parent)
        cur = parent


def norm_for_requirement(req: dict, spec: dict, norms: dict) -> tuple[str, dict] | None:
    """Match a requirement to a norm via its target gate's emitted outcome
    types, walking each type's ancestor chain until a norm key matches."""
    target = req.get("target", {})
    gate = spec.get("gates", {}).get(target.get("gate"), {})
    outcome_name = target.get("outcome")
    flows: list[str] = []
    for e in gate.get("emits", []):
        if isinstance(e, dict) and (outcome_name is None or e.get("outcome") == outcome_name):
            flows.extend(e.get("flows", []))
    for t in flows:
        for anc in ancestor_chain(t, spec):
            if anc in norms:
                return anc, norms[anc]
    return None


def run_twin(
    twin_bin: Path, flow_path: Path, latencies: Path, runs: int, seed: int | None,
) -> dict | None:
    with tempfile.NamedTemporaryFile(suffix=".json", prefix="twin_report_", delete=False) as f:
        report_path = f.name
    cmd = [str(twin_bin), "--spec", str(flow_path), "--runs", str(runs),
           "--latencies", str(latencies), "--report", report_path]
    if seed is not None:
        cmd += ["--seed", str(seed)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(err(f"da-twin failed: {result.stderr.strip()[:500]}"))
        return None
    report = json.loads(Path(report_path).read_text())
    Path(report_path).unlink(missing_ok=True)
    return report


def check_flow_performance(
    flow_path: Path, latencies_path: Path, twin_bin: Path,
    runs: int, seed: int | None,
) -> tuple[list[str], list[str], dict | None]:
    """Returns (hard_issues, advisory_flags, report)."""
    spec = eval_mod.load_spec(flow_path)
    lib = json.loads(latencies_path.read_text())
    norms = lib.get("norms", {})

    report = run_twin(twin_bin, flow_path, latencies_path, runs, seed)
    if report is None:
        return (["twin did not produce a report"], [], None)

    issues: list[str] = []
    flags: list[str] = []

    dead = report.get("dead_gates", [])
    if dead:
        issues.append(
            f"dead gates (never fired in {report.get('runs')} runs): {', '.join(dead)}"
        )

    gates_stats = report.get("gates", {})
    for req in spec.get("requirements", []):
        rid = req.get("id", "?")
        target_gate = req.get("target", {}).get("gate")
        stats = gates_stats.get(target_gate)
        if stats is None:
            flags.append(f"{rid}: target gate '{target_gate}' missing from twin report")
            continue
        p95 = stats.get("p95_ms", 0.0)
        fire = stats.get("fire_pct", 0.0)
        matched = norm_for_requirement(req, spec, norms)
        if matched is None:
            flags.append(
                f"{rid} → {target_gate}: e2e p95 {p95:.0f} ms, fire {fire:.1f}% — "
                f"no norm matches its outcome types (unjudged)"
            )
            continue
        norm_key, norm = matched
        expected = float(norm.get("expected_p95_ms", 0))
        confidence = norm.get("confidence", "llm-estimate")
        if expected and p95 > expected:
            flags.append(
                f"{rid} → {target_gate}: UNUSUALLY SLOW — e2e p95 {p95:.0f} ms > "
                f"norm '{norm_key}' {expected:.0f} ms ({confidence}); fire {fire:.1f}%"
            )
        else:
            flags.append(
                f"{rid} → {target_gate}: e2e p95 {p95:.0f} ms within norm "
                f"'{norm_key}' {expected:.0f} ms ({confidence}); fire {fire:.1f}%"
            )

    return issues, flags, report


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    flow_path = Path(sys.argv[1])
    latencies_path = DEFAULT_LATENCIES
    runs, seed = 3000, None
    twin_cli: str | None = None
    report_out: str | None = None
    argv = sys.argv
    if "--latencies" in argv:
        latencies_path = Path(argv[argv.index("--latencies") + 1])
    if "--runs" in argv:
        runs = int(argv[argv.index("--runs") + 1])
    if "--seed" in argv:
        seed = int(argv[argv.index("--seed") + 1])
    if "--twin-bin" in argv:
        twin_cli = argv[argv.index("--twin-bin") + 1]
    if "--report-out" in argv:
        report_out = argv[argv.index("--report-out") + 1]

    print(c("\nopis-twin-check  ", BOLD) + c(str(flow_path.resolve()), YELLOW))

    twin_bin = find_twin_bin(twin_cli)
    if twin_bin is None:
        print(err("da-twin binary not found — build it (from OUTSIDE the synced folder, "
                  "e.g. copy agents/ crates to /tmp/da-build and `cargo build -p da-twin "
                  "--release`), then pass --twin-bin or set $DA_TWIN_BIN"))
        sys.exit(1)
    print(info(f"twin: {twin_bin}"))
    print(info(f"latencies: {latencies_path}"))

    issues, flags, report = check_flow_performance(
        flow_path, latencies_path, twin_bin, runs, seed,
    )

    if report is not None:
        bn = report.get("bottleneck")
        if bn:
            print(info(f"bottleneck: {bn['gate']} (p99 {bn['p99_ms']:.0f} ms)"))
        if report_out:
            Path(report_out).write_text(json.dumps(report, indent=1))
            print(info(f"full twin report → {report_out}"))

    print(hdr("Requirement end-to-end timing vs norms (advisory)"))
    slow = 0
    for f in flags:
        if "UNUSUALLY SLOW" in f:
            slow += 1
            print(warn(f))
        elif "unjudged" in f or "missing" in f:
            print(info(f))
        else:
            print(ok(f))

    print()
    if issues:
        for i in issues:
            print(err(i))
        print(c(f"\n✗ {len(issues)} hard issue(s)", RED))
        sys.exit(1)
    if slow:
        print(c(f"⚠ twin ran clean; {slow} requirement(s) flagged unusually slow "
                f"(advisory — architect's call)", YELLOW))
    else:
        print(c("✓ twin ran clean; all judged requirements within norms", GREEN))
    sys.exit(0)


if __name__ == "__main__":
    main()
