#!/usr/bin/env python3
"""
opis-eval — static pulse network analyzer

Analogous to Petri net structural analysis: answers "is this topology sound?"
before injecting a single pulse. Complements pulse-sim (which answers runtime
questions) by catching structural impossibilities statically.

Checks:
  1. Reachability       — which pulse types can arrive at each gate?
                          Gates whose `requires` can never be satisfied are dead.
                          Subtype-aware: requires "food" satisfied by "sandwich" (IS-A food).
  2. Orphans            — loci with no synapses (archetypes are type DAG, not graph nodes)
  3. Cycles (SCCs)      — Tarjan's algorithm; reported, not flagged (cycles are valid)
  4. Hop depth          — minimum hops from any injection point to each gate
  5. Sentinel coverage  — gates with no sentinel upstream are flagged (security gap)
  5b. Authorization reality — ERROR: gate requires a sentinel-emitted (sig-bearing)
                          type but declares auth_required:false (credential consumed,
                          never verified — CA falsification class #6, flow_v5)
  6. Silent gates       — gates that fire but emit nothing (signal dead-ends)
  7. Window feasibility — cascade min-hops vs gate window_ms (warns if path may time out)
  8. Cardinality        — shared loci flagged as scaling ceilings; per_instance/shared
                          overlap is an error; referenced loci must exist
  9. Topology groups    — slot isolation (no direct slot→slot synapse), shared loci
                          declared for cross-slot reach, zoom interface references valid
 10. Locus type leak    — warning: locus emits type not present on incoming synapses (likely gate)
 11. Emit coverage      — every flow in every gate outcome bundle has a consuming synapse
 12. Sync gates          — kind:"sync" gates are explicit consistency boundaries; verifies
                          count matches upstream cardinality; flags N-cardinality sources
                          reaching non-sync gates directly (eventual path)
 13. Gate internals      — gate files (gates/GateName/v1.json) validated as standalone
                          sub-topologies: reachability, emit coverage, orphans.
                          Pull synapses checked for round-trip pair.
                          Legacy `mechanism` blocks in monolithic specs are also validated.

Usage:
  python -m tools.opis-eval.eval <spec.json>
  python tools/opis-eval/eval.py <spec.json>
  python tools/opis-eval/eval.py flow.json gates/GateName/v1.json   # compose + check one gate

Exit codes:
  0 — clean (no errors, no warnings)
  1 — one or more errors (structural failure)
  2 — warnings only (structurally valid, but has flagged concerns)
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ── ANSI colours ──────────────────────────────────────────────────────────────

import os

def _use_color() -> bool:
    try:
        return os.isatty(sys.stdout.fileno())
    except Exception:
        return False

USE_COLOR = _use_color()
RESET  = "\033[0m"
RED    = "\033[31m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
BOLD   = "\033[1m"
DIM    = "\033[2m"

def c(text: str, *codes: str) -> str:
    if not USE_COLOR:
        return text
    return "".join(codes) + text + RESET

def ok(msg: str)   -> str: return c("  ✓ " + msg, GREEN)
def err(msg: str)  -> str: return c("  ✗ " + msg, RED)
def warn(msg: str) -> str: return c("  ⚠ " + msg, YELLOW)
def info(msg: str) -> str: return c("  · " + msg, DIM)
def hdr(msg: str)  -> str: return c(f"\n{msg}", BOLD)


# ── Spec loading ───────────────────────────────────────────────────────────────

def load_spec(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        print(err(f"spec file not found: {path}"))
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(err(f"invalid JSON in spec: {e}"))
        sys.exit(1)


def compose_flow_gate(flow: dict, gate_file: dict) -> dict:
    """
    Merge a gate file into a flow spec for combined validation.

    Gate file format:
      {
        "gate":    "GateName",
        "version": 1,
        "description": "...",
        "in":  ["IncomingPulseType"],   # must match flow-level wiring
        "out": ["OutgoingPulseType"],   # must match flow-level wiring
        "loci":    { ... },             # internal loci
        "gates":   { ... },             # internal sub-gates
        "synapses": [ ... ]             # internal wiring
      }

    The gate's internal nodes are namespaced as "GateName__NodeName" so they
    cannot collide with top-level flow nodes. The gate stub in the flow is
    replaced with a full gate whose requires/emits are derived from in/out.
    """
    import copy
    composed = copy.deepcopy(flow)
    gate_name = gate_file.get("gate")
    if not gate_name:
        raise ValueError("gate file missing 'gate' field")

    prefix       = gate_name + "__"
    entry_locus  = prefix + "_entry"   # virtual source that seeds in-types
    exit_locus   = prefix + "_exit"    # virtual sink that absorbs out-types

    # Replace the flow-level stub with a full gate derived from the gate file
    stub = composed.get("gates", {}).get(gate_name, {})
    full_gate: dict = {
        "description": gate_file.get("description", stub.get("description", "")),
        "kind":        stub.get("kind", "gate"),
        "requires":    gate_file.get("in", []),
        "emits": stub.get("emits") or (
            [{"outcome": "default", "flows": gate_file.get("out", []), "weight": 1.0}]
            if gate_file.get("out") else []
        ),
    }
    for k in ("logic", "optional", "window_ms", "refractory_ms",
              "input_timeout_ms", "trips_on", "trip_threshold",
              "trip_window_ms", "recovery_ms", "count", "correlation_key"):
        if k in stub:
            full_gate[k] = stub[k]
    composed.setdefault("gates", {})[gate_name] = full_gate

    # Virtual boundary loci:
    #   entry — source:true, seeds the gate's `in` pulse types into the internal topology
    #   exit  — plain locus, absorbs `out` pulse types from the internal topology
    # These replace `gate_name` references in internal synapses so the gate's own
    # node (which is a gate and emits different types) isn't used as a pass-through.
    composed.setdefault("loci", {})[entry_locus] = {
        "description": f"virtual entry boundary for {gate_name} — seeds in-types",
        "source": True,
    }
    composed.setdefault("loci", {})[exit_locus] = {
        "description": f"virtual exit boundary for {gate_name} — absorbs out-types",
    }

    # Internal loci — namespaced
    internal_nodes: set[str] = (
        set(gate_file.get("loci", {}).keys()) |
        set(gate_file.get("gates", {}).keys())
    )
    for lname, lspec in gate_file.get("loci", {}).items():
        composed.setdefault("loci", {})[prefix + lname] = lspec

    # Internal sub-gates — namespaced
    for gname, gspec in gate_file.get("gates", {}).items():
        composed.setdefault("gates", {})[prefix + gname] = gspec

    # Internal synapses:
    #   from/to == gate_name → reroute through virtual boundary loci
    #   from/to in internal_nodes → namespace them
    for syn in gate_file.get("synapses", []):
        new_syn = copy.deepcopy(syn)
        src = syn.get("from", "")
        dst = syn.get("to", "")
        if src == gate_name:
            new_syn["from"] = entry_locus
        elif src in internal_nodes:
            new_syn["from"] = prefix + src
        if dst == gate_name:
            new_syn["to"] = exit_locus
        elif dst in internal_nodes:
            new_syn["to"] = prefix + dst
        composed.setdefault("synapses", []).append(new_syn)

    return composed


# ── Stub normalisation ────────────────────────────────────────────────────────

def _normalize_gate(gspec: dict) -> dict:
    """
    Normalise a flow-level gate stub that uses `in`/`out` shorthand into the
    full gate format that all eval checks expect (`requires` / `emits`).

    Flow-level stub:
      { "kind": "gate", "in": ["OrderSubmission"], "out": ["OrderConfirmed"], ... }

    Full format:
      { "kind": "gate", "requires": ["OrderSubmission"],
        "emits": [{"outcome": "default", "flows": ["OrderConfirmed"], "weight": 1.0}] }

    Leaves full-format gates untouched.
    """
    if "in" not in gspec and "out" not in gspec:
        return gspec
    g = dict(gspec)
    if "in" in g:
        if "requires" not in g:
            g["requires"] = g.pop("in")
        else:
            g.pop("in")
    if "out" in g:
        if "emits" not in g:
            out = g.pop("out", [])
            g["emits"] = [{"outcome": "default", "flows": out, "weight": 1.0}] if out else []
        else:
            g.pop("out")
    return g


def _normalize_spec_gates(spec: dict) -> dict:
    """Return spec with all gate stubs normalised (top-level and inside topology_groups)."""
    if "gates" not in spec and "topology_groups" not in spec:
        return spec
    s = dict(spec)
    if "gates" in s:
        s["gates"] = {n: _normalize_gate(g) for n, g in s["gates"].items()}
    if "topology_groups" in s:
        tgs: dict = {}
        for tg_name, tg in s["topology_groups"].items():
            if "gates" in tg:
                tg = dict(tg)
                tg["gates"] = {n: _normalize_gate(g) for n, g in tg["gates"].items()}
            tgs[tg_name] = tg
        s["topology_groups"] = tgs
    return s


# ── Graph construction ─────────────────────────────────────────────────────────

@dataclass
class Edge:
    src:        str
    dst:        str
    pulse_type: str | None   # None = any type passes
    inhibitor:  bool = False


def build_graph(spec: dict) -> tuple[dict, dict, list[Edge]]:
    """
    Returns:
      nodes   — {name: kind}  where kind ∈ {locus, archetype, gate}
      gates   — {name: gate_spec}
      edges   — list[Edge]
    """
    nodes: dict[str, str] = {}
    for name in spec.get("loci", {}):
        nodes[name] = "locus"
    for name in spec.get("archetypes", {}):
        nodes[name] = "archetype"
    for name in spec.get("gates", {}):
        nodes[name] = "gate"

    gates = spec.get("gates", {})

    edges: list[Edge] = []
    for syn in spec.get("synapses", []):
        src = syn.get("from", "")
        dst = syn.get("to", "")
        inh = syn.get("inhibitor", False)
        # Support both pulse_type (singular) and pulse_types (plural)
        pts: list[str | None]
        if "pulse_types" in syn:
            pts = syn["pulse_types"] or [None]
        elif "pulse_type" in syn:
            pts = [syn["pulse_type"]]
        else:
            pts = [None]
        if src and dst:
            for pt in pts:
                edges.append(Edge(src, dst, pt, inh))

    return nodes, gates, edges


def extract_emitted_flows(emits: list) -> list[str]:
    """
    Handle both emits formats:
      Old: ["TypeA", "TypeB"]
      New: [{"outcome": "ok", "flows": ["TypeA", "TypeB"]}, ...]
    Returns the flat union of all possible flow types.
    """
    flows: list[str] = []
    for item in emits:
        if isinstance(item, str):
            flows.append(item)
        elif isinstance(item, dict):
            flows.extend(item.get("flows", []))
    return flows


_BASE_TAXONOMY_CACHE: dict[str, str] | None = None


def load_base_taxonomy() -> dict[str, str]:
    """
    Parse agents/slot_types/index.md's table into {type: parent} for base
    slot types with a non-root parent (e.g. accepted_order → order).

    Flows only declare their own domain archetypes; base→base edges live
    solely in this index. Without them, subtype resolution breaks whenever
    coverage depends on a base-level edge (e.g. accepted_cancellation_order
    extends accepted_order extends order — the second hop was invisible,
    so a delivery_router `order` slot rejected a legitimate subtype).
    Anchored to this repo's layout; returns {} if the index is absent.
    """
    global _BASE_TAXONOMY_CACHE
    if _BASE_TAXONOMY_CACHE is not None:
        return _BASE_TAXONOMY_CACHE
    edges: dict[str, str] = {}
    index = Path(__file__).resolve().parents[2] / "agents" / "slot_types" / "index.md"
    if index.exists():
        for line in index.read_text().splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 2 and cells[0] and not set(cells[0]) <= {"-", " "}:
                name, parent = cells[0], cells[1]
                if name != "type" and parent and parent not in ("—", "-", ""):
                    edges[name] = parent
    _BASE_TAXONOMY_CACHE = edges
    return edges


def build_type_dag(spec: dict) -> dict[str, set[str]]:
    """
    Build subtype map from archetype `extends` declarations, merged with the
    base slot-type taxonomy (agents/slot_types/index.md).
    Returns {supertype: set_of_all_subtypes} (transitive closure).

    Example: sandwich extends food, food extends consumable
      → {"food": {"sandwich"}, "consumable": {"food", "sandwich"}}
    """
    archetypes = spec.get("archetypes", {})
    children: dict[str, set[str]] = defaultdict(set)
    for name, parent in load_base_taxonomy().items():
        children[parent].add(name)
    for name, aspec in archetypes.items():
        if isinstance(aspec, dict):
            parent = aspec.get("extends")
            if parent:
                children[parent].add(name)

    # Transitive closure via BFS per type
    subtypes: dict[str, set[str]] = {}
    all_types = set(archetypes.keys()) | set(children.keys())
    for t in all_types:
        if t in subtypes:
            continue
        visited: set[str] = set()
        queue: deque[str] = deque(children.get(t, []))
        while queue:
            child = queue.popleft()
            if child not in visited:
                visited.add(child)
                queue.extend(children.get(child, []))
        subtypes[t] = visited

    return subtypes


def adjacency(edges: list[Edge]) -> tuple[dict[str, list[Edge]], dict[str, list[Edge]]]:
    """Forward and reverse adjacency lists."""
    fwd: dict[str, list[Edge]] = defaultdict(list)
    rev: dict[str, list[Edge]] = defaultdict(list)
    for e in edges:
        fwd[e.src].append(e)
        rev[e.dst].append(e)
    return fwd, rev


# ── Check 1: reachability ──────────────────────────────────────────────────────

def check_reachability(
    nodes: dict[str, str],
    gates: dict[str, Any],
    edges: list[Edge],
    type_dag: dict[str, set[str]] | None = None,
    spec: dict | None = None,
) -> tuple[list[str], list[str], dict[str, set[str]]]:
    """
    Forward dataflow: propagate reachable pulse types from sources.

    A node is an injection point (source) if it has no incoming non-inhibitor edges.
    Subtype-aware: requires "food" is satisfied if "sandwich" (IS-A food) is reachable.

    Returns:
      errors   — gates whose requires can never be satisfied
      warnings — (unused, reserved)
      reachable_types — {node: set of pulse types that can arrive there}
    """
    fwd, rev = adjacency(edges)
    type_dag = type_dag or {}

    # Identify injection points: nodes with no incoming signal edges
    has_incoming = set(e.dst for e in edges if not e.inhibitor)
    sources = [n for n in nodes if n not in has_incoming]

    # reachable_types[node] = set of pulse types that can arrive at this node
    reachable: dict[str, set[str]] = defaultdict(set)

    # Pure sources (no incoming edges) seed from their outgoing typed synapses.
    for s in sources:
        for edge in fwd.get(s, []):
            if edge.pulse_type and not edge.inhibitor:
                reachable[s].add(edge.pulse_type)

    # Loci declared source=true are external actors/APIs/sensors that inject
    # pulses from the real world. They seed their outgoing types regardless of
    # whether they also receive feedback from the graph.
    loci_spec = spec.get("loci", {}) if spec else {}
    explicit_sources = {
        name for name, lspec in loci_spec.items()
        if isinstance(lspec, dict) and lspec.get("source")
    }
    for name in explicit_sources:
        if name in sources:
            continue  # already seeded above
        for edge in fwd.get(name, []):
            if edge.pulse_type and not edge.inhibitor:
                reachable[name].add(edge.pulse_type)

    # Gates produce all flows across all their outcomes (conservative union)
    gate_emits: dict[str, set[str]] = {
        gname: set(extract_emitted_flows(gspec.get("emits", [])))
        for gname, gspec in gates.items()
    }
    for gname in gates:
        reachable[gname].update(gate_emits[gname])

    # Propagate via BFS (forward).
    # NO PASS-THROUGH (semantics decision 2026-07-01, confirmed against the
    # twin): a gate forwards only types it EMITS — a pulse that merely arrived
    # at a gate does not relay across its outgoing synapses. Loci (passive
    # carriers) still relay everything that reaches them.
    queue: deque[str] = deque(
        sources + list(gates.keys()) + list(explicit_sources - set(sources))
    )
    visited: set[str] = set()

    while queue:
        node = queue.popleft()
        if node in visited:
            continue
        visited.add(node)

        forwardable = (
            reachable[node] & gate_emits[node] if node in gates
            else set(reachable[node])
        )
        for edge in fwd.get(node, []):
            if edge.inhibitor:
                continue
            crossing = (
                {edge.pulse_type} & forwardable
                if edge.pulse_type
                else set(forwardable)
            )
            before = len(reachable[edge.dst])
            reachable[edge.dst].update(crossing)
            if len(reachable[edge.dst]) > before:
                queue.append(edge.dst)
                visited.discard(edge.dst)

    # Check gates — subtype-aware; optional types are enrichment, not required
    errors: list[str] = []
    warnings: list[str] = []
    for gname, gspec in gates.items():
        required = set(gspec.get("requires", []))
        # optional types enrich the gate but are not required for firing
        optional_types = set(gspec.get("optional", []))
        required -= optional_types  # just in case of overlap, don't flag optionals
        if not required:
            continue
        arrived = reachable.get(gname, set())
        missing = required - arrived
        # A required type T is also satisfied if any subtype of T arrived
        actually_missing = set()
        for t in missing:
            subtypes_of_t = type_dag.get(t, set())
            if not (subtypes_of_t & arrived):
                actually_missing.add(t)
        if actually_missing:
            errors.append(
                f"gate '{gname}': requires {sorted(actually_missing)} but "
                f"no upstream path produces {'these types' if len(actually_missing) > 1 else 'this type'} "
                f"(or any subtype) — gate can never fire"
            )

    return errors, warnings, dict(reachable)


# ── Check 2: orphans ──────────────────────────────────────────────────────────

def check_orphans(nodes: dict[str, str], edges: list[Edge]) -> list[str]:
    """
    Flag loci with no synapses. Archetypes are type DAG entries — they are type
    labels on pulses, not graph nodes, so they are excluded from this check.
    """
    connected = set(e.src for e in edges) | set(e.dst for e in edges)
    orphans = []
    for name, kind in nodes.items():
        if kind in ("gate", "archetype"):
            continue
        if name not in connected:
            orphans.append(f"{kind} '{name}' has no synapses — unreachable island")
    return orphans


# ── Check 3: SCCs (Tarjan's) ──────────────────────────────────────────────────

def find_sccs(nodes: dict[str, str], edges: list[Edge]) -> list[list[str]]:
    """Tarjan's SCC. Returns list of SCCs with >1 node (i.e. real cycles)."""
    fwd, _ = adjacency(edges)
    index_counter = [0]
    stack = []
    lowlink: dict[str, int] = {}
    index:   dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    sccs: list[list[str]] = []

    def strongconnect(v: str) -> None:
        index[v]    = index_counter[0]
        lowlink[v]  = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack[v] = True

        for edge in fwd.get(v, []):
            w = edge.dst
            if w not in index:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink.get(w, lowlink[v]))
            elif on_stack.get(w, False):
                lowlink[v] = min(lowlink[v], index[w])

        if lowlink[v] == index[v]:
            scc = []
            while True:
                w = stack.pop()
                on_stack[w] = False
                scc.append(w)
                if w == v:
                    break
            if len(scc) > 1:
                sccs.append(scc)

    # Use iterative DFS to avoid Python recursion limit on large specs
    all_nodes = list(nodes.keys())
    for n in all_nodes:
        if n not in index:
            # iterative Tarjan
            _tarjan_iterative(n, fwd, index, lowlink, on_stack, stack, index_counter, sccs)

    return sccs


