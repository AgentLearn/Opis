#!/usr/bin/env python3
"""
opis-gate-proof — gate-internals verifier (the GA verification stack, Phase 2)

Where opis-proof verifies a *flow* against its requirements, opis-gate-proof
verifies a gate template's *internals* against the template's own contract
(the frontmatter of agents/gates/<template>.md). A gate's internals are a
recursive pulse-network in the format eval.py's compose_flow_gate already
defines: {gate, version, in, out, loci, gates, synapses} — internal synapses
that name the gate itself are rewritten to virtual entry/exit boundary loci.

Four checks, per GA_PLAN.md:

  1. Contract consistency — the internals file's declared in/out match the
     template frontmatter's required input types and output types exactly.
  2. Contract coverage — every `out` type has a real witness path from the
     entry boundary through the internal topology to the exit boundary,
     computed with the same logic-aware AND/OR/FIRST/THRESHOLD fixed point
     opis-proof uses. Every `in` type must be consumed by some internal gate.
  3. Outcome exclusivity — flow-level semantics say a gate emits exactly one
     outcome per firing. The internals must preserve that: enumerating every
     combination of outcome choices at internal multi-outcome gates, no single
     combination may deliver two distinct contract out-types to the exit
     boundary. (Exhaustive over outcome assignments, not sampled; capped —
     internals are meant to be small.)
  4. Static timing budget — worst-case arrival time at the exit boundary,
     computed by DP over the fired DAG (each gate contributes its window_ms
     on top of the latest-arriving input it could wait for — conservative
     upper bound for OR/THRESHOLD joins), must fit the template's window_ms.
     The slowest-re-arming internal gate's refractory_ms must not exceed the
     template's refractory_ms, or the gate cannot re-arm as fast as its
     contract promises.

Additionally the composed harness (a minimal synthetic flow wrapping the gate
stub + internals) is run through the full opis-eval battery; structural
errors (exit 1) fail the proof, warnings are tolerated (same policy as FA's
success gate — the virtual entry boundary is inside an already-authenticated
gate, so sentinel warnings there are expected noise).

Usage:
  python tools/opis-eval/gate_proof.py <internals.json> [--gates-dir <path>]

Exit codes:
  0 — internals honor the contract on all four checks (+ eval has no errors)
  1 — one or more violations
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import subprocess
import sys
import tempfile
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent

# proof.py transitively loads eval.py and registers both module names.
_spec = importlib.util.spec_from_file_location("opis_proof", HERE / "proof.py")
proof_mod = importlib.util.module_from_spec(_spec)
sys.modules["opis_proof"] = proof_mod
_spec.loader.exec_module(proof_mod)  # type: ignore[union-attr]
eval_mod = sys.modules["opis_eval"]

c, ok, err, warn, info, hdr = (
    eval_mod.c, eval_mod.ok, eval_mod.err, eval_mod.warn, eval_mod.info, eval_mod.hdr,
)
GREEN, RED, YELLOW, CYAN, BOLD = (
    eval_mod.GREEN, eval_mod.RED, eval_mod.YELLOW, eval_mod.CYAN, eval_mod.BOLD,
)

EXCLUSIVITY_CAP = 4096  # max outcome-choice combinations to enumerate


# ── harness construction ───────────────────────────────────────────────────────

def build_harness(internals: dict, frontmatter: dict) -> tuple[dict, str, str]:
    """Wrap the gate stub in a minimal synthetic flow and compose the internals
    into it via eval.compose_flow_gate. Returns (composed_spec, entry, exit)."""
    template = internals["gate"]
    in_types = list(internals.get("in", []))
    out_types = list(internals.get("out", []))

    stub: dict[str, Any] = {
        "description": f"stub of template {template} under gate-proof harness",
        "kind": frontmatter.get("kind", "gate"),
        "requires": in_types,
        "emits": [{"outcome": t, "flows": [t], "weight": 1.0} for t in out_types],
    }
    for key in ("window_ms", "refractory_ms"):
        if key in frontmatter:
            # parse_gate_frontmatter is a light YAML reader — numbers can come
            # back as strings; eval's timing checks need real numbers.
            try:
                stub[key] = float(frontmatter[key])
            except (TypeError, ValueError):
                stub[key] = frontmatter[key]

    harness: dict[str, Any] = {
        "name": f"{template}__gate_proof_harness",
        "version": internals.get("version", 1),
        "description": f"synthetic harness flow for gate-proof of {template}",
        # internals' micro-types must be visible to build_type_dag
        "archetypes": dict(internals.get("archetypes", {})),
        "loci": {
            "HarnessDriver": {
                "description": "synthetic upstream — supplies the contract's input slots",
                "source": True,
            },
            "HarnessSink": {
                "description": "synthetic downstream — absorbs the contract's output slots",
            },
        },
        "gates": {template: stub},
        "synapses": (
            [{"from": "HarnessDriver", "to": template, "pulse_type": t,
              "medium": "local", "interaction": "push"} for t in in_types]
            + [{"from": template, "to": "HarnessSink", "pulse_type": t,
                "medium": "local", "interaction": "push"} for t in out_types]
        ),
        "requirements": [],
    }

    composed = eval_mod.compose_flow_gate(harness, internals)
    composed = eval_mod._normalize_spec_gates(composed)
    prefix = template + "__"
    return composed, prefix + "_entry", prefix + "_exit"


# ── check 1: contract consistency ──────────────────────────────────────────────

def check_contract_consistency(internals: dict, frontmatter: dict) -> list[str]:
    issues: list[str] = []
    declared_in = set(internals.get("in", []))
    declared_out = set(internals.get("out", []))
    fm_in = proof_mod._required_input_types(frontmatter)
    fm_out = proof_mod._output_types(frontmatter)

    if declared_in != fm_in:
        issues.append(
            f"internals `in` {sorted(declared_in)} ≠ template required inputs {sorted(fm_in)}"
        )
    if declared_out != fm_out:
        issues.append(
            f"internals `out` {sorted(declared_out)} ≠ template outputs {sorted(fm_out)}"
        )
    return issues


# ── check 2: contract coverage ─────────────────────────────────────────────────

def _arrived_matches(t: str, arrived: set[str], type_dag: dict[str, set[str]]) -> bool:
    return t in arrived or bool(type_dag.get(t, set()) & arrived)


def check_contract_coverage(
    composed: dict, internals: dict, exit_locus: str,
) -> tuple[list[str], list[str], dict[str, list[dict[str, Any]]]]:
    """Every out type must genuinely arrive at the exit boundary (witness path
    reconstructed); every in type must be consumed by some internal gate.
    Returns (issues, notes, witness_paths_by_out_type)."""
    issues: list[str] = []
    notes: list[str] = []
    prefix = internals["gate"] + "__"
    type_dag = eval_mod.build_type_dag(composed)

    reachable, pred = proof_mod.trace_reachability_with_paths(composed)
    at_exit = reachable.get(exit_locus, set())

    witnesses: dict[str, list[dict[str, Any]]] = {}
    for out_t in internals.get("out", []):
        concrete = out_t if out_t in at_exit else next(
            iter(type_dag.get(out_t, set()) & at_exit), None
        )
        if concrete is None:
            issues.append(
                f"out type '{out_t}' never reaches the exit boundary — "
                f"no internal path emits it (or its emitter cannot fire)"
            )
            continue
        path = proof_mod.reconstruct_path(pred, exit_locus, concrete)
        witnesses[out_t] = path
        if any(hop.get("fired") == "fallback" for hop in path):
            notes.append(
                f"out type '{out_t}': witness path crosses a requires-cycle FALLBACK — "
                f"not a clean trace"
            )

    consumed: set[str] = set()
    internal_gates = {
        prefix + name: g for name, g in internals.get("gates", {}).items()
    }
    for gname, gspec in internal_gates.items():
        for req in gspec.get("requires", []) + gspec.get("optional", []):
            consumed.add(req)
            consumed.update(type_dag.get(req, set()))
    for in_t in internals.get("in", []):
        if in_t not in consumed and not (type_dag.get(in_t, set()) & consumed):
            issues.append(
                f"in type '{in_t}' is never consumed by any internal gate — "
                f"dead input slot inside the gate"
            )

    return issues, notes, witnesses


# ── check 3: outcome exclusivity ───────────────────────────────────────────────

def _constrained_reachability(
    composed: dict,
    choice: dict[str, int],
    skip_gates: set[str],
) -> dict[str, set[str]]:
    """Forward propagation where each gate in `choice` emits ONLY its chosen
    outcome's flows (per-firing exclusivity, made explicit). Gates in
    `skip_gates` (the stub, harness scaffolding) never fire. Logic-aware.
    No cycle fallback: a gate stuck behind a cycle simply does not fire —
    conservative for coverage, and internals are meant to be acyclic anyway."""
    nodes, gates, edges = eval_mod.build_graph(composed)
    fwd, _ = eval_mod.adjacency(edges)
    type_dag = eval_mod.build_type_dag(composed)

    loci_spec = composed.get("loci", {})
    has_incoming = {e.dst for e in edges if not e.inhibitor}
    sources = {n for n in nodes if n not in has_incoming} | {
        n for n, ls in loci_spec.items()
        if isinstance(ls, dict) and ls.get("source")
    }

    reachable: dict[str, set[str]] = defaultdict(set)
    emitted: dict[str, set[str]] = defaultdict(set)  # gate → types it actually emitted
    fired: set[str] = set()
    queue: deque[str] = deque()

    def add(node: str, t: str) -> None:
        if t not in reachable[node]:
            reachable[node].add(t)
            queue.append(node)

    for s in sources:
        for e in fwd.get(s, []):
            if e.pulse_type and not e.inhibitor:
                add(s, e.pulse_type)

    def emitted_flows(gname: str, gspec: dict) -> list[str]:
        emits = gspec.get("emits", [])
        outcomes = [e for e in emits if isinstance(e, dict)]
        if gname in choice and choice[gname] < len(outcomes):
            outcomes = [outcomes[choice[gname]]]
        flows: list[str] = []
        for o in outcomes:
            flows.extend(o.get("flows", []))
        return flows

    while queue:
        node = queue.popleft()
        # NO PASS-THROUGH: gates forward only what they emitted; loci relay all.
        forwardable = emitted[node] & reachable[node] if node in gates else set(reachable[node])
        for e in fwd.get(node, []):
            if e.inhibitor:
                continue
            crossing = (
                {e.pulse_type} & forwardable if e.pulse_type
                else set(forwardable)
            )
            for t in crossing:
                add(e.dst, t)
        if node in gates and node not in fired and node not in skip_gates:
            gspec = gates[node]
            if proof_mod.gate_logic_satisfied(gspec, reachable.get(node, set()), type_dag):
                fired.add(node)
                for t in emitted_flows(node, gspec):
                    emitted[node].add(t)
                    add(node, t)
                queue.append(node)

    return dict(reachable)


def check_outcome_exclusivity(
    composed: dict, internals: dict, exit_locus: str,
) -> tuple[list[str], list[str]]:
    """No single assignment of outcome choices may deliver ≥2 distinct contract
    out-types to the exit boundary. Skipped (with a note) if the contract has
    fewer than two output types."""
    issues: list[str] = []
    notes: list[str] = []
    template = internals["gate"]
    prefix = template + "__"
    out_types = list(internals.get("out", []))
    if len(out_types) < 2:
        notes.append("single-output contract — exclusivity trivially holds")
        return issues, notes

    type_dag = eval_mod.build_type_dag(composed)
    internal_gate_names = [prefix + n for n in internals.get("gates", {})]
    gates_spec = composed.get("gates", {})

    choice_gates = [
        g for g in internal_gate_names
        if len([e for e in gates_spec.get(g, {}).get("emits", []) if isinstance(e, dict)]) > 1
    ]
    n_combos = 1
    for g in choice_gates:
        n_combos *= len([e for e in gates_spec[g].get("emits", []) if isinstance(e, dict)])
    if n_combos > EXCLUSIVITY_CAP:
        issues.append(
            f"outcome-choice space too large to enumerate ({n_combos} > {EXCLUSIVITY_CAP}) — "
            f"internals should be smaller than this; refusing to sample"
        )
        return issues, notes

    skip = {template}  # the stub must not shortcut in→out around the internals
    ranges = [
        range(len([e for e in gates_spec[g].get("emits", []) if isinstance(e, dict)]))
        for g in choice_gates
    ]
    for combo in itertools.product(*ranges) if choice_gates else [()]:
        choice = dict(zip(choice_gates, combo))
        at_exit = _constrained_reachability(composed, choice, skip).get(exit_locus, set())
        delivered = {
            out_t for out_t in out_types
            if _arrived_matches(out_t, at_exit, type_dag)
        }
        if len(delivered) >= 2:
            picks = ", ".join(
                f"{g.removeprefix(prefix)}→outcome[{i}]" for g, i in choice.items()
            ) or "(no multi-outcome gates)"
            issues.append(
                f"outcome exclusivity violated: choices {{{picks}}} deliver "
                f"{sorted(delivered)} together in a single admission"
            )

    if not issues:
        notes.append(
            f"exhaustive over {n_combos} outcome combination(s) at "
            f"{len(choice_gates)} decision gate(s)"
        )
    return issues, notes


# ── check 4: static timing budget ──────────────────────────────────────────────

def check_timing_budget(
    composed: dict, internals: dict, frontmatter: dict, exit_locus: str,
) -> tuple[list[str], list[str]]:
    """Worst-case arrival at the exit boundary vs the template's window_ms,
    via DP over the fired DAG: a gate completes at its window_ms after the
    latest-arriving input it could wait for (conservative for OR/THRESHOLD).
    Synapse traversal is 0 statically — realistic medium latencies are the
    twin's job (GA_PLAN Phase 3), this is the cheap impossible-contract catch."""
    issues: list[str] = []
    notes: list[str] = []
    template = internals["gate"]
    prefix = template + "__"

    parent_window = frontmatter.get("window_ms")
    parent_refractory = frontmatter.get("refractory_ms")

    reachable, pred = proof_mod.trace_reachability_with_paths(composed)
    gates_spec = composed.get("gates", {})
    type_dag = eval_mod.build_type_dag(composed)

    memo: dict[tuple[str, str], float] = {}
    in_progress: set[tuple[str, str]] = set()

    def fire_time(gname: str) -> float:
        gspec = gates_spec.get(gname, {})
        window = float(gspec.get("window_ms", 0.0))
        required = set(gspec.get("requires", [])) - set(gspec.get("optional", []))
        arrived = reachable.get(gname, set())
        waits = [
            avail(gname, t) for t in required
            if _arrived_matches(t, arrived, type_dag)
        ]
        return window + (max(waits) if waits else 0.0)

    def avail(node: str, t: str) -> float:
        # `t` may be abstract (a required supertype); resolve to the concrete
        # arrived type whose pred chain exists.
        arrived = reachable.get(node, set())
        concrete = t if (node, t) in pred or t in arrived else next(
            iter(type_dag.get(t, set()) & arrived), t
        )
        key = (node, concrete)
        if key in memo:
            return memo[key]
        if key in in_progress:
            return 0.0  # cycle guard — flagged by coverage's FALLBACK note
        in_progress.add(key)
        p = pred.get(key)
        if p is None:
            t_val = 0.0
        elif p[1] in (proof_mod.FIRED, proof_mod.FALLBACK):
            t_val = fire_time(key[0])
        else:
            t_val = avail(p[0], p[1])
        in_progress.discard(key)
        memo[key] = t_val
        return t_val

    at_exit = reachable.get(exit_locus, set())
    worst: float = 0.0
    for out_t in internals.get("out", []):
        if not _arrived_matches(out_t, at_exit, type_dag):
            continue  # coverage already reports the miss
        concrete = out_t if out_t in at_exit else next(
            iter(type_dag.get(out_t, set()) & at_exit)
        )
        t_val = avail(exit_locus, concrete)
        worst = max(worst, t_val)
        if parent_window is not None and t_val > float(parent_window):
            issues.append(
                f"out type '{out_t}': worst-case internal path {t_val:.0f} ms "
                f"exceeds template window_ms {parent_window}"
            )
        else:
            notes.append(
                f"out type '{out_t}': worst-case internal path {t_val:.0f} ms"
                + (f" ≤ window_ms {parent_window}" if parent_window is not None else "")
            )

    if parent_window is None:
        notes.append("template declares no window_ms — budget reported, not enforced")

    if parent_refractory is not None:
        slowest = max(
            (float(g.get("refractory_ms", 0.0)), name.removeprefix(prefix))
            for name, g in gates_spec.items() if name.startswith(prefix)
        ) if any(n.startswith(prefix) for n in gates_spec) else (0.0, "-")
        if slowest[0] > float(parent_refractory):
            issues.append(
                f"internal gate '{slowest[1]}' refractory_ms {slowest[0]:.0f} exceeds "
                f"template refractory_ms {parent_refractory} — gate cannot re-arm "
                f"as fast as its contract promises"
            )
        else:
            notes.append(
                f"slowest internal re-arm {slowest[0]:.0f} ms ('{slowest[1]}') "
                f"≤ template refractory_ms {parent_refractory}"
            )

    return issues, notes


