#!/usr/bin/env python3
"""
Load the Opis SA-taxonomy into an embedded Kùzu graph database.

Kùzu = "SQLite/DuckDB for graphs": a single embedded file, no server, speaks
Cypher. Simplest local graph DB that actually stores the graph (vs. hand-rolled
Python traversal). Data source is sa_taxonomy_v1.json (JSON-LD), so this is
portable to any GQL/Cypher store later.

Schema (property graph):
  (:Concept {id, label, ntype, axis, semantics, grounding, triggers})   -- taxonomy vocab + axes
  (:Gate    {name})                                                     -- gates that realize templates/kinds
  (:Concept)-[:ON_AXIS]->(:Concept {ntype:'axis'})
  (:Concept)-[:REALIZED_BY]->(:Gate)

`triggers` carries the lexical vocabulary (stems like "estimat","rout") AS GRAPH
DATA on each concept, so step-1 retrieval is a Cypher query, not Python string code.

Run:  python build_graph.py        # (re)builds ./opis_kuzu
"""
import json, os, shutil, kuzu
from pathlib import Path

HERE = Path(__file__).resolve().parent
TAXO = HERE.parent / "sa_taxonomy_v1.json"
# Kùzu needs a writable FS (WAL/shadow files). Default in-place for local use;
# override with OPIS_KUZU_DIR when the working dir is read-only (e.g. sandbox mount).
DBDIR = Path(os.environ.get("OPIS_KUZU_DIR", HERE / "opis_kuzu"))

# lexical trigger stems per role (knowledge stored AS DATA on concepts).
ROLE_TRIGGERS = {
    "logic:AND": ["all","both","combin","coordinat","aggregat","consolidat"],
    "logic:OR": ["either","any"],
    "logic:FIRST": ["first","accept","within a"],
    "logic:THRESHOLD": ["sufficient","majority","enough","several","quorum","fraction"],
    "tmpl:router": ["rout","dispatch","sent to","escalat","correct","fall back","fallback"],
    "tmpl:aggregator": ["aggregat","consolidat","reconcil","correlat","combine","ensemble"],
    "tmpl:scatter": ["broadcast","multiple service","several driver","several model","scatter"],
    "tmpl:filter": ["filter","validat","guardrail","unsafe","check","scoped","their own"],
    "tmpl:splitter": ["split","decompos","batch"],
    "tmpl:wiretap": ["rating","track","record","monitor","log "],
    "comp:map": ["comput","estimat","rank","calcul","fus","integrat","scor","price"],
    "comp:reduce": ["accumulat","count","point","loyalt","never oversold","capacit","inventor","baseline"],
    "comp:window": ["over a window","rolling","per window","windowed","within a short window"],
    "kind:sentinel": ["confirm","auth","consent","access","credential"],
    "kind:breaker": ["isolat","suspend","cut off","circuit","quarantin","trip"],
    "kind:regulator": ["rate-limit","throttl","cooldown","overwhelm","shed","one at a time","only one"],
}

def role_of(node):
    """map a taxonomy node to its role tag (axis:value) for trigger attachment."""
    t = node.get("@type",""); v = (node.get("opisValue") or "").lower()
    if t == "GateLogic": return "logic:"+v.upper() if v else None
    if t == "GateKind" and v in ("sentinel","breaker","regulator"): return "kind:"+v
    if t == "GateTemplate":
        for tag,key in [("tmpl:router","router"),("tmpl:aggregator","aggregat"),
                        ("tmpl:aggregator","join"),("tmpl:scatter","scatter"),
                        ("tmpl:filter","filter"),("tmpl:splitter","splitter"),
                        ("tmpl:wiretap","wire"),("tmpl:wiretap","observer")]:
            if key in v: return tag
    if t == "GateComputeTemplate":
        for tag,key in [("comp:map","transform"),("comp:map","domain service"),
                        ("comp:reduce","reducer"),("comp:window","windowed")]:
            if key in v: return tag
    return None

def main():
    if DBDIR.exists(): shutil.rmtree(DBDIR)
    doc = json.loads(TAXO.read_text())
    db = kuzu.Database(str(DBDIR)); conn = kuzu.Connection(db)

    conn.execute("CREATE NODE TABLE Concept(id STRING, label STRING, ntype STRING, "
                 "axis STRING, semantics STRING, grounding STRING, triggers STRING[], "
                 "PRIMARY KEY(id))")
    conn.execute("CREATE NODE TABLE Gate(name STRING, PRIMARY KEY(name))")
    conn.execute("CREATE REL TABLE ON_AXIS(FROM Concept TO Concept)")
    conn.execute("CREATE REL TABLE REALIZED_BY(FROM Concept TO Gate)")

    axis_ids = {n["@id"] for n in doc["@graph"] if n["@type"] == "TaxonomyAxis"}
    gates = set()
    # nodes
    for n in doc["@graph"]:
        role = role_of(n)
        trig = ROLE_TRIGGERS.get(role, [])
        conn.execute(
            "CREATE (:Concept {id:$id, label:$label, ntype:$ntype, axis:$axis, "
            "semantics:$sem, grounding:$gr, triggers:$trig})",
            {"id": n["@id"],
             "label": n.get("opisValue") or n.get("name") or n["@id"],
             "ntype": "axis" if n["@type"]=="TaxonomyAxis" else n["@type"],
             "axis": (n.get("onAxis") or "").split("axis_")[-1],
             "sem": (n.get("semantics") or n.get("note") or "")[:400],
             "gr": n.get("grounding") or "",
             "trig": trig})
        if n.get("realizedBy"): gates.add(n["realizedBy"])
    # gates
    for g in sorted(gates):
        conn.execute("CREATE (:Gate {name:$n})", {"n": g})
    # edges
    for n in doc["@graph"]:
        if n.get("onAxis"):
            conn.execute("MATCH (c:Concept {id:$a}),(x:Concept {id:$b}) "
                         "CREATE (c)-[:ON_AXIS]->(x)", {"a":n["@id"],"b":n["onAxis"]})
        if n.get("realizedBy"):
            conn.execute("MATCH (c:Concept {id:$a}),(g:Gate {name:$b}) "
                         "CREATE (c)-[:REALIZED_BY]->(g)", {"a":n["@id"],"b":n["realizedBy"]})

    n_c = conn.execute("MATCH (c:Concept) RETURN count(*)").get_next()[0]
    n_g = conn.execute("MATCH (g:Gate) RETURN count(*)").get_next()[0]
    n_r = conn.execute("MATCH ()-[r:REALIZED_BY]->() RETURN count(*)").get_next()[0]
    print(f"built {DBDIR.name}: {n_c} concepts, {n_g} gates, {n_r} realized-by edges")

if __name__ == "__main__":
    main()