def _tarjan_iterative(
    root: str,
    fwd: dict[str, list[Edge]],
    index: dict[str, int],
    lowlink: dict[str, int],
    on_stack: dict[str, bool],
    stack: list[str],
    index_counter: list[int],
    sccs: list[list[str]],
) -> None:
    """Iterative Tarjan's SCC to avoid recursion depth issues."""
    # Each frame: (node, iterator over neighbours, parent)
    call_stack = [(root, iter(fwd.get(root, [])), None)]
    index[root]   = index_counter[0]
    lowlink[root] = index_counter[0]
    index_counter[0] += 1
    stack.append(root)
    on_stack[root] = True

    while call_stack:
        v, neighbours, parent = call_stack[-1]
        try:
            edge = next(neighbours)
            w = edge.dst
            if w not in index:
                index[w]   = index_counter[0]
                lowlink[w] = index_counter[0]
                index_counter[0] += 1
                stack.append(w)
                on_stack[w] = True
                call_stack.append((w, iter(fwd.get(w, [])), v))
            elif on_stack.get(w, False):
                lowlink[v] = min(lowlink[v], index[w])
        except StopIteration:
            call_stack.pop()
            if call_stack:
                parent_v = call_stack[-1][0]
                lowlink[parent_v] = min(lowlink[parent_v], lowlink[v])
            if lowlink[v] == index[v]:
                scc = []
                while True:
                    w = stack.pop()
                    on_stack[w] = False
                    scc.append(w)
                    if w == v:
                        break
                if len(scc) > 1:
                    sccs.append(scc)


