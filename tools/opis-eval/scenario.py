#!/usr/bin/env python3
"""
opis-scenario — user-story (scenario) verifier, v1 static leg.

Design closed 2026-07-13 (strategy.md). A scenario is EXACTLY three parts —
anything else is inexpressible by grammar (the anti-spaghetti rule):

  setup    — ONE shared-state predicate (uninterpreted string in v1; the
             harness/contention leg gives it meaning via the ADR-005 sim
             adapter)
  stimuli  — an UNORDERED MULTISET of initiating pulses:
             [{"source": <locus>, "type": <pulse_type>, "count": N}, ...]
             Unordered is load-bearing: concurrency is the default, ordering
             is not expressible. If order matters, that is two scenarios
             with different setups.
  claim    — cardinalities over TERMINAL outcome types:
             [{"outcome": <type>, "cardinality": {"exactly"|"at_least"|
               "at_most"|"none": N}}, ...]
             Claims are actor-anonymous PERMANENTLY (tie-break policy is a
             domain decision → lives in the kata → FA derives gates).

Axioms (always in force, never opt-in):
  1. CLOSURE — every success-reachable terminal type must appear in the
     claim; a reachable type the claim is silent about is a violation
     (silent third outcomes are CA falsification class #1).
  2. PRESUMED FALLIBILITY — every stimulus can fail; failure-side terminals
     (see below) are always acceptable and never need claiming. The expert
     is only ever asked the success-side shape.
  3. ACTOR-ANONYMOUS — claims count outcome types, never who-gets-what.

v1 static semantics:
  - terminal: a (locus, type) delivery where the receiving locus has no
    outgoing synapse carrying that type further — the pulse is ABSORBED.
    Derivational; no locus markers needed. The claim is over types.
  - failure-side (KNOWN v1 WART, one name anchor): an emit bundle is
    failure-side iff its outcome name is "failed" OR all its flows are
    loud_failure_event / its subtypes. This is the same REQ-35 convention
    the CA codegen doctrine keys on. Fix path (agenda): explicit
    `failure: true` on emit bundles, FA-side.
  - reachability walk is per-stimulus and gate-participation requires the
    gate's OTHER inputs to be ambient-reachable (eval.py's fixpoint), so a
    stimulus cannot conjure inputs the flow never provides.
  - cardinalities: form-checked; "none" is statically verified (the type
    must NOT be success-reachable); counting claims defer to the harness
    leg and are reported as such.

Confirmed scenarios carry pins (kata hash + flow hash at confirmation) and
are kata-keyed regress fixtures that SURVIVE flow rebuilds: regress
re-verifies them against the CURRENT canonical flow; the pin is provenance,
not a freeze.

Usage:
  python tools/opis-eval/scenario.py verify <scenario.json> <flow.json>
  python tools/opis-eval/scenario.py generate <flow.json> [--out <dir>]
  python tools/opis-eval/scenario.py confirm <scenario.json> <flow.json> --kata <kata.md>

Exit codes: 0 verified / generated; 1 disproof (unreachable claim, closure
violation, or violated "none"); 2 malformed scenario.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


eval_mod = sys.modules.get("opis_eval") or _load("opis_eval", HERE / "eval.py")

LOUD_FAILURE_BASE = "loud_failure_event"
FAILURE_OUTCOME = "failed"


# ── flow model ────────────────────────────────────────────────────────────────

class Flow:
    def __init__(self, spec: dict):
        self.spec = spec
        self.nodes, self.gates, self.edges = eval_mod.build_graph(spec)
        self.type_dag = eval_mod.build_type_dag(spec)  # {type: descendants}
        self.fwd, self.rev = eval_mod.adjacency(self.edges)
        _, _, self.ambient = eval_mod.check_reachability(
            self.nodes, self.gates, self.edges, self.type_dag, spec)

    def satisfies(self, required: str, offered: str) -> bool:
        """offered IS-A required (subtype-aware, same rule as eval)."""
        return offered == required or offered in self.type_dag.get(required, set())

    def sig_types(self) -> set[str]:
        """Sentinel/regulator-emitted (credential) types — same derivation as
        eval check 5b. Credentials ENABLE gates; they do not CAUSE outcomes:
        the causal walk never crosses a gate via a credential input, so
        'request a token' does not become the story of every authorized
        action in the flow."""
        out: set[str] = set()
        for g in self.gates.values():
            if g.get("kind") in ("sentinel", "regulator"):
                out.update(eval_mod.extract_emitted_flows(g.get("emits", [])))
        return out

    def failure_types(self) -> set[str]:
        """Types carried by failure-side emit bundles (see module docstring)."""
        loud = {LOUD_FAILURE_BASE} | self.type_dag.get(LOUD_FAILURE_BASE, set())
        out: set[str] = set()
        for g in self.gates.values():
            for e in g.get("emits", []):
                flows = set(e.get("flows", [])) if isinstance(e, dict) else {e}
                name = e.get("outcome") if isinstance(e, dict) else None
                if name == FAILURE_OUTCOME or (flows and flows <= loud):
                    out |= flows
        return out

    def gate_participates(self, gname: str, via_type: str) -> bool:
        """A gate joins a stimulus chain if every OTHER required input is
        ambient-reachable — the stimulus cannot conjure missing inputs."""
        g = self.gates[gname]
        arrived = self.ambient.get(gname, set())
        for req in g.get("requires", []):
            if self.satisfies(req, via_type):
                continue
            if not any(self.satisfies(req, t) for t in arrived):
                return False
        return True


# ── the walk ──────────────────────────────────────────────────────────────────

def trace(flow: Flow, source: str, stim_type: str):
    """BFS from one stimulus. Returns (terminals, failure_only_terminals)
    as {type: sorted list of absorbing loci}. A terminal is failure-only if
    every path to it passes through a failure-side emit bundle."""
    if source not in flow.nodes:
        raise ValueError(f"stimulus source '{source}' is not a locus in this flow")
    fail_types = flow.failure_types()
    sig_types = flow.sig_types()
    # state: (node, type, tainted) — tainted = reached via failure-side emit
    seen: set[tuple[str, str, bool]] = set()
    frontier: list[tuple[str, str, bool]] = []
    terminals: dict[tuple[str, bool], set[str]] = {}

    def push(node: str, ptype: str, taint: bool):
        key = (node, ptype, taint)
        if key not in seen:
            seen.add(key)
            frontier.append(key)

    emitted_from_source = False
    for e in flow.fwd.get(source, []):
        if e.pulse_type == stim_type or flow.satisfies(stim_type, e.pulse_type):
            push(e.dst, e.pulse_type, False)
            emitted_from_source = True
    if not emitted_from_source:
        raise ValueError(
            f"stimulus ('{source}', '{stim_type}') has no outgoing synapse — "
            f"the flow never carries this pulse from this locus")

    while frontier:
        node, ptype, taint = frontier.pop()
        if node in flow.gates:
            if ptype in sig_types:
                continue  # credential delivery: enables, never causes
            if not flow.gate_participates(node, ptype):
                continue
            for em in flow.gates[node].get("emits", []):
                flows = em.get("flows", []) if isinstance(em, dict) else [em]
                name = em.get("outcome") if isinstance(em, dict) else None
                em_fail = (name == FAILURE_OUTCOME
                           or (flows and set(flows) <= fail_types))
                for out_t in flows:
                    delivered = False
                    for e in flow.fwd.get(node, []):
                        if e.pulse_type == out_t or flow.satisfies(out_t, e.pulse_type):
                            push(e.dst, out_t, taint or em_fail)
                            delivered = True
                    if not delivered:
                        terminals.setdefault((out_t, taint or em_fail),
                                             set()).add(node)
        else:
            forwarded = False
            for e in flow.fwd.get(node, []):
                if e.pulse_type == ptype:
                    push(e.dst, ptype, taint)
                    forwarded = True
            if not forwarded:
                terminals.setdefault((ptype, taint), set()).add(node)

    succ: dict[str, list[str]] = {}
    fail_only: dict[str, list[str]] = {}
    types = {t for (t, _) in terminals}
    for t in sorted(types):
        clean = terminals.get((t, False))
        tainted = terminals.get((t, True))
        if clean:
            succ[t] = sorted(clean | (tainted or set()))
        else:
            fail_only[t] = sorted(tainted or set())
    return succ, fail_only


# ── scenario schema ───────────────────────────────────────────────────────────

CARD_KEYS = ("exactly", "at_least", "at_most", "none")


def validate_scenario(sc: dict) -> list[str]:
    errs = []
    if not isinstance(sc.get("name"), str) or not sc.get("name"):
        errs.append("scenario needs a non-empty 'name'")
    setup = sc.get("setup")
    if not isinstance(setup, dict) or not isinstance(setup.get("predicate"), str):
        errs.append("'setup' must be {'predicate': <one shared-state predicate string>}")
    elif len([k for k in setup if k != "note"]) != 1:
        errs.append("'setup' carries exactly ONE predicate (plus optional 'note') — "
                    "more state = a different scenario")
    stimuli = sc.get("stimuli")
    if not isinstance(stimuli, list) or not stimuli:
        errs.append("'stimuli' must be a non-empty list (unordered multiset)")
    else:
        for s in stimuli:
            if not (isinstance(s, dict) and isinstance(s.get("source"), str)
                    and isinstance(s.get("type"), str)
                    and isinstance(s.get("count", 1), int) and s.get("count", 1) >= 1):
                errs.append(f"malformed stimulus: {s!r} — needs source, type, count>=1")
    claim = sc.get("claim")
    if not isinstance(claim, list) or not claim:
        errs.append("'claim' must be a non-empty list of outcome cardinalities")
    else:
        for cl in claim:
            card = cl.get("cardinality") if isinstance(cl, dict) else None
            if not (isinstance(cl, dict) and isinstance(cl.get("outcome"), str)
                    and isinstance(card, dict) and len(card) == 1
                    and next(iter(card)) in CARD_KEYS
                    and isinstance(next(iter(card.values())), int)):
                errs.append(f"malformed claim entry: {cl!r} — needs outcome + one of "
                            f"{CARD_KEYS} with an int")
    forbidden = set(sc) - {"name", "kata", "words", "setup", "stimuli", "claim",
                           "confirmed"}
    if forbidden:
        errs.append(f"inexpressible keys {sorted(forbidden)} — scenarios have no "
                    f"middles, no ordering, no actor bindings (by grammar)")
    return errs


# ── verify ────────────────────────────────────────────────────────────────────

def verify(sc: dict, flow: Flow) -> tuple[list[str], list[str]]:
    """Returns (disproofs, notes)."""
    disproofs: list[str] = []
    notes: list[str] = []
    succ_all: dict[str, list[str]] = {}
    fail_all: dict[str, list[str]] = {}
    for s in sc["stimuli"]:
        try:
            succ, fail = trace(flow, s["source"], s["type"])
        except ValueError as e:
            disproofs.append(str(e))
            continue
        for t, loci in succ.items():
            succ_all.setdefault(t, sorted(set(succ_all.get(t, [])) | set(loci)))
        for t, loci in fail_all.items():
            pass
        for t, loci in fail.items():
            fail_all.setdefault(t, sorted(set(fail_all.get(t, [])) | set(loci)))
    if disproofs:
        return disproofs, notes

    claimed = {cl["outcome"]: next(iter(cl["cardinality"].items()))
               for cl in sc["claim"]}

    for t, (kind, n) in claimed.items():
        if kind == "none" or (kind in ("exactly", "at_most") and n == 0):
            if t in succ_all:
                disproofs.append(
                    f"claim says NO '{t}', but it is success-reachable "
                    f"(absorbed at {succ_all[t]})")
            continue
        if t in succ_all:
            continue
        if t in fail_all:
            notes.append(f"claimed outcome '{t}' is reachable only via "
                         f"failure-side emits — axiom 2 already covers it; "
                         f"claiming it is redundant but not wrong")
        else:
            disproofs.append(
                f"claimed outcome '{t}' is NOT reachable from any stimulus — "
                f"the flow cannot deliver this story")

    positive = {t for t, (k, n) in claimed.items()
                if not (k == "none" or (k in ("exactly", "at_most") and n == 0))}
    unclaimed = [t for t in succ_all if t not in positive]
    if unclaimed:
        for t in unclaimed:
            disproofs.append(
                f"CLOSURE: '{t}' is success-reachable (absorbed at "
                f"{succ_all[t]}) but the claim is silent about it — silent "
                f"outcomes are forbidden (axiom 1); claim it or amend the flow")

    if fail_all:
        notes.append(f"failure-side terminals (axiom 2, always acceptable): "
                     f"{sorted(fail_all)}")
    counting = [t for t, (k, n) in claimed.items()
                if t in succ_all and not (k == "none" or n == 0)]
    if counting:
        notes.append(f"cardinalities on {sorted(counting)} are form-checked "
                     f"only — counting is the harness/contention leg (ADR-005 "
                     f"sim adapter), not the static leg")
    return disproofs, notes


# ── generate (machine enumerates, expert selects) ─────────────────────────────

def generate(flow: Flow, faces: list[str] | None = None) -> list[dict]:
    """One candidate scenario per (face locus, outgoing pulse type). The
    machine enumerates what CAN happen; only a domain expert can say what
    SHOULD (confirm/reject on the expert face). Candidates carry the full
    success-terminal set as an exactly-1 claim each — the expert edits."""
    out = []
    if faces:
        sources = faces
    else:
        # Derivational: actor faces = loci named as requirement origins
        # (origin pins are exactly "which face drives this" — proof.py).
        sources = sorted({r.get("origin") for r in flow.spec.get("requirements", [])
                          if isinstance(r, dict) and r.get("origin")})
        if not sources:  # legacy flow without origins: any source locus
            sources = [n for n, l in flow.spec.get("loci", {}).items()
                       if isinstance(l, dict) and l.get("source")]
    seen_stims = set()
    for src in sorted(set(sources)):
        for e in flow.fwd.get(src, []):
            if (src, e.pulse_type) in seen_stims:
                continue
            seen_stims.add((src, e.pulse_type))
            try:
                succ, fail = trace(flow, src, e.pulse_type)
            except ValueError:
                continue
            if not succ:
                continue
            claim = [{"outcome": t, "cardinality": {"exactly": 1}}
                     for t in sorted(succ)]
            words = (f"When {src} sends {e.pulse_type}, "
                     f"{' and '.join(sorted(succ))} happen"
                     f"{'s' if len(succ) == 1 else ''}"
                     f" (or it fails loudly: {', '.join(sorted(fail)) or '—'}).")
            out.append({
                "name": f"{src}_{e.pulse_type}",
                "kata": flow.spec.get("name", "?"),
                "words": words,
                "setup": {"predicate": "true",
                          "note": "autogenerated — expert must set the real "
                                  "shared-state predicate"},
                "stimuli": [{"source": src, "type": e.pulse_type, "count": 1}],
                "claim": claim,
            })
    return out


# ── confirm (pin) ─────────────────────────────────────────────────────────────

def sha256_file(p: Path) -> str:
    return "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()


def confirm(sc: dict, flow_path: Path, kata_path: Path) -> dict:
    sc = dict(sc)
    sc["confirmed"] = {
        "kata": {"file": str(kata_path.relative_to(REPO_ROOT))
                 if kata_path.is_relative_to(REPO_ROOT) else str(kata_path),
                 "hash": sha256_file(kata_path)},
        "flow_at_confirmation": {"file": flow_path.name,
                                 "hash": sha256_file(flow_path)},
        "confirmed_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return sc


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="user-story scenario verifier (v1 static leg)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify")
    v.add_argument("scenario"); v.add_argument("flow")
    g = sub.add_parser("generate")
    g.add_argument("flow"); g.add_argument("--out"); g.add_argument("--face", action="append")
    c = sub.add_parser("confirm")
    c.add_argument("scenario"); c.add_argument("flow")
    c.add_argument("--kata", required=True)
    args = ap.parse_args()

    flow_path = Path(args.flow).resolve()
    flow = Flow(json.loads(flow_path.read_text()))

    if args.cmd == "generate":
        cands = generate(flow, args.face)
        if args.out:
            outdir = Path(args.out); outdir.mkdir(parents=True, exist_ok=True)
            for sc in cands:
                (outdir / f"{sc['name']}.json").write_text(json.dumps(sc, indent=1))
            print(f"{len(cands)} candidate scenario(s) → {outdir}")
        else:
            for sc in cands:
                print(f"  · {sc['words']}")
            print(f"{len(cands)} candidate(s) — an expert selects; a candidate "
                  f"is a question, not a fact")
        return 0

    sc_path = Path(args.scenario).resolve()
    sc = json.loads(sc_path.read_text())
    errs = validate_scenario(sc)
    if errs:
        for e in errs:
            print(f"  ✗ {e}")
        return 2

    if args.cmd == "confirm":
        disproofs, notes = verify(sc, flow)
        for n in notes:
            print(f"  · {n}")
        if disproofs:
            for d in disproofs:
                print(f"  ✗ {d}")
            print("REFUSED: a scenario that fails verification cannot be confirmed")
            return 1
        pinned = confirm(sc, flow_path, Path(args.kata).resolve())
        sc_path.write_text(json.dumps(pinned, indent=1))
        print(f"  ✓ confirmed + pinned (kata hash, flow hash) → {sc_path.name}")
        return 0

    disproofs, notes = verify(sc, flow)
    for n in notes:
        print(f"  · {n}")
    if disproofs:
        for d in disproofs:
            print(f"  ✗ {d}")
        print(f"✗ scenario '{sc['name']}' DISPROVED against {flow_path.name}")
        return 1
    print(f"  ✓ scenario '{sc['name']}' holds against {flow_path.name} "
          f"(static leg: reachability + closure + none-claims)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
