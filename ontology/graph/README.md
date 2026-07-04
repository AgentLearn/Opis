# ontology/graph — SA-taxonomy in an embedded graph DB (Kùzu)

Step 1 of the Opis GraphRAG pipeline, on a real graph database instead of
hand-rolled Python traversal.

**Engine: Kùzu** — embedded (single directory, like SQLite/DuckDB), no server,
speaks Cypher (openCypher). `pip install kuzu`. Archived upstream (Apple, Oct 2025)
but the package is stable MIT; the fork is LadybugDB, same Cypher, drop-in later.
The data source is `../sa_taxonomy_v1.json` (JSON-LD), so the graph is portable to
any Cypher/GQL store.

## Files
- `build_graph.py` — loads `sa_taxonomy_v1.json` into `./opis_kuzu` (Concept + Gate
  nodes, ON_AXIS + REALIZED_BY edges). Lexical trigger stems are stored AS DATA on
  each concept (`triggers` property) so retrieval is a query, not code.
- `step1.py` — step-1 retrieval: one Cypher query per kata behaviour → the relevant
  SA-taxonomy subset (logic / template_movement / template_computation / kind) +
  candidate gates via REALIZED_BY.

## Run
```
pip install kuzu --break-system-packages
cd ontology/graph
python build_graph.py                       # builds ./opis_kuzu
python step1.py                             # silicon by default
python step1.py ../../agents/katas/aegiswatch_threat_detection.md
```
On a read-only working dir (e.g. the sandbox mount), point the DB at writable space:
`OPIS_KUZU_DIR=/tmp/opis_kuzu python build_graph.py`. `opis_kuzu/` is regenerated
by build_graph.py — do not commit it (add to .gitignore).

## Pipeline position
```
kata behaviour + typed DSL terms  --(step1.py Cypher)-->  SA-taxonomy subset + candidate gates
                                  --(FA / generation)-->  chosen gate
```
Retrieval is recall-biased on purpose: hand FA a candidate subset; FA (generation)
prunes to the chosen gate.

## Portability / GQL note
The retrieval query (`MATCH / UNWIND / WITH / OPTIONAL MATCH / RETURN / collect`) is
core openCypher — the dialect converging into the ISO GQL standard (39075:2024) — and
ports to Neo4j / other GQL-family stores with little change. The **schema DDL**
(`CREATE NODE TABLE ...`) is Kùzu's typed-table form and would differ on a
schema-optional store; the JSON-LD data is fully portable regardless.