# ── Check 4: hop depth ────────────────────────────────────────────────────────

def check_hop_depth(
    nodes: dict[str, str],
    gates: dict[str, Any],
    edges: list[Edge],
) -> dict[str, int]:
    """BFS from injection points. Returns {gate_name: min_hops}."""
    fwd, rev = adjacency(edges)
    has_incoming = set(e.dst for e in edges if not e.inhibitor)
    sources = [n for n in nodes if n not in has_incoming]

    depth: dict[str, int] = {}
    queue: deque[tuple[str, int]] = deque((s, 0) for s in sources)
    while queue:
        node, d = queue.popleft()
        if node in depth:
            continue
        depth[node] = d
        for edge in fwd.get(node, []):
            if edge.dst not in depth:
                queue.append((edge.dst, d + 1))

    return {g: depth[g] for g in gates if g in depth}


# ── Check 5: sentinel coverage ────────────────────────────────────────────────

def check_sentinel_coverage(
    gates: dict[str, Any],
    edges: list[Edge],
    reachable_types: dict[str, set[str]],
    spec: dict | None = None,
) -> list[str]:
    """
    Two sub-checks:

    A) Sentinel-in-requires: a gate is 'protected' if at least one sentinel gate
       appears in its requires (i.e. a sentinel's emitted type is required and
       reachable at this gate).

    B) Direct source→gate: a gate that receives directly from a source:true locus
       (external actor) without an intervening sentinel is a zero-trust violation.
       Both sub-checks produce warnings.
    """
    sentinel_names = {
        name for name, g in gates.items()
        if g.get("kind") in ("sentinel", "regulator")
    }
    sentinel_emits: set[str] = set()
    for sname in sentinel_names:
        sentinel_emits.update(extract_emitted_flows(gates[sname].get("emits", [])))

    warnings = []

    # ── A) Sentinel-in-requires ───────────────────────────────────────────────
    for gname, gspec in gates.items():
        kind = gspec.get("kind", "gate")
        if kind in ("sentinel", "regulator"):
            continue
        requires = set(gspec.get("requires", []))
        # Protected if any required type is emitted by a sentinel
        if sentinel_names and not (requires & sentinel_emits):
            warnings.append(
                f"gate '{gname}': no sentinel/regulator in upstream requires "
                f"— unprotected gate (security topology gap)"
            )

    # ── B) Direct source-locus → non-sentinel gate ────────────────────────────
    if spec:
        loci_spec = spec.get("loci", {})
        source_loci = {
            n for n, ls in loci_spec.items()
            if isinstance(ls, dict) and ls.get("source")
        }
        for e in edges:
            if e.src not in source_loci:
                continue
            if e.dst not in gates:
                continue
            dst_kind = gates[e.dst].get("kind", "gate")
            if dst_kind in ("sentinel", "regulator"):
                continue
            warnings.append(
                f"gate '{e.dst}': receives directly from untrusted source locus "
                f"'{e.src}' with no sentinel — zero-trust violation "
                f"(insert a sentinel between '{e.src}' and '{e.dst}')"
            )

    return warnings


