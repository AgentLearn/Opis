#!/usr/bin/env python3
"""
opis-proof — requirement coverage prover

Companion to opis-eval. Where opis-eval answers "is this topology sound?",
opis-proof answers "does every requirement FA claims to have covered actually
have a real path through the graph?" — for each entry in a flow spec's
`requirements` array, and for every one of the target gate's required input
types, it reconstructs the literal route (source locus → ... → target gate)
that satisfies it, the same way a human would trace it on the diagram by
hand. If no such route exists, or the gate/outcome named doesn't even exist,
or the gate's `gate_template` doesn't resolve to a real file in the gates
repo, that's reported as an unproved requirement — not a warning, a missing
wire.

Reachability is computed as a proper AND-join fixed point: a gate only
contributes its emitted types as "reachable" once ALL of its (non-optional)
required types have genuinely arrived via real upstream propagation — not
the blanket "every gate conservatively emits regardless of input" shortcut
opis-eval's check 1 uses for its simpler clean/dirty verdict. That shortcut
is fine for a boolean pass/fail; it produces tautological, useless paths
("this gate's input is satisfied because this gate also happens to emit
the same type name") when you need an actual witness path to show someone.
Genuine cycles (two gates whose requires depend on each other) still can't
be resolved by a fixed point and fall back to the conservative assumption,
same as opis-eval — but that fallback is explicitly marked in the proof
output, never silently presented as a clean trace.

This is intentionally file-based and stateless (no graph database) — the
"proof" is just the path, written out as a list of hops. A future version
could persist these in a graph database to track them across flow versions
without recomputing; for now this recomputes from scratch every run.

Usage:
  python tools/opis-eval/proof.py <flow.json> [--gates-dir <path>]

Exit codes:
  0 — every requirement in the flow has every required input proved
  1 — one or more requirements unproved, or no requirements array present
"""

from __future__ import annotations

import importlib.util
import re
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

# ── load eval.py as a module (sibling dir has a hyphen, can't `import`) ───────

_EVAL_PATH = Path(__file__).resolve().parent / "eval.py"
_spec = importlib.util.spec_from_file_location("opis_eval", _EVAL_PATH)
eval_mod = importlib.util.module_from_spec(_spec)
sys.modules["opis_eval"] = eval_mod  # dataclasses needs this registered before exec
_spec.loader.exec_module(eval_mod)  # type: ignore[union-attr]


# ── ANSI colour helpers (reuse eval.py's) ──────────────────────────────────────

c, ok, err, warn, info, hdr = eval_mod.c, eval_mod.ok, eval_mod.err, eval_mod.warn, eval_mod.info, eval_mod.hdr
GREEN, RED, YELLOW, CYAN, BOLD, DIM = (
    eval_mod.GREEN, eval_mod.RED, eval_mod.YELLOW, eval_mod.CYAN, eval_mod.BOLD, eval_mod.DIM,
)

FIRED = "__fired__"      # gate fired: all its real required inputs genuinely arrived
FALLBACK = "__fallback__"  # gate forced to fire: stuck behind a genuine requires-cycle


# ── reachability with path reconstruction (AND-join fixed point) ──────────────