# ── eval battery on the composed harness ───────────────────────────────────────

def run_eval_on_composed(composed: dict) -> tuple[bool, str]:
    """Full opis-eval battery. Errors (exit 1) fail; warnings tolerated."""
    with tempfile.NamedTemporaryFile(
        "w", suffix=".json", prefix="gate_proof_composed_", delete=False
    ) as f:
        json.dump(composed, f, indent=1)
        tmp = f.name
    result = subprocess.run(
        [sys.executable, str(HERE / "eval.py"), tmp],
        capture_output=True, text=True,
    )
    Path(tmp).unlink(missing_ok=True)
    return result.returncode != 1, result.stdout


# ── driver ─────────────────────────────────────────────────────────────────────

def verify_gate_internals(
    internals_path: Path, gates_dir: Path,
) -> tuple[list[str], list[str]]:
    """Run all checks. Returns (issues, notes) — empty issues means proved."""
    internals = json.loads(internals_path.read_text())
    template = internals.get("gate")
    if not template:
        return ["internals file missing 'gate' field"], []

    gate_md = gates_dir / f"{template}.md"
    if not gate_md.exists():
        return [f"template file not found: {gate_md}"], []
    frontmatter = proof_mod.parse_gate_frontmatter(gate_md.read_text())

    issues: list[str] = []
    notes: list[str] = []

    issues += check_contract_consistency(internals, frontmatter)

    composed, entry, exit_locus = build_harness(internals, frontmatter)

    eval_ok_, _eval_out = run_eval_on_composed(composed)
    if not eval_ok_:
        issues.append("opis-eval reports structural errors on the composed harness (exit 1)")

    cov_issues, cov_notes, _wit = check_contract_coverage(composed, internals, exit_locus)
    issues += cov_issues
    notes += cov_notes

    excl_issues, excl_notes = check_outcome_exclusivity(composed, internals, exit_locus)
    issues += excl_issues
    notes += excl_notes

    tim_issues, tim_notes = check_timing_budget(composed, internals, frontmatter, exit_locus)
    issues += tim_issues
    notes += tim_notes

    return issues, notes


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python tools/opis-eval/gate_proof.py <internals.json> [--gates-dir <path>]")
        sys.exit(1)
    internals_path = Path(sys.argv[1])
    gates_dir = HERE.parents[1] / "agents" / "gates"
    if "--gates-dir" in sys.argv:
        gates_dir = Path(sys.argv[sys.argv.index("--gates-dir") + 1])

    print(c("\nopis-gate-proof  ", BOLD) + c(str(internals_path.resolve()), YELLOW))

    issues, notes = verify_gate_internals(internals_path, gates_dir)

    for n in notes:
        print(info(n))
    if not issues:
        print(c("\n✓ internals honor the contract — consistency, coverage, "
                "exclusivity, timing all pass", GREEN))
        sys.exit(0)
    print()
    for i in issues:
        print(err(i))
    print(c(f"\n✗ {len(issues)} violation(s)", RED))
    sys.exit(1)


if __name__ == "__main__":
    main()