# ── Check 5b: authorization reality ──────────────────────────────────────────
#
# Shift-left of CA falsification #6 (flow_v5, 2026-07-13, class:
# authorization-not-real): all 13 executors required auth_token yet declared
# auth_required:false — the sentinel signs, executors consume the token as a
# timing input, and NOBODY verifies. Forge-on-the-wire tamper: Σ|Δfire%| = 0.
# The static symptom is exact: a gate whose `requires` includes a sig-bearing
# type (any type EMITTED by a sentinel/regulator — derived, never a name
# heuristic) while declaring auth_required:false consumes credentials it does
# not check. That is an ERROR, not a warning: the flow claims a security
# property it cannot have.

def check_auth_reality(gates: dict[str, Any]) -> list[str]:
    """Every consumer of a sentinel-emitted (sig-bearing) type must declare
    auth_required:true. Sentinels/regulators themselves (the issuers) are
    exempt. Returns error strings."""
    sig_types: set[str] = set()
    for g in gates.values():
        if g.get("kind") in ("sentinel", "regulator"):
            sig_types.update(extract_emitted_flows(g.get("emits", [])))
    if not sig_types:
        return []
    errors: list[str] = []
    for gname, gspec in gates.items():
        if gspec.get("kind") in ("sentinel", "regulator"):
            continue
        consumed = sorted(set(gspec.get("requires", [])) & sig_types)
        if consumed and not gspec.get("auth_required", False):
            errors.append(
                f"gate '{gname}': requires sig-bearing type(s) {consumed} "
                f"(sentinel-emitted) but declares auth_required:false — "
                f"credential consumed as timing input, never verified "
                f"(authorization-not-real; CA falsification class #6)"
            )
    return errors


# ── Check 6: silent gates ─────────────────────────────────────────────────────

def check_silent_gates(gates: dict[str, Any], edges: list[Edge]) -> list[str]:
    """Gates that fire but emit nothing downstream."""
    has_outgoing = set(e.src for e in edges)
    warnings = []
    for gname, gspec in gates.items():
        flows = extract_emitted_flows(gspec.get("emits", []))
        if not flows and gname not in has_outgoing:
            warnings.append(
                f"gate '{gname}': fires but emits nothing and has no outgoing synapses "
                f"— signal dead-end (intentional sink or missing wiring?)"
            )
    return warnings


# ── Check 7: window feasibility ───────────────────────────────────────────────

def check_window_feasibility(
    gates: dict[str, Any],
    hop_depth: dict[str, int],
    assumed_min_latency_ms: float = 1.0,
) -> list[str]:
    """
    Warns if a gate's minimum cascade depth × assumed_min_latency_ms > window_ms.
    This is a conservative lower bound — actual latency will be higher.
    """
    warnings = []
    for gname, gspec in gates.items():
        window = gspec.get("window_ms")
        if window is None:
            continue
        hops = hop_depth.get(gname)
        if hops is None:
            continue
        min_cascade_ms = hops * assumed_min_latency_ms
        if min_cascade_ms > window:
            warnings.append(
                f"gate '{gname}': window_ms={window} but min cascade depth is "
                f"{hops} hops × {assumed_min_latency_ms}ms/hop = {min_cascade_ms}ms "
                f"— cascade may time out before coincidence assembles"
            )
    return warnings


# ── Check 8: Cardinality ──────────────────────────────────────────────────────

def check_cardinality(spec: dict) -> tuple[list[str], list[str]]:
    """
    For loci with a `cardinality` declaration:
      - Error:   per_instance and shared sets overlap (contradiction)
      - Error:   referenced locus names must exist in the top-level loci dict
      - Warning: each shared locus is a scaling ceiling — count N ≠ N× throughput
    """
    errors:   list[str] = []
    warnings: list[str] = []
    all_loci = set(spec.get("loci", {}).keys())

    for lname, lspec in spec.get("loci", {}).items():
        if not isinstance(lspec, dict):
            continue
        card = lspec.get("cardinality")
        if not card:
            continue

        count        = card.get("count", 1)
        per_instance = set(card.get("per_instance", []))
        shared       = set(card.get("shared", []))

        overlap = per_instance & shared
        if overlap:
            errors.append(
                f"locus '{lname}': cardinality per_instance and shared overlap: "
                f"{sorted(overlap)} — a locus cannot be both"
            )

        for ref in per_instance | shared:
            if ref not in all_loci:
                errors.append(
                    f"locus '{lname}': cardinality references unknown locus '{ref}'"
                )

        if shared:
            warnings.append(
                f"locus '{lname}' (×{count}): shared loci {sorted(shared)} are scaling "
                f"ceilings — throughput < {count}× single-instance capacity"
            )

    return errors, warnings


# ── Check 9: Topology groups (zoom + slot isolation) ──────────────────────────