def trace_reachability_with_paths(
    spec: dict,
) -> tuple[dict[str, set[str]], dict[tuple[str, str], tuple[str, str] | None]]:
    """
    Forward propagation from real sources only, with gates firing (and
    contributing their emitted types onward) only once ALL of their
    non-optional `requires` have genuinely arrived — a proper AND-join,
    not opis-eval's "every gate emits regardless of input" shortcut.

    pred[(node, type)] = None                  → true origin: a source locus
    pred[(node, type)] = (node, "__fired__")    → gate fired for real (all
                                                   requires independently met)
    pred[(node, type)] = (node, "__fallback__") → gate forced to fire because
                                                   it's stuck behind a genuine
                                                   requires-cycle (same
                                                   conservative assumption
                                                   opis-eval makes — flagged,
                                                   never presented as clean)
    pred[(node, type)] = (prev_node, type)      → reached via a real edge
    """
    nodes, gates, edges = eval_mod.build_graph(spec)
    fwd, _ = eval_mod.adjacency(edges)
    type_dag = eval_mod.build_type_dag(spec)

    has_incoming = set(e.dst for e in edges if not e.inhibitor)
    pure_sources = [n for n in nodes if n not in has_incoming]
    loci_spec = spec.get("loci", {})
    explicit_sources = {
        name for name, lspec in loci_spec.items()
        if isinstance(lspec, dict) and lspec.get("source")
    }
    true_sources = set(pure_sources) | explicit_sources

    reachable: dict[str, set[str]] = defaultdict(set)
    pred: dict[tuple[str, str], tuple[str, str] | None] = {}
    fired: set[str] = set()
    queue: deque[str] = deque()

    def add(node: str, ptype: str, origin: tuple[str, str] | None) -> None:
        if ptype not in reachable[node]:
            reachable[node].add(ptype)
            pred[(node, ptype)] = origin
            queue.append(node)

    for s in true_sources:
        for edge in fwd.get(s, []):
            if edge.pulse_type and not edge.inhibitor:
                add(s, edge.pulse_type, None)

    def gate_satisfied(gname: str, gspec: dict) -> bool:
        required = set(gspec.get("requires", [])) - set(gspec.get("optional", []))
        arrived = reachable.get(gname, set())
        for t in required:
            if t in arrived:
                continue
            if type_dag.get(t, set()) & arrived:
                continue
            return False
        return True

    def try_fire(gname: str, gspec: dict, fallback: bool = False) -> None:
        if gname in fired:
            return
        if not fallback and not gate_satisfied(gname, gspec):
            return
        fired.add(gname)
        marker = (gname, FALLBACK if fallback else FIRED)
        for flow in eval_mod.extract_emitted_flows(gspec.get("emits", [])):
            add(gname, flow, marker)

    def drain() -> None:
        while queue:
            node = queue.popleft()
            for edge in fwd.get(node, []):
                if edge.inhibitor:
                    continue
                crossing = (
                    {edge.pulse_type} & reachable[node]
                    if edge.pulse_type else set(reachable[node])
                )
                for t in crossing:
                    add(edge.dst, t, (node, t))
            if node in gates:
                try_fire(node, gates[node])

    drain()

    # Phase 2: anything still un-fired is stuck behind a genuine requires-cycle
    # (two gates each waiting on the other). Force it, same conservative
    # assumption opis-eval makes — but every path through here is marked.
    for gname, gspec in gates.items():
        if gname not in fired:
            try_fire(gname, gspec, fallback=True)
    drain()

    return dict(reachable), pred


def reconstruct_path(
    pred: dict[tuple[str, str], tuple[str, str] | None], node: str, ptype: str
) -> list[dict[str, Any]]:
    """Walk the predecessor chain back to a true origin or a fired/fallback
    gate boundary (firing is treated as a terminal node here — the proof for
    *why* that gate could fire is its own required-types' proofs, not
    recursed into inline)."""
    chain: list[dict[str, Any]] = []
    cur = (node, ptype)
    seen = {cur}
    while True:
        p = pred.get(cur)
        if p is None:
            chain.append({"node": cur[0], "pulse_type": cur[1]})
            break
        if p[1] in (FIRED, FALLBACK):
            chain.append({
                "node": cur[0], "pulse_type": cur[1],
                "fired": "fired" if p[1] == FIRED else "fallback",
            })
            break
        chain.append({"node": cur[0], "pulse_type": cur[1]})
        if p in seen:
            break  # defensive
        seen.add(p)
        cur = p
    chain.reverse()
    return chain


# ── per-requirement proof ───────────────────────────────────────────────────────

def find_requirement_proof(
    spec: dict,
    gates_dir: Path,
    requirement: dict,
    reachable: dict[str, set[str]],
    pred: dict[tuple[str, str], tuple[str, str] | None],
    type_dag: dict[str, set[str]],
) -> dict:
    target = requirement.get("target", {}) or {}
    gate_name = target.get("gate")
    outcome_name = target.get("outcome")

    result: dict[str, Any] = {
        "id": requirement.get("id"),
        "text": requirement.get("text"),
        "target": target,
        "status": "unproved",
        "proofs": {},   # required_type -> path (list of hops)
        "issues": [],   # blocks "proved"
        "notes": [],    # informational (e.g. fallback/cyclic origin) — doesn't block
    }

    gates_spec = spec.get("gates", {})
    if not gate_name or gate_name not in gates_spec:
        result["issues"].append(f"target gate '{gate_name}' does not exist in this flow")
        return result

    gspec = gates_spec[gate_name]

    template = gspec.get("gate_template")
    if template and not (gates_dir / f"{template}.md").exists():
        result["issues"].append(
            f"gate_template '{template}' referenced by gate '{gate_name}' "
            f"does not exist in {gates_dir} — phantom gate"
        )

    emits = gspec.get("emits", [])
    outcome_items = [e for e in emits if isinstance(e, dict)]
    outcome_names = {e.get("outcome") for e in outcome_items if e.get("outcome")}
    if outcome_name and outcome_names and outcome_name not in outcome_names:
        result["issues"].append(
            f"outcome '{outcome_name}' not found in gate '{gate_name}' emits "
            f"({sorted(outcome_names)})"
        )

    required = set(gspec.get("requires", [])) - set(gspec.get("optional", []))
    if not required:
        result["issues"].append(f"gate '{gate_name}' declares no requires — nothing to prove")
        return result

    arrived = reachable.get(gate_name, set())
    all_satisfied = True

    for t in sorted(required):
        satisfied_type = t if t in arrived else None
        if not satisfied_type:
            hit = type_dag.get(t, set()) & arrived
            if hit:
                satisfied_type = sorted(hit)[0]
        if not satisfied_type:
            all_satisfied = False
            result["issues"].append(
                f"required type '{t}' (or any subtype) is not reachable at "
                f"gate '{gate_name}' from any source"
            )
            continue
        path = reconstruct_path(pred, gate_name, satisfied_type)
        result["proofs"][t] = path
        if path and path[0].get("fired") == "fallback":
            result["notes"].append(
                f"'{t}' only resolves via a conservative cyclic fallback at "
                f"'{path[0]['node']}' — two gates depend on each other; not a "
                f"clean external trace"
            )

    if all_satisfied and not result["issues"]:
        result["status"] = "proved"

    return result


