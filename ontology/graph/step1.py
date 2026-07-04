#!/usr/bin/env python3
"""
Step 1 of the Opis GraphRAG pipeline, as Cypher over the embedded Kùzu graph.

Given a kata behaviour (its DSL terms already typed, step 0), retrieve the relevant
SUBSET of the SA-taxonomy (logic / template / kind) and the candidate gates that
realize it. The retrieval is ONE Cypher query per behaviour — the graph + the
lexical trigger vocabulary both live in the DB (see build_graph.py), so this file
is just: read behaviour -> run query -> print. Swap Kùzu for any Cypher/GQL store
and the query is unchanged.

Run:  python step1.py ../../agents/katas/silicon_sandwiches.md
      python step1.py            # defaults to silicon
"""
import os, sys, kuzu
from pathlib import Path

HERE = Path(__file__).resolve().parent
DBDIR = Path(os.environ.get("OPIS_KUZU_DIR", HERE / "opis_kuzu"))
DEFAULT_KATA = HERE.parent.parent / "agents/katas/silicon_sandwiches.md"

# The retrieval query: match vocab concepts whose stored trigger stems occur in the
# behaviour text, group by axis, and expand to the gates that realize them.
RETRIEVE = """
MATCH (c:Concept)
WHERE c.ntype IN ['GateLogic','GateTemplate','GateComputeTemplate','GateKind']
UNWIND c.triggers AS trig
WITH c, trig WHERE $b CONTAINS trig
WITH DISTINCT c
OPTIONAL MATCH (c)-[:ON_AXIS]->(a:Concept)
OPTIONAL MATCH (c)-[:REALIZED_BY]->(g:Gate)
RETURN a.label AS axis, c.label AS concept, collect(DISTINCT g.name) AS gates
ORDER BY axis, concept
"""

def behaviours(path):
    return [l.strip("- ").strip() for l in Path(path).read_text().splitlines()
            if l.strip().startswith("-")]

def main():
    kata = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_KATA
    conn = kuzu.Connection(kuzu.Database(str(DBDIR)))
    print(f"# Step-1 retrieval (Cypher/Kùzu) for {kata.name}\n")
    for b in behaviours(kata):
        res = conn.execute(RETRIEVE, {"b": b.lower()})
        by_axis, gates = {}, []
        while res.has_next():
            axis, concept, gs = res.get_next()
            by_axis.setdefault(axis or "?", []).append(concept)
            gates += [x for x in (gs or []) if x]
        print("•", b[:80])
        if by_axis:
            for axis in ("logic","template_movement","template_computation","kind"):
                if axis in by_axis:
                    print(f"    {axis}: {', '.join(sorted(set(by_axis[axis])))}")
            if gates:
                seen=set(); uniq=[g for g in gates if not (g in seen or seen.add(g))]
                print(f"    → candidate gates: {', '.join(uniq)}")
        else:
            print("    (no taxonomy subset matched)")
        print()

if __name__ == "__main__":
    main()