def check_topology_groups(spec: dict) -> tuple[list[str], list[str]]:
    """
    For each topology_group:
      - Error:   locus with detail= references a non-existent group
      - Error:   a slot listed in 'slots' is not declared in the group's loci
      - Error:   direct slot→slot synapse (must route through a gate)
      - Warning: a locus reachable from multiple slots is not in shared_loci
    """
    errors:   list[str] = []
    warnings: list[str] = []
    groups = spec.get("topology_groups", {})

    # Validate locus detail= references
    for lname, lspec in spec.get("loci", {}).items():
        if not isinstance(lspec, dict):
            continue
        detail = lspec.get("detail")
        if detail and detail not in groups:
            errors.append(
                f"locus '{lname}': detail='{detail}' references unknown topology_group"
            )

    for gname, group in groups.items():
        slots        = set(group.get("slots", []))
        shared_loci  = set(group.get("shared_loci", []))
        group_loci   = set(group.get("loci", {}).keys())
        group_gates  = set(group.get("gates", {}).keys())
        synapses     = group.get("synapses", [])

        # Slots must be declared in group loci
        for slot in slots:
            if slot not in group_loci:
                errors.append(
                    f"topology_group '{gname}': slot '{slot}' not declared in group loci"
                )

        # No direct slot→slot synapse
        for syn in synapses:
            src = syn.get("from", "")
            dst = syn.get("to", "")
            if src in slots and dst in slots:
                errors.append(
                    f"topology_group '{gname}': direct synapse '{src}' → '{dst}' "
                    f"between slots — transitions must go through a gate"
                )

        # Loci reachable from multiple slots without being declared shared
        slot_reach: dict[str, set[str]] = defaultdict(set)
        for syn in synapses:
            src = syn.get("from", "")
            dst = syn.get("to", "")
            if src in slots:
                slot_reach[dst].add(src)

        for locus, reaching_slots in slot_reach.items():
            if (
                len(reaching_slots) > 1
                and locus not in shared_loci
                and locus not in group_gates
            ):
                warnings.append(
                    f"topology_group '{gname}': '{locus}' is reachable from slots "
                    f"{sorted(reaching_slots)} but not declared in shared_loci "
                    f"— potential pulse interference"
                )

    return errors, warnings


# ── Check 10: Locus type leak ─────────────────────────────────────────────────

def check_locus_type_leak(
    nodes: dict[str, str],
    edges: list[Edge],
    spec: dict | None = None,
) -> list[str]:
    """
    A locus is a pass-through: it can only forward types that arrive on its
    incoming synapses. If a locus emits a type that never arrives on any of its
    incoming synapses, it is fabricating a type — likely a mismodeled transformer
    that should be a gate.

    External actors and sensors (loci with no typed incoming edges) are skipped —
    they legitimately originate types. Warning (not error) because some loci
    intentionally act as both sinks and originators (e.g. a user who receives
    status updates and also submits new requests).
    """
    fwd, rev = adjacency(edges)
    warnings: list[str] = []

    loci_spec = spec.get("loci", {})
    explicit_sources = {
        n for n, ls in loci_spec.items()
        if isinstance(ls, dict) and ls.get("source")
    }

    for name, kind in nodes.items():
        if kind != "locus":
            continue
        # source=true loci legitimately originate types — skip
        if name in explicit_sources:
            continue
        incoming_types = {
            e.pulse_type for e in rev.get(name, [])
            if e.pulse_type and not e.inhibitor
        }
        # No typed incoming edges → pure external source — skip
        if not incoming_types:
            continue
        for e in fwd.get(name, []):
            if e.pulse_type and not e.inhibitor:
                if e.pulse_type not in incoming_types:
                    warnings.append(
                        f"locus '{name}': outgoing pulse_type '{e.pulse_type}' never "
                        f"arrives on any incoming synapse — if this node transforms types, "
                        f"convert it to a gate"
                    )
    return warnings


# ── Check 11: Emit coverage ───────────────────────────────────────────────────

def check_emit_coverage(gates: dict[str, Any], edges: list[Edge]) -> list[str]:
    """
    For gates using the new outcome format, every flow in every outcome bundle
    must have at least one consuming synapse from that gate.

    Old format (list of strings) is skipped — backwards compatible.
    New format: emits = [{"outcome": "ok", "flows": ["TypeA", "TypeB"]}, ...]
    """
    # Build per-gate outgoing typed synapses
    gate_outgoing: dict[str, list[Edge]] = defaultdict(list)
    for e in edges:
        if not e.inhibitor:
            gate_outgoing[e.src].append(e)

    errors: list[str] = []
    for gname, gspec in gates.items():
        emits = gspec.get("emits", [])
        # Only check new outcome format (list of dicts)
        outcome_items = [item for item in emits if isinstance(item, dict)]
        if not outcome_items:
            continue

        outgoing = gate_outgoing.get(gname, [])
        has_untyped = any(e.pulse_type is None for e in outgoing)
        consumed: set[str] = {e.pulse_type for e in outgoing if e.pulse_type}

        for item in outcome_items:
            outcome_name = item.get("outcome", "?")
            for flow in item.get("flows", []):
                if not has_untyped and flow not in consumed:
                    errors.append(
                        f"gate '{gname}' outcome '{outcome_name}': "
                        f"flow '{flow}' has no consuming synapse — silently dropped"
                    )

    return errors


# ── Check 13: Mechanism level ─────────────────────────────────────────────────

def check_mechanism(spec: dict) -> tuple[list[str], list[str]]:
    """
    Gates may declare a `mechanism` block: per-outcome sub-topologies that show
    the conditional downstream flow and push/pull interaction patterns.

    mechanism shape (per gate):
      {
        "<outcome_name>": {
          "description": "...",
          "loci":     { name: {...} },
          "gates":    { name: {...} },
          "synapses": [ {from, to, pulse_type, interaction: "push"|"pull"} ]
        }
      }

    Checks:
      Warning: gate has emits with multiple outcomes but no mechanism declared
      Error:   mechanism references an outcome not in emits
      Warning: mechanism outcome has no synapses (empty sub-topology)
      Warning: pull synapse has no corresponding outbound synapse from the gate
               that carries the query (round-trip incomplete)
    """
    errors:   list[str] = []
    warnings: list[str] = []

    for gname, gspec in spec.get("gates", {}).items():
        emits = gspec.get("emits", [])
        outcome_items = [e for e in emits if isinstance(e, dict)]
        outcome_names = {e.get("outcome") for e in outcome_items if e.get("outcome")}

        mechanism = gspec.get("mechanism")

        # Warn if multiple outcomes but no mechanism
        if len(outcome_names) > 1 and not mechanism:
            warnings.append(
                f"gate '{gname}': {len(outcome_names)} outcomes "
                f"({', '.join(sorted(outcome_names))}) but no mechanism declared "
                f"— conditional downstream topology is implicit"
            )
            continue

        if not mechanism:
            continue

        # Check each mechanism outcome is declared in emits
        for moutcome in mechanism:
            if outcome_names and moutcome not in outcome_names:
                errors.append(
                    f"gate '{gname}': mechanism outcome '{moutcome}' not found in emits "
                    f"— remove or add matching emits entry"
                )

        # Validate each sub-topology
        for moutcome, msub in mechanism.items():
            if not isinstance(msub, dict):
                continue
            msynapses = msub.get("synapses", [])

            if not msynapses and not msub.get("gates") and not msub.get("loci"):
                warnings.append(
                    f"gate '{gname}' mechanism '{moutcome}': empty sub-topology "
                    f"— add loci, gates, and synapses to show conditional flow"
                )
                continue

            # Check pull synapses have a corresponding outbound query synapse
            pull_types = {
                s.get("pulse_type") for s in msynapses
                if s.get("interaction") == "pull" and s.get("pulse_type")
            }
            # For each pull response type, there should be a corresponding
            # synapse FROM this gate in the main spec carrying a query type
            main_outgoing = {
                e.pulse_type for e in
                [Edge(s.get("from",""), s.get("to",""),
                      s.get("pulse_type") if not isinstance(s.get("pulse_types"), list)
                      else None, s.get("inhibitor", False))
                 for s in spec.get("synapses", [])
                 if s.get("from") == gname and not s.get("inhibitor")]
                if e.pulse_type
            }
            for pull_type in pull_types:
                if not main_outgoing:
                    warnings.append(
                        f"gate '{gname}' mechanism '{moutcome}': pull synapse for "
                        f"'{pull_type}' has no outbound query synapse from '{gname}' "
                        f"in main topology — round-trip is incomplete"
                    )

    return errors, warnings