def verify_requirements(spec: dict, gates_dir: Path) -> list[dict]:
    requirements = spec.get("requirements", [])
    reachable, pred = trace_reachability_with_paths(spec)
    type_dag = eval_mod.build_type_dag(spec)
    return [
        find_requirement_proof(spec, gates_dir, r, reachable, pred, type_dag)
        for r in requirements
    ]


# ── gate conformance: does a flow's gate instance honor its claimed template? ──
#
# A flow's gate stub (`gate_template: "delivery_router", requires: [...]`) can
# claim a template without actually wiring what that template demands — e.g.
# delivery_router.md declares BOTH `order` and `location` as required input
# slots, but a flow can write `requires: ["seat_reservation_order"]` and drop
# `location` entirely. Nothing else catches this: opis-eval only checks the
# flow's own internal graph; find_requirement_proof only checks reachability
# of whatever the flow itself claims. This checks the claim against the
# template file's own declared input/output bundle (the "obvious part").

def parse_gate_frontmatter(text: str) -> dict[str, Any]:
    """Minimal parser for the gate .md frontmatter shape FA's
    GATE_GENERATION_PROMPT produces (see agents/fa/prompts.py). Deliberately
    dependency-free — no pyyaml — to match the rest of this codebase's
    regex-based frontmatter handling (eval.py/agent.py do the same for
    `kind:`/`name:`). Only understands this fixed shape, not general YAML:

        ---
        name: order_intake
        kind: gate
        input_slots:
          - name: order
            type: order
            required: true
        output_slots:
          - name: accepted_order
            type: accepted_order
        window_ms: 5000
        ---
    """
    m = re.match(r"^---\s*\n(.*?\n)---\s*\n", text, re.DOTALL)
    if not m:
        return {"input_slots": [], "output_slots": []}
    lines = m.group(1).split("\n")

    result: dict[str, Any] = {"input_slots": [], "output_slots": []}
    current_list: str | None = None
    current_slot: dict[str, str] | None = None

    def flush() -> None:
        nonlocal current_slot
        if current_slot is not None and current_list is not None:
            result.setdefault(current_list, []).append(current_slot)
        current_slot = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if not line[:1].isspace():  # top-level key
            flush()
            key, _, val = stripped.partition(":")
            key, val = key.strip(), val.strip()
            if key in ("input_slots", "output_slots"):
                current_list = key
            else:
                current_list = None
                if val:
                    result[key] = val
            continue
        if stripped.startswith("- "):  # new slot list item
            flush()
            current_slot = {}
            rest = stripped[2:].strip()
            if rest:
                k, _, v = rest.partition(":")
                current_slot[k.strip()] = v.strip()
        elif ":" in stripped and current_slot is not None:
            k, _, v = stripped.partition(":")
            current_slot[k.strip()] = v.strip()

    flush()
    return result


def _required_input_types(frontmatter: dict) -> set[str]:
    return {
        s["type"] for s in frontmatter.get("input_slots", [])
        if s.get("type") and s.get("required", "true").strip().lower() != "false"
    }


def _output_types(frontmatter: dict) -> set[str]:
    return {s["type"] for s in frontmatter.get("output_slots", []) if s.get("type")}


