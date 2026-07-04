#!/usr/bin/env python3
"""
Build the Opis GATE HYPERGRAPH — the retrieval spine for FA (OG-RAG style).

A gate is a HYPEREDGE over terms: it connects the slot types it CONSUMES and EMITS
into one cluster (exactly OG-RAG's hyperedge = a cluster of grounded facts). Retrieval
(retrieve_gates.py) selects a minimal set of these hyperedges covering a kata's terms,
expanding iteratively as selected gates emit new terms.

Storage: the canonical store is JSON (`gate_hypergraph.json`) — committable source, no
binary blob (per Zarko: "DB could be stored as json"). It is also loaded into an embedded
Kùzu graph so the per-step candidate lookup is a Cypher query.

Sources (product/gates-RAG repo):
  ../../agents/slot_types/index.md   -> terms + extends (the term axis)
  ../../agents/gates/index.md        -> gates as hyperedges (consumes/emits/kind)

Run:  python build_hypergraph.py     # writes gate_hypergraph.json (+ ./opis_hg Kùzu db)
"""
import glob, json, os, re, shutil, kuzu
from pathlib import Path

HERE = Path(__file__).resolve().parent
AG = HERE.parent.parent / "agents"
OUT_JSON = HERE.parent / "gate_hypergraph.json"
DBDIR = Path(os.environ.get("OPIS_HG_DIR", HERE / "opis_hg"))

def _rm(p):
    for path in [str(p)] + glob.glob(str(p) + "*"):
        pp = Path(path)
        if pp.is_dir(): shutil.rmtree(pp, ignore_errors=True)
        elif pp.exists(): pp.unlink()

def parse_table(md, ncols):
    """yield cell-lists for pipe-table data rows (skip header/separator)."""
    for line in md.splitlines():
        s = line.strip()
        if not s.startswith("|"): continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < ncols: continue
        if cells[0] in ("type","gate") or set(cells[0]) <= set("-: "): continue
        yield cells

def load_terms():
    md = (AG/"slot_types/index.md").read_text()
    terms = {}
    for c in parse_table(md, 3):
        name, ext = c[0], c[1]
        terms[name] = None if ext in ("—","-","") else ext
    return terms

def split_terms(cell):
    return [t.strip() for t in cell.split(",") if t.strip() and t.strip() not in ("—","-")]

def load_gates():
    md = (AG/"gates/index.md").read_text()
    gates = []
    for c in parse_table(md, 5):
        gates.append({"gate": c[0], "kind": c[1],
                      "consumes": split_terms(c[2]), "emits": split_terms(c[3]),
                      "auth_required": c[4].lower().startswith("t")})
    return gates

def main():
    terms, gates = load_terms(), load_gates()
    hg = {"terms": terms, "gates": gates}
    OUT_JSON.write_text(json.dumps(hg, indent=2))

    _rm(DBDIR)
    conn = kuzu.Connection(kuzu.Database(str(DBDIR)))
    conn.execute("CREATE NODE TABLE Term(name STRING, extends STRING, PRIMARY KEY(name))")
    conn.execute("CREATE NODE TABLE Gate(name STRING, kind STRING, PRIMARY KEY(name))")
    conn.execute("CREATE REL TABLE EXTENDS(FROM Term TO Term)")
    conn.execute("CREATE REL TABLE CONSUMES(FROM Gate TO Term)")
    conn.execute("CREATE REL TABLE EMITS(FROM Gate TO Term)")
    for name, ext in terms.items():
        conn.execute("CREATE (:Term {name:$n, extends:$e})", {"n": name, "e": ext or ""})
    for name, ext in terms.items():
        if ext and ext in terms:
            conn.execute("MATCH (a:Term {name:$a}),(b:Term {name:$b}) CREATE (a)-[:EXTENDS]->(b)",
                         {"a": name, "b": ext})
    for g in gates:
        conn.execute("CREATE (:Gate {name:$n, kind:$k})", {"n": g["gate"], "k": g["kind"]})
        for t in g["consumes"]:
            conn.execute("MATCH (g:Gate {name:$g}),(t:Term {name:$t}) CREATE (g)-[:CONSUMES]->(t)",
                         {"g": g["gate"], "t": t})
        for t in g["emits"]:
            conn.execute("MATCH (g:Gate {name:$g}),(t:Term {name:$t}) CREATE (g)-[:EMITS]->(t)",
                         {"g": g["gate"], "t": t})
    def cnt(q): return conn.execute(q).get_next()[0]
    print(f"gate_hypergraph.json + {DBDIR.name}: {len(terms)} terms, {len(gates)} gate-hyperedges, "
          f"{cnt('MATCH ()-[r:CONSUMES]->() RETURN count(*)')} consumes, "
          f"{cnt('MATCH ()-[r:EMITS]->() RETURN count(*)')} emits edges")

if __name__ == "__main__":
    main()