# ── Check 12: Sync gates and consistency boundaries ───────────────────────────

def check_sync_gates(
    spec: dict,
    nodes: dict[str, str],
    edges: list[Edge],
) -> tuple[list[str], list[str], list[str]]:
    """
    kind: "sync" gates are explicit consistency boundaries.

    A sync gate gathers from N upstream sources and fans out a consistent
    snapshot. Its cardinality must be 1 (no cardinality declaration or count=1)
    — otherwise it is N independent local sync points, not one global one.

    Checks:
      Error:   sync gate has cardinality > 1 (per_instance)
      Warning: sync gate has no count declaration — cannot verify it gathers
               from all upstream sources
      Warning: N-cardinality source feeds a non-sync gate directly — eventual
               path without a declared sync point

    Info:    report each sync gate as a consistency boundary (the choke point
             the twin will flag as bottleneck is intentional architecture)
    """
    fwd, rev = adjacency(edges)
    gates_spec = spec.get("gates", {})
    loci_spec  = spec.get("loci",  {})

    sync_gates = {n: g for n, g in gates_spec.items() if g.get("kind") == "sync"}

    errors:   list[str] = []
    warnings: list[str] = []
    info_lines: list[str] = []

    # Cardinality of each locus
    def locus_cardinality(name: str) -> int:
        ls = loci_spec.get(name)
        if not isinstance(ls, dict):
            return 1
        card = ls.get("cardinality")
        if not card:
            return 1
        return int(card.get("count", 1))

    # Check each sync gate
    for gname, gspec in sync_gates.items():
        # Sync gate must have cardinality 1
        ls = loci_spec.get(gname)  # sync gates are gates, not loci — skip locus check
        # (gates don't have cardinality in loci dict; flag if someone puts it there)

        count_decl = gspec.get("count", {})
        requires   = gspec.get("requires", [])
        window_ms  = gspec.get("window_ms")

        # Find upstream sources per required type
        upstream_by_type: dict[str, list[str]] = defaultdict(list)
        for e in rev.get(gname, []):
            if not e.inhibitor and e.pulse_type:
                upstream_by_type[e.pulse_type].append(e.src)

        # Check count vs upstream cardinality
        for req_type in requires:
            srcs = upstream_by_type.get(req_type, [])
            total_upstream = sum(locus_cardinality(s) for s in srcs)
            declared_count = count_decl.get(req_type, 1)

            if total_upstream > 1 and declared_count == 1:
                warnings.append(
                    f"sync gate '{gname}': requires {declared_count}× '{req_type}' "
                    f"but upstream cardinality is {total_upstream} "
                    f"— add count: {{\"{req_type}\": {total_upstream}}} to gather all"
                )
            elif total_upstream > 1 and declared_count == total_upstream:
                info_lines.append(
                    f"sync gate '{gname}': '{req_type}' gathers {declared_count}× "
                    f"(cardinality matches) — strong consistency boundary"
                )
            elif total_upstream == 1:
                info_lines.append(
                    f"sync gate '{gname}': '{req_type}' from cardinality-1 source "
                    f"— consistency boundary (window={window_ms}ms)"
                )

    # Flag N-cardinality sources that reach non-sync gates directly
    for gname, gspec in gates_spec.items():
        if gspec.get("kind") == "sync":
            continue
        for e in rev.get(gname, []):
            if e.inhibitor or not e.pulse_type:
                continue
            card = locus_cardinality(e.src)
            if card > 1:
                # Check if there's a sync gate between this source and this gate
                # (simple: any sync gate in the reverse path)
                visited: set[str] = {gname}
                q: deque[str] = deque([e.src])
                has_sync = False
                while q:
                    n = q.popleft()
                    if n in visited:
                        continue
                    visited.add(n)
                    if nodes.get(n) == "gate" and gates_spec.get(n, {}).get("kind") == "sync":
                        has_sync = True
                        break
                    for re in rev.get(n, []):
                        if re.src not in visited:
                            q.append(re.src)
                if not has_sync:
                    warnings.append(
                        f"gate '{gname}': receives '{e.pulse_type}' from "
                        f"'{e.src}' (cardinality {card}) with no sync gate upstream "
                        f"— eventual consistency; add a sync gate to coordinate"
                    )

    return errors, warnings, info_lines


# ── Check 14a: Persistent loci ───────────────────────────────────────────────

def check_persistent_loci(spec: dict, edges: list[Edge]) -> list[str]:
    """
    Loci that receive state-update pulses (i.e. are written to by gates) but
    lack persistent:true are ephemeral — their state is lost on restart.
    This is a data-loss risk worth flagging as a warning.

    Heuristic: a locus that has incoming synapses FROM gates (not from other loci
    or sources) is likely receiving state updates, not just forwarding pulses.
    """
    warnings: list[str] = []
    loci_spec = spec.get("loci", {})
    gates_spec = spec.get("gates", {})

    # Build set of gate names
    gate_names = set(gates_spec.keys())

    # Find loci that receive pulses from gates
    for e in edges:
        if e.inhibitor or e.src not in gate_names:
            continue
        dst = e.dst
        if dst not in loci_spec:
            continue
        lspec = loci_spec[dst]
        if not isinstance(lspec, dict):
            continue
        if lspec.get("source"):
            continue  # source loci are external actors, not stores
        if not lspec.get("persistent"):
            warnings.append(
                f"locus '{dst}': receives pulses from gate '{e.src}' but has no "
                f"persistent:true — state will be lost on restart; add persistent:true "
                f"if this locus holds durable state"
            )

    return warnings


# ── Check 14: Gate logic operators ───────────────────────────────────────────