def compare_gate_bundles(a_fm: dict, b_fm: dict) -> dict:
    """Structural comparison of two gate frontmatter bundles — the 'obvious
    part' of gate equality (input/output slot types). Doesn't judge behavior
    or written description, only the type-level contract."""
    a_req, b_req = _required_input_types(a_fm), _required_input_types(b_fm)
    a_out, b_out = _output_types(a_fm), _output_types(b_fm)
    return {
        "identical": a_req == b_req and a_out == b_out,
        "required_inputs_match": a_req == b_req,
        "outputs_match": a_out == b_out,
        "a_required_inputs": sorted(a_req), "b_required_inputs": sorted(b_req),
        "a_outputs": sorted(a_out), "b_outputs": sorted(b_out),
        "in_a_not_b_inputs": sorted(a_req - b_req), "in_b_not_a_inputs": sorted(b_req - a_req),
        "in_a_not_b_outputs": sorted(a_out - b_out), "in_b_not_a_outputs": sorted(b_out - a_out),
    }


def check_gate_conformance(spec: dict, gates_dir: Path) -> list[dict]:
    """For every gate instance that claims a gate_template, verify the
    instance's `requires` genuinely covers every required input slot type the
    template declares (subtype-aware via this flow's archetype DAG). A
    template-required type that the instance never asks for is a sign the
    gate was bent to fit a need it doesn't structurally cover — exactly how
    delivery_router (requires order + location) ended up reused for a
    ticket-routing gate that only ever supplied an order-shaped type and
    silently dropped `location` entirely."""
    type_dag = eval_mod.build_type_dag(spec)
    issues: list[dict] = []

    for gname, gspec in spec.get("gates", {}).items():
        template = gspec.get("gate_template")
        if not template:
            continue
        template_path = gates_dir / f"{template}.md"
        if not template_path.exists():
            continue  # phantom gate_template — already caught by find_requirement_proof

        fm = parse_gate_frontmatter(template_path.read_text())
        template_required = _required_input_types(fm)
        instance_requires = set(gspec.get("requires", [])) - set(gspec.get("optional", []))

        uncovered = []
        for req_type in sorted(template_required):
            covered = (
                req_type in instance_requires
                or bool(type_dag.get(req_type, set()) & instance_requires)
                or any(req_type in type_dag.get(it, set()) for it in instance_requires)
            )
            if not covered:
                uncovered.append(req_type)

        if uncovered:
            issues.append({
                "gate": gname,
                "gate_template": template,
                "template_required_inputs": sorted(template_required),
                "instance_requires": sorted(instance_requires),
                "uncovered": uncovered,
                "message": (
                    f"gate '{gname}' claims gate_template '{template}', which requires "
                    f"input slot type(s) {uncovered}, but the instance's requires "
                    f"{sorted(instance_requires)} never covers {'this' if len(uncovered)==1 else 'these'} "
                    f"(or any subtype/supertype) — the gate template's actual contract "
                    f"isn't honored, only superficially referenced"
                ),
            })

    return issues


# ── wiring-gap vs. no-domain-source ──────────────────────────────────────────
#
# opis-eval's "requires X but no upstream path produces this type" reads the
# same whether X just isn't wired up yet (genuinely fixable by adding a
# synapse) or X is never produced ANYWHERE in this entire flow by anything
# (not a wiring gap at all — the concept doesn't exist in this domain's model,
# and no amount of rewiring existing nodes will manufacture it). FA can't tell
# these apart from the error text alone, so it keeps trying to wire the
# unwireable instead of reconsidering the gate choice. This distinguishes them.

def types_ever_emitted(spec: dict) -> set[str]:
    """Every pulse type that appears ANYWHERE in this spec as something
    emitted — by any synapse's pulse_type(s), or any gate's emits — whether
    or not there's a valid path to it. The full universe of things this flow
    ever claims to produce, connected or not."""
    types: set[str] = set()
    for syn in spec.get("synapses", []):
        if "pulse_types" in syn:
            types.update(t for t in (syn.get("pulse_types") or []) if t)
        elif syn.get("pulse_type"):
            types.add(syn["pulse_type"])
    for gspec in spec.get("gates", {}).values():
        types.update(eval_mod.extract_emitted_flows(gspec.get("emits", [])))
    return types


