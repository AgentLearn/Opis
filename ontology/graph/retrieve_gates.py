#!/usr/bin/env python3
"""
Step 1 as OG-RAG hypergraph retrieval (Sharma et al. 2024, arXiv:2412.15235).

A gate = a hyperedge over terms (consumes ∪ emits). Given a kata's typed DSL terms,
retrieve a minimal set of gate-hyperedges covering them, EXPANDING iteratively: each
selected gate emits new terms, which surface more selectable gates — repeat to closure.
Terms still uncovered at closure = the "gate-needed" signal FA raises via ADR.

This is the same forward fixpoint proof.py computes for reachability — here used as
retrieval/selection rather than verification.

Store: reads `../gate_hypergraph.json` (JSON is the canonical store).

Run:  python retrieve_gates.py                     # silicon demo
      python retrieve_gates.py --seed a,b --goal c,d
"""
import json, sys
from pathlib import Path

HG = Path(__file__).resolve().parent.parent / "gate_hypergraph.json"

# demo term sets (until step-0 term typing derives these from a kata automatically)
DEMOS = {
    "silicon": {
        "seed": ["order","payment","auth_request","menu_update","location",
                 "query","query_response","event"],
        "goal": ["accepted_order","command","notification","reward","estimate",
                 "routing_decision","tracking_update"],
    },
}

def ancestors(term, terms):
    """subtype chain: accepted_order -> order. So `order` input is satisfied by
    `accepted_order` (a subtype). Returns the set incl. the term itself."""
    out, cur = set(), term
    while cur:
        out.add(cur); cur = terms.get(cur)
    return out

def satisfied(inp, available, terms):
    # an input slot `inp` is met if any available term equals it or is a subtype of it
    return any(inp in ancestors(a, terms) for a in available)

def cover(seed, goal, hg):
    terms, gates = hg["terms"], hg["gates"]
    available = set(seed)
    selected, order = [], 0
    changed = True
    while changed:                                  # "repeat if more terms surface"
        changed = False
        for g in gates:
            if g["gate"] in {s["gate"] for s in selected}: continue
            if all(satisfied(i, available, terms) for i in g["consumes"]):
                order += 1
                selected.append({**g, "step": order,
                                 "new": [t for t in g["emits"] if t not in available]})
                available |= set(g["emits"])
                changed = True
    reached = {t for t in goal if satisfied(t, available, terms)}
    missing = [t for t in goal if t not in reached]
    return selected, available, reached, missing

def main():
    hg = json.loads(HG.read_text())
    seed, goal = DEMOS["silicon"]["seed"], DEMOS["silicon"]["goal"]
    label = "silicon (demo)"
    if "--seed" in sys.argv:
        seed = sys.argv[sys.argv.index("--seed")+1].split(","); label = "custom"
    if "--goal" in sys.argv:
        goal = sys.argv[sys.argv.index("--goal")+1].split(",")

    selected, closure, reached, missing = cover(seed, goal, hg)
    print(f"# OG-RAG gate retrieval — {label}")
    print(f"seed terms ({len(seed)}): {', '.join(seed)}")
    print(f"goal terms ({len(goal)}): {', '.join(goal)}\n")
    print(f"retrieved {len(selected)} gate-hyperedges (in expansion order):")
    for g in selected:
        new = f"  +new: {', '.join(g['new'])}" if g["new"] else ""
        print(f"  {g['step']}. {g['gate']} [{g['kind']}]  "
              f"consumes({', '.join(g['consumes'])}) → emits({', '.join(g['emits'])}){new}")
    print(f"\nterm closure: {len(closure)} terms")
    print(f"goals reached: {', '.join(sorted(reached)) or '—'}")
    if missing:
        print(f"\n⚠ goals NOT covered (→ gate-needed / ADR): {', '.join(missing)}")
    else:
        print("\n✓ all goals covered by the retrieved gate set")

if __name__ == "__main__":
    main()