def check_gate_logic(spec: dict) -> tuple[list[str], list[str]]:
    """
    Check 14: Gate logic field, optional inputs, outcome weights, circuit breakers.

    Validates:
      logic.op ∈ {AND, OR, FIRST, THRESHOLD}
      FIRST.order ⊆ requires
      THRESHOLD.n: 1 ≤ n ≤ len(requires)
      input_timeout_ms keys ⊆ requires
      optional ∩ requires = ∅
      outcome weight sum ≈ 1.0 (warn if not, using equal weight if omitted)
      kind: "breaker" — must have trips_on; warn if no recovery_ms
    """
    errors:   list[str] = []
    warnings: list[str] = []
    valid_ops = {"AND", "OR", "FIRST", "THRESHOLD"}

    for gname, gspec in spec.get("gates", {}).items():
        requires: list[str] = gspec.get("requires", [])
        optional: list[str] = gspec.get("optional", [])
        kind: str = gspec.get("kind", "gate")

        # ── optional ∩ requires must be empty ─────────────────────────────────
        overlap = set(optional) & set(requires)
        if overlap:
            errors.append(
                f"gate '{gname}': optional types {sorted(overlap)} also appear in requires "
                f"— move to requires (mandatory) or optional, not both"
            )

        # ── input_timeout_ms: scalar (uniform) or dict (per-input) ────────────
        # SYSTEM_PROMPT documents the scalar form (`input_timeout_ms: <int>`);
        # the dict form {input_type: ms} allows per-input overrides. Anything
        # else is a structural error — a verifier must report, never crash
        # (first triggered 2026-07-02 by the amended delivery_router).
        timeout_spec = gspec.get("input_timeout_ms")
        if isinstance(timeout_spec, dict):
            unknown_timeout = set(timeout_spec.keys()) - set(requires)
            if unknown_timeout:
                warnings.append(
                    f"gate '{gname}': input_timeout_ms references types not in requires: "
                    f"{sorted(unknown_timeout)} — these timeouts have no effect"
                )
        elif timeout_spec is not None and not isinstance(timeout_spec, (int, float)):
            errors.append(
                f"gate '{gname}': input_timeout_ms must be an integer (uniform) "
                f"or an object mapping input types to ms — got {type(timeout_spec).__name__}"
            )

        # ── logic field ────────────────────────────────────────────────────────
        logic = gspec.get("logic")
        if logic is not None:
            if isinstance(logic, str):
                op = logic.upper()
                logic_n = 0
                logic_order: list[str] = []
            elif isinstance(logic, dict):
                op = logic.get("op", "AND").upper()
                logic_n = int(logic.get("n", 0))
                logic_order = logic.get("order", [])
            else:
                errors.append(f"gate '{gname}': logic must be a string or object")
                continue

            if op not in valid_ops:
                errors.append(
                    f"gate '{gname}': logic.op '{op}' not valid — "
                    f"must be one of {sorted(valid_ops)}"
                )

            if op == "FIRST" and logic_order:
                unknown_order = set(logic_order) - set(requires)
                if unknown_order:
                    warnings.append(
                        f"gate '{gname}': logic FIRST.order references types not in requires: "
                        f"{sorted(unknown_order)}"
                    )

            if op == "THRESHOLD":
                if logic_n < 1:
                    errors.append(
                        f"gate '{gname}': logic THRESHOLD.n must be ≥ 1, got {logic_n}"
                    )
                elif requires and logic_n > len(requires):
                    errors.append(
                        f"gate '{gname}': logic THRESHOLD.n={logic_n} > len(requires)={len(requires)} "
                        f"— can never be satisfied"
                    )

        # ── outcome weights ────────────────────────────────────────────────────
        emits = gspec.get("emits", [])
        outcome_items = [e for e in emits if isinstance(e, dict) and "outcome" in e]
        if outcome_items and any("weight" in e for e in outcome_items):
            # At least one weight declared — check they sum to ~1.0
            total_weight = sum(float(e.get("weight", 1.0)) for e in outcome_items)
            if abs(total_weight - 1.0) > 0.05:
                warnings.append(
                    f"gate '{gname}': outcome weights sum to {total_weight:.3f} ≠ 1.0 "
                    f"— twin will normalise; consider making them sum to 1.0 explicitly"
                )

        # ── circuit breaker ────────────────────────────────────────────────────
        if kind == "breaker":
            if not gspec.get("trips_on"):
                errors.append(
                    f"gate '{gname}' (kind: breaker): missing trips_on — "
                    f"declare which pulse type triggers failure counting"
                )
            if not gspec.get("recovery_ms"):
                warnings.append(
                    f"gate '{gname}' (kind: breaker): no recovery_ms declared — "
                    f"breaker will never re-close after tripping"
                )

    return errors, warnings


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m tools.opis-eval.eval <spec.json>")
        print("       python -m tools.opis-eval.eval flow.json gates/GateName/v1.json")
        sys.exit(1)

    path = Path(sys.argv[1])
    spec = _normalize_spec_gates(load_spec(path))

    # Compose mode: flow.json + gate file
    if len(sys.argv) >= 3:
        gate_path = Path(sys.argv[2])
        gate_file = load_spec(gate_path)
        gate_name = gate_file.get("gate", gate_path.stem)
        print(c(f"\n  ↳ composing gate: {gate_name} (v{gate_file.get('version', '?')})", CYAN))
        spec = _normalize_spec_gates(compose_flow_gate(spec, gate_file))

    nodes, gates, edges = build_graph(spec)
    fwd, rev = adjacency(edges)
    type_dag = build_type_dag(spec)

    n_loci       = sum(1 for k in nodes.values() if k == "locus")
    n_archetypes = sum(1 for k in nodes.values() if k == "archetype")
    n_gates      = len(gates)
    n_synapses   = len(edges)

    print(c(f"\nopis-eval  ", BOLD) + c(str(path.resolve()), YELLOW))
    print(f"  {n_loci} loci  {n_archetypes} archetypes  "
          f"{n_gates} gates  {n_synapses} synapses")

    all_errors:   list[str] = []
    all_warnings: list[str] = []

    # ── 1. Reachability ───────────────────────────────────────────────────────
    print(hdr("1. Pulse type reachability"))
    errs, warns, reachable_types = check_reachability(nodes, gates, edges, type_dag, spec)
    if errs:
        all_errors.extend(errs)
        for e in errs: print(err(e))
    else:
        print(ok("all gate requires are reachable from upstream sources"))

    # ── 2. Orphans ────────────────────────────────────────────────────────────
    print(hdr("2. Orphan nodes"))
    orphans = check_orphans(nodes, edges)
    if orphans:
        all_warnings.extend(orphans)
        for w in orphans: print(warn(w))
    else:
        print(ok("no orphaned loci or archetypes"))

    # ── 3. Cycles (SCCs) ─────────────────────────────────────────────────────
    print(hdr("3. Cycles (strongly connected components)"))
    sccs = find_sccs(nodes, edges)
    if sccs:
        for scc in sccs:
            print(info(f"cycle: {' ↔ '.join(sorted(scc))}"))
        print(c(f"  {len(sccs)} cycle(s) found — cycles are valid in Opis", CYAN))
    else:
        print(ok("no cycles — purely feed-forward topology"))

    # ── 4. Hop depth ─────────────────────────────────────────────────────────
    print(hdr("4. Hop depth from injection points"))
    hop_depth = check_hop_depth(nodes, gates, edges)
    if hop_depth:
        for gname, d in sorted(hop_depth.items(), key=lambda x: -x[1]):
            bar = "─" * d
            print(info(f"{gname:40s}  {d:2d} hops  {bar}"))
    else:
        print(warn("no gates reachable from injection points"))

    # ── 5. Sentinel coverage ─────────────────────────────────────────────────
    print(hdr("5. Sentinel / regulator coverage"))
    sentinel_names = {n for n, g in gates.items() if g.get("kind") in ("sentinel", "regulator")}
    if not sentinel_names:
        print(info("no sentinels or regulators defined — skipping coverage check"))
    else:
        warns = check_sentinel_coverage(gates, edges, reachable_types, spec)
        if warns:
            all_warnings.extend(warns)
            for w in warns: print(warn(w))
        else:
            print(ok("all non-sentinel gates have upstream sentinel coverage"))

    # ── 5b. Authorization reality ─────────────────────────────────────────────
    print(hdr("5b. Authorization reality (sig-consumers must verify)"))
    auth_errs = check_auth_reality(gates)
    if auth_errs:
        all_errors.extend(auth_errs)
        for e in auth_errs: print(err(e))
    else:
        print(ok("every consumer of a sentinel-emitted type declares auth_required:true"))

    # ── 6. Silent gates ───────────────────────────────────────────────────────
    print(hdr("6. Silent gates (signal dead-ends)"))
    silent = check_silent_gates(gates, edges)
    if silent:
        all_warnings.extend(silent)
        for w in silent: print(warn(w))
    else:
        print(ok("all gates emit at least one pulse type or have outgoing synapses"))

    # ── 7. Window feasibility ─────────────────────────────────────────────────
    print(hdr("7. Window feasibility (cascade timing)"))
    gates_with_windows = [g for g in gates if gates[g].get("window_ms") is not None]
    if not gates_with_windows:
        print(info("no window_ms defined on any gate — skipping timing check"))
    else:
        feas_warns = check_window_feasibility(gates, hop_depth)
        if feas_warns:
            all_warnings.extend(feas_warns)
            for w in feas_warns: print(warn(w))
        else:
            print(ok("all gate windows are reachable within minimum cascade latency"))

    # ── 8. Cardinality ────────────────────────────────────────────────────────
    print(hdr("8. Cardinality (scaling ceilings)"))
    card_loci = [l for l, v in spec.get("loci", {}).items()
                 if isinstance(v, dict) and v.get("cardinality")]
    if not card_loci:
        print(info("no cardinality declarations — skipping"))
    else:
        card_errs, card_warns = check_cardinality(spec)
        if card_errs:
            all_errors.extend(card_errs)
            for e in card_errs: print(err(e))
        if card_warns:
            all_warnings.extend(card_warns)
            for w in card_warns: print(warn(w))
        if not card_errs and not card_warns:
            print(ok("cardinality declarations are consistent"))

    # ── 9. Topology groups ────────────────────────────────────────────────────
    print(hdr("9. Topology groups (zoom levels / slot isolation)"))
    if not spec.get("topology_groups"):
        print(info("no topology_groups defined — skipping"))
    else:
        tg_errs, tg_warns = check_topology_groups(spec)
        if tg_errs:
            all_errors.extend(tg_errs)
            for e in tg_errs: print(err(e))
        if tg_warns:
            all_warnings.extend(tg_warns)
            for w in tg_warns: print(warn(w))
        if not tg_errs and not tg_warns:
            print(ok("all topology groups are internally consistent"))

    # ── 10. Locus type leak ───────────────────────────────────────────────────
    print(hdr("10. Locus type leak (pass-through violations)"))
    leak_warns = check_locus_type_leak(nodes, edges, spec)
    if leak_warns:
        all_warnings.extend(leak_warns)
        for w in leak_warns: print(warn(w))
    else:
        print(ok("all loci only forward types that arrive on incoming synapses"))

    # ── 11. Emit coverage ─────────────────────────────────────────────────────
    print(hdr("11. Emit coverage (outcome flows reachable downstream)"))
    outcome_gates = [
        g for g, spec_ in gates.items()
        if any(isinstance(item, dict) for item in spec_.get("emits", []))
    ]
    if not outcome_gates:
        print(info("no outcome-format emits defined — skipping"))
    else:
        emit_errs = check_emit_coverage(gates, edges)
        if emit_errs:
            all_errors.extend(emit_errs)
            for e in emit_errs: print(err(e))
        else:
            print(ok("all outcome flows have consuming synapses"))

    # ── 12. Sync gates (consistency boundaries) ───────────────────────────────
    print(hdr("12. Sync gates (consistency boundaries)"))
    sync_gate_names = [n for n, g in gates.items() if g.get("kind") == "sync"]
    multi_card_loci = [l for l, ls in spec.get("loci", {}).items()
                       if isinstance(ls, dict) and isinstance(ls.get("cardinality"), dict)
                       and ls["cardinality"].get("count", 1) > 1]
    if not sync_gate_names and not multi_card_loci:
        print(info("no sync gates or multi-cardinality loci — skipping"))
    else:
        sync_errs, sync_warns, sync_info = check_sync_gates(spec, nodes, edges)
        for line in sync_info:  print(info(line))
        if sync_errs:
            all_errors.extend(sync_errs)
            for e in sync_errs:   print(err(e))
        if sync_warns:
            all_warnings.extend(sync_warns)
            for w in sync_warns:  print(warn(w))
        if not sync_errs and not sync_warns:
            print(ok("sync gates correctly coordinate upstream cardinality"))

    # ── 13. Gate internals ────────────────────────────────────────────────────
    print(hdr("13. Gate internals (conditional sub-topologies)"))
    multi_outcome_gates = [
        g for g, gs in gates.items()
        if sum(1 for e in gs.get("emits", []) if isinstance(e, dict) and e.get("outcome")) > 1
    ]
    gates_with_mechanism = [g for g, gs in gates.items() if gs.get("mechanism")]
    if not multi_outcome_gates and not gates_with_mechanism:
        print(info("no multi-outcome gates or mechanism declarations — skipping"))
    else:
        mech_errs, mech_warns = check_mechanism(spec)
        if mech_errs:
            all_errors.extend(mech_errs)
            for e in mech_errs: print(err(e))
        if mech_warns:
            all_warnings.extend(mech_warns)
            for w in mech_warns: print(warn(w))
        if not mech_errs and not mech_warns:
            print(ok("mechanism sub-topologies are consistent with emits"))
        else:
            # Report which gates have mechanism declared
            for g in gates_with_mechanism:
                outcomes = list(gates[g].get("mechanism", {}).keys())
                print(info(f"gate '{g}': mechanism declared for {outcomes}"))

    # ── 14a. Persistent loci (durability) ────────────────────────────────────
    print(hdr("14a. Persistent loci (state durability)"))
    persistent_warns = check_persistent_loci(spec, edges)
    if persistent_warns:
        all_warnings.extend(persistent_warns)
        for w in persistent_warns: print(warn(w))
    else:
        print(ok("all gate-written loci declare persistent:true or are source loci"))

    # ── 14. Gate logic operators ──────────────────────────────────────────────
    print(hdr("14. Gate logic operators (AND/OR/FIRST/THRESHOLD/breaker)"))
    logic_gates = [g for g, gs in gates.items() if gs.get("logic") or gs.get("optional")
                   or gs.get("kind") == "breaker" or gs.get("input_timeout_ms")]
    if not logic_gates:
        print(info("no logic / optional / breaker declarations — skipping"))
    else:
        logic_errs, logic_warns = check_gate_logic(spec)
        if logic_errs:
            all_errors.extend(logic_errs)
            for e in logic_errs: print(err(e))
        if logic_warns:
            all_warnings.extend(logic_warns)
            for w in logic_warns: print(warn(w))
        if not logic_errs and not logic_warns:
            print(ok("gate logic declarations are consistent"))
        for g in logic_gates:
            gsp = gates[g]
            parts = []
            if gsp.get("logic"):
                logic_val = gsp["logic"]
                op = logic_val.get("op") if isinstance(logic_val, dict) else logic_val
                parts.append(f"logic={op}")
            if gsp.get("optional"):
                parts.append(f"optional={gsp['optional']}")
            if gsp.get("kind") == "breaker":
                parts.append(f"breaker trips_on={gsp.get('trips_on')}")
            print(info(f"gate '{g}': {', '.join(parts)}"))

    # ── Summary ───────────────────────────────────────────────────────────────
    # Exit codes: 0 = clean, 1 = errors (structural failure), 2 = warnings only.
    print()
    if not all_errors and not all_warnings:
        print(c("✓ Clean", GREEN))
        sys.exit(0)
    else:
        if all_errors:
            print(c(f"✗ {len(all_errors)} error(s)", RED))
        if all_warnings:
            print(c(f"⚠ {len(all_warnings)} warning(s)", YELLOW))
        sys.exit(1 if all_errors else 2)


if __name__ == "__main__":
    main()