def diagnose_unreachable_type(
    spec: dict, required_type: str, type_dag: dict[str, set[str]], ever_emitted: set[str] | None = None
) -> str:
    """'wiring-gap' — the type (or a subtype) IS produced somewhere in this
    flow, just not connected to the gate that needs it. Fixable by adding a
    synapse.
    'no-domain-source' — nothing anywhere in this flow ever produces this
    type or any subtype. Not a wiring gap — either the wrong gate_template
    was chosen, or a genuinely new source locus needs to be introduced."""
    ever_emitted = types_ever_emitted(spec) if ever_emitted is None else ever_emitted
    candidates = {required_type} | type_dag.get(required_type, set())
    return "wiring-gap" if candidates & ever_emitted else "no-domain-source"


_REQUIRES_LINE_RE = re.compile(r"requires \[(.*?)\] but no upstream path produces")


def enrich_reachability_errors(spec: dict, error_lines: list[str]) -> list[str]:
    """Append a wiring-gap / no-domain-source diagnosis to each opis-eval
    'requires [...] but no upstream path produces...' line. Leaves other
    error lines (dead-end outputs, etc.) untouched."""
    type_dag = eval_mod.build_type_dag(spec)
    ever_emitted = types_ever_emitted(spec)
    enriched = []
    for line in error_lines:
        m = _REQUIRES_LINE_RE.search(line)
        if not m:
            enriched.append(line)
            continue
        required_types = [t.strip().strip("'\"") for t in m.group(1).split(",") if t.strip()]
        notes = []
        for t in required_types:
            kind = diagnose_unreachable_type(spec, t, type_dag, ever_emitted)
            if kind == "no-domain-source":
                notes.append(
                    f"'{t}' is NEVER produced anywhere in this entire flow — no locus or "
                    f"gate emits this type or any subtype. This is NOT a wiring gap; adding "
                    f"a synapse cannot fix it. Either this gate_template is the wrong choice "
                    f"for this need, or a genuinely new source locus must be introduced. "
                    f"Strongly consider proposing a new gate via ADR instead of continuing "
                    f"to rewire around this."
                )
            else:
                notes.append(f"'{t}' is produced elsewhere in this flow, just not wired to this gate — add a synapse.")
        enriched.append(line + "\n      " + "\n      ".join(notes))
    return enriched


# ── CLI ──────────────────────────────────────────────────────────────────────

def format_path(path: list[dict[str, Any]]) -> str:
    parts = []
    for hop in path:
        label = f"{hop['node']}({hop['pulse_type']})"
        if hop.get("fired") == "fired":
            label += " [fired]"
        elif hop.get("fired") == "fallback":
            label += " [FALLBACK-cyclic]"
        parts.append(label)
    return " → ".join(parts)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python tools/opis-eval/proof.py <flow.json> [--gates-dir <path>]")
        sys.exit(1)

    flow_path = Path(sys.argv[1])
    if "--gates-dir" in sys.argv:
        idx = sys.argv.index("--gates-dir")
        gates_dir = Path(sys.argv[idx + 1])
    else:
        # default: <repo_root>/agents/gates, derived from
        # agents/output/<kata>/flow/flow_vN.json → parents[3] == agents/
        gates_dir = flow_path.resolve().parents[3] / "gates"

    spec = eval_mod.load_spec(flow_path)
    print(c("\nopis-proof  ", BOLD) + c(str(flow_path.resolve()), YELLOW))
    print(info(f"gates repo: {gates_dir}"))

    requirements = spec.get("requirements", [])
    if not requirements:
        print(warn("no `requirements` array in this flow — nothing to prove"))
        sys.exit(1)

    results = verify_requirements(spec, gates_dir)

    proved = 0
    unproved = 0
    for r in results:
        label = f"{r['id']}: {r['text']}"
        if r["status"] == "proved":
            proved += 1
            print(ok(label))
            for t, path in r["proofs"].items():
                print(info(f"  [{t}] {format_path(path)}"))
            for note in r["notes"]:
                print(warn(f"  {note}"))
        else:
            unproved += 1
            print(err(label))
            for issue in r["issues"]:
                print(err(f"  {issue}"))
            for t, path in r["proofs"].items():
                print(info(f"  [{t}] {format_path(path)}"))

    print(hdr("Gate conformance (does each instance honor its claimed template's bundle?)"))
    conformance_issues = check_gate_conformance(spec, gates_dir)
    if not conformance_issues:
        print(ok("every gate instance covers its template's required input slots"))
    else:
        for issue in conformance_issues:
            print(err(issue["message"]))

    print()
    print(c(f"{proved} proved, {unproved} unproved", GREEN if not unproved else RED))
    if conformance_issues:
        print(c(f"{len(conformance_issues)} gate(s) don't conform to their claimed template", RED))
    sys.exit(0 if not unproved and not conformance_issues else 1)


if __name__ == "__main__":
    main()
