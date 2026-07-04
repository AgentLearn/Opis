#!/usr/bin/env python3
"""
Step 1 of the Opis GraphRAG pipeline, over the embedded Kùzu graph.

Given a kata behaviour (DSL terms already typed, step 0), retrieve:
  1. the relevant SA-taxonomy SUBSET (logic / template / kind), via stored triggers;
  2. candidate gates RANKED BY PRECEDENT — how many of the 11 katas' mapped
     behaviours that used the same axis-values were realized by each gate;
  3. the nearest precedent behaviours themselves (context for FA / generation).

(1) is lexical over the taxonomy; (2)+(3) are graph retrieval over the precedent
corpus (mappings.jsonl loaded by build_graph.py). Everything is Cypher — swap Kùzu
for any Cypher/GQL store and the queries are unchanged.

Run:  python step1.py [../../agents/katas/<kata>.md]
"""
import os, sys, kuzu
from pathlib import Path

HERE = Path(__file__).resolve().parent
DBDIR = Path(os.environ.get("OPIS_KUZU_DIR", HERE / "opis_kuzu"))
DEFAULT_KATA = HERE.parent.parent / "agents/katas/silicon_sandwiches.md"

# (1) taxonomy subset: vocab concepts whose stored trigger stems occur in the behaviour
SUBSET = """
MATCH (c:Concept)
WHERE c.ntype IN ['GateLogic','GateTemplate','GateComputeTemplate','GateKind']
UNWIND c.triggers AS trig
WITH c, trig WHERE $b CONTAINS trig
WITH DISTINCT c
OPTIONAL MATCH (c)-[:ON_AXIS]->(a:Concept)
RETURN c.id AS id, a.label AS axis, c.label AS concept
ORDER BY axis, concept
"""
# (2) candidate gates ranked by precedent: behaviours using the seed concepts,
#     grouped by the gate that realized them.
GATES = """
MATCH (c:Concept)<-[:USES]-(b:Behaviour)-[:REALIZES_GATE]->(g:Gate)
WHERE c.id IN $ids
RETURN g.name AS gate, count(DISTINCT b) AS freq, collect(DISTINCT b.kata) AS katas
ORDER BY freq DESC
"""
# (3) nearest precedent behaviours: most axis-value overlap with the query.
PRECEDENTS = """
MATCH (c:Concept)<-[:USES]-(b:Behaviour)
WHERE c.id IN $ids
RETURN b.kata AS kata, b.text AS text, count(DISTINCT c) AS overlap
ORDER BY overlap DESC LIMIT 3
"""

def behaviours(path):
    return [l.strip("- ").strip() for l in Path(path).read_text().splitlines()
            if l.strip().startswith("-")]

def rows(res):
    out = []
    while res.has_next(): out.append(res.get_next())
    return out

def main():
    kata = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_KATA
    conn = kuzu.Connection(kuzu.Database(str(DBDIR)))
    print(f"# Step-1 retrieval (Cypher/Kùzu, precedent-ranked) for {kata.name}\n")
    for b in behaviours(kata):
        sub = rows(conn.execute(SUBSET, {"b": " " + b.lower()}))  # leading space => word-start match
        ids = [r[0] for r in sub]
        by_axis = {}
        for _id, axis, concept in sub:
            by_axis.setdefault(axis or "?", set()).add(concept)
        print("•", b[:82])
        for axis in ("logic","template_movement","template_computation","kind"):
            if axis in by_axis:
                print(f"    {axis}: {', '.join(sorted(by_axis[axis]))}")
        if ids:
            gates = rows(conn.execute(GATES, {"ids": ids}))
            if gates:
                g = "; ".join(f"{name}×{freq}" for name, freq, _k in gates[:5])
                print(f"    → gates by precedent: {g}")
            prec = rows(conn.execute(PRECEDENTS, {"ids": ids}))
            prec = [(k,t,o) for k,t,o in prec if t.lower() != b.lower()][:2]
            if prec:
                print("    ~ precedents: " +
                      " | ".join(f"[{k}] {t[:40]}" for k,t,o in prec))
        if not by_axis:
            print("    (no taxonomy subset matched)")
        print()

if __name__ == "__main__":
    main()
