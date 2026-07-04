// ===========================================================================
// Opis gate-ontology loader for Neo4j
// ---------------------------------------------------------------------------
// Loads induced_ontology_v1.json into a property graph: the control-flow
// pattern <-> Opis gate-vocabulary mapping as a queryable graph. This is the
// store for the gate ontology (the eventual gates-RAG repo backend).
//
// Prereq: put induced_ontology_v1.json where Neo4j can read it. Two options:
//   A) copy it into <neo4j>/import/ and use file name only (default; below).
//   B) enable apoc.import.file.use_neo4j_config=false and use an absolute path.
//
// Run:  cat load_ontology.cypher | cypher-shell -u neo4j -p <pw>
//       (or paste into Neo4j Browser)
// APOC is used only to read the JSON file; the modelling is plain Cypher.
// ===========================================================================

// 0. Clean slate (safe: only touches these labels)
MATCH (n) WHERE n:Pattern OR n:Category OR n:GateLogic OR n:GateKind OR n:OpisConstruct
DETACH DELETE n;

// 1. Constraints (idempotent)
CREATE CONSTRAINT pattern_id IF NOT EXISTS FOR (p:Pattern) REQUIRE p.id IS UNIQUE;
CREATE CONSTRAINT target_id  IF NOT EXISTS FOR (t:Target)  REQUIRE t.id IS UNIQUE;

// 2. Read the JSON-LD @graph
CALL apoc.load.json("induced_ontology_v1.json") YIELD value
WITH value.`@graph` AS nodes
UNWIND nodes AS n

// 3. Create every node under a type-specific label, keyed by @id
CALL apoc.merge.node(
  [ CASE n.`@type`
      WHEN 'ControlFlowPattern' THEN 'Pattern'
      WHEN 'PatternCategory'    THEN 'Category'
      WHEN 'GateLogic'          THEN 'GateLogic'
      WHEN 'GateKind'           THEN 'GateKind'
      WHEN 'OpisConstruct'      THEN 'OpisConstruct'
      ELSE 'Node' END ],
  { id: n.`@id` },
  apoc.map.clean({
    name: n.name, wcpId: n.wcpId, semantics: n.semantics,
    synchronizes: n.synchronizes, mappingStrength: n.mappingStrength,
    opisGap: n.opisGap
  }, [], [null])
) YIELD node
RETURN count(node) AS nodes_created;

// 4. Second pass for relationships (re-read; small file, fine for practice)
CALL apoc.load.json("induced_ontology_v1.json") YIELD value
WITH value.`@graph` AS nodes
UNWIND nodes AS n
WITH n WHERE n.`@type` = 'ControlFlowPattern'

// 4a. Pattern -> Category
MATCH (p:Pattern {id: n.`@id`})
OPTIONAL MATCH (c:Category {id: n.inCategory})
FOREACH (_ IN CASE WHEN c IS NULL THEN [] ELSE [1] END |
  MERGE (p)-[:IN_CATEGORY]->(c))

// 4b. Pattern -> Opis target (GateLogic | GateKind | OpisConstruct), null = no counterpart
WITH n, p
OPTIONAL MATCH (t {id: n.mapsToOpis})
FOREACH (_ IN CASE WHEN t IS NULL THEN [] ELSE [1] END |
  MERGE (p)-[:MAPS_TO {strength: n.mappingStrength}]->(t))

// 4c. generalizes / specializes between patterns
WITH n, p
OPTIONAL MATCH (g:Pattern {id: n.generalizes})
FOREACH (_ IN CASE WHEN g IS NULL THEN [] ELSE [1] END |
  MERGE (p)-[:GENERALIZES]->(g))
WITH n, p
OPTIONAL MATCH (s:Pattern {id: n.specializes})
FOREACH (_ IN CASE WHEN s IS NULL THEN [] ELSE [1] END |
  MERGE (p)-[:SPECIALIZES]->(s))
RETURN count(*) AS patterns_wired;

// ===========================================================================
// Queries over the mapping (the diff report, as Cypher)
// ===========================================================================

// Q1. The finding: how many patterns map exact / partial / none?
// MATCH (p:Pattern) RETURN p.mappingStrength AS strength, count(*) AS n ORDER BY n DESC;

// Q2. Patterns Opis has NO counterpart for (the gaps), by category:
// MATCH (p:Pattern) WHERE p.mappingStrength = 'none'
// MATCH (p)-[:IN_CATEGORY]->(c:Category)
// RETURN c.name AS category, collect(p.wcpId + ' ' + p.name) AS gaps ORDER BY category;

// Q3. Which literature patterns collapse onto each Opis gate logic operator?
// MATCH (p:Pattern)-[m:MAPS_TO]->(t:GateLogic)
// RETURN t.name AS logic, m.strength AS strength, collect(p.name) AS patterns
// ORDER BY logic;

// Q4. The FIRST = THRESHOLD(n=1) specialization edge:
// MATCH (a:Pattern)-[:SPECIALIZES]->(b:Pattern) RETURN a.name, b.name;

// Q5. Cancellation family — the biggest gap (map to breaker, mostly partial/none):
// MATCH (p:Pattern)-[:IN_CATEGORY]->(c:Category {name:'Cancellation and Force-Completion'})
// OPTIONAL MATCH (p)-[m:MAPS_TO]->(t)
// RETURN p.name, coalesce(t.name,'—') AS opis, coalesce(m.strength,'none') AS strength, p.opisGap;

// ---------------------------------------------------------------------------
// NEXT (GraphRAG proper): add the actual Opis gates + slot_types as nodes and
// connect Gate-[:USES_LOGIC]->GateLogic, Gate-[:HAS_KIND]->GateKind,
// Term-[:EXTENDS]->Term, Gate-[:CONSUMES|EMITS]->Term. Then a gate-selection
// query becomes a graph traversal, and vector-embedding the pattern.semantics
// text gives you hybrid vector+graph retrieval to compare against flat RAG.
// ===========================================================================
