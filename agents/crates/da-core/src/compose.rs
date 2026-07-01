/// Compose logic — shared between da-compose (CLI) and da-cli (eval loop).
use crate::types::GateSpec;
use serde_json::{json, Map, Value};
use std::collections::{BTreeSet, HashMap, HashSet};

/// TransactionCoordination + 2PC-vocabulary input → sync gate.
/// TransactionCoordination + no 2PC inputs               → sentinel.
/// Everything else                                        → gate.
pub fn gate_kind(spec: &GateSpec) -> &'static str {
    let arch = spec.archetype.as_deref().unwrap_or("");
    if arch == "TransactionCoordination" {
        if spec.inputs.iter().any(|i| is_2pc_input(i)) { "sync" } else { "sentinel" }
    } else {
        "gate"
    }
}

/// Token-level 2PC keyword match.
/// "compensate-points" → yes; "compensation_channel" → no.
pub fn is_2pc_input(s: &str) -> bool {
    s.split(|c: char| !c.is_alphanumeric())
        .any(|tok| matches!(tok.to_lowercase().as_str(),
            "commit" | "compensate" | "prepare" | "rollback" | "abort"
        ))
}

/// Build outcome-bundle emits.
///
/// `sync` gates (true 2PC coordinators) have EXCLUSIVE outcomes — commit OR compensate.
/// Everything else fans out ALL outputs simultaneously (weight = 1.0).
pub fn outcome_emits(outputs: &[String], kind: &str) -> Value {
    if outputs.is_empty() {
        return json!([]);
    }
    if kind == "sync" {
        let n = outputs.len();
        let weight = (1.0_f64 / n as f64 * 1000.0).round() / 1000.0;
        json!(outputs.iter()
            .map(|out| json!({ "outcome": out, "flows": [out], "weight": weight }))
            .collect::<Vec<_>>())
    } else {
        json!([{ "outcome": "emit_all", "flows": outputs, "weight": 1.0 }])
    }
}

/// Assemble individual gate specs into a monolithic Opis JSON spec.
pub fn compose(specs: &[GateSpec]) -> Value {
    // pulse_type → gate that produces it
    let mut producers: HashMap<&str, &str> = HashMap::new();
    for spec in specs {
        for out in &spec.outputs {
            producers.insert(out.as_str(), spec.name.as_str());
        }
    }

    // Inputs that arrive from outside the flow
    let mut external_inputs: Vec<(&str, &str)> = vec![];
    for spec in specs {
        for inp in &spec.inputs {
            if !producers.contains_key(inp.as_str()) {
                external_inputs.push((inp.as_str(), spec.name.as_str()));
            }
        }
    }

    // One external source locus per unique external pulse type
    let mut ext_loci: HashMap<&str, &str> = HashMap::new();
    let mut loci_map: Map<String, Value> = Map::new();

    for (pulse_type, _) in &external_inputs {
        if ext_loci.contains_key(pulse_type) { continue; }
        let locus_name = format!("ext__{}", pulse_type.replace('.', "_").replace('-', "_"));
        ext_loci.insert(pulse_type, Box::leak(locus_name.clone().into_boxed_str()));
        loci_map.insert(locus_name, json!({
            "description": format!("External injection point for '{pulse_type}'"),
            "source": true
        }));
    }

    // Archetypes — one entry per unique pulse type
    let mut all_pulse_types: BTreeSet<&str> = BTreeSet::new();
    for spec in specs {
        for f in &spec.inputs  { all_pulse_types.insert(f.as_str()); }
        for f in &spec.outputs { all_pulse_types.insert(f.as_str()); }
    }
    let mut archetypes: Map<String, Value> = Map::new();
    for pt in &all_pulse_types {
        archetypes.insert(pt.to_string(), json!({ "description": pt }));
    }

    // Gates
    let mut gates: Map<String, Value> = Map::new();
    for spec in specs {
        let kind = gate_kind(spec);
        let emits = outcome_emits(&spec.outputs, kind);
        gates.insert(spec.name.clone(), json!({
            "kind":          kind,
            "description":   spec.description,
            "requires":      spec.inputs,
            "emits":         emits,
            "window_ms":     5000,
            "refractory_ms": 50
        }));
    }

    // Synapses
    let mut synapses: Vec<Value> = vec![];
    for (pulse_type, consumer) in &external_inputs {
        let locus = ext_loci[pulse_type];
        synapses.push(json!({ "from": locus, "to": consumer, "pulse_type": pulse_type }));
    }

    let mut consumed: HashSet<(&str, &str)> = HashSet::new();
    for spec in specs {
        for inp in &spec.inputs {
            if let Some(&producer) = producers.get(inp.as_str()) {
                synapses.push(json!({
                    "from": producer, "to": spec.name.as_str(), "pulse_type": inp.as_str()
                }));
                consumed.insert((producer, inp.as_str()));
            }
        }
    }

    // Terminal outputs → flow_sink
    let mut needs_sink = false;
    for spec in specs {
        for out in &spec.outputs {
            if !consumed.contains(&(spec.name.as_str(), out.as_str())) {
                needs_sink = true;
                synapses.push(json!({
                    "from": spec.name.as_str(), "to": "flow_sink", "pulse_type": out.as_str()
                }));
            }
        }
    }
    if needs_sink {
        loci_map.insert("flow_sink".to_string(), json!({
            "description": "Terminal sink — absorbs outputs that leave the system boundary",
            "persistent": true
        }));
    }

    json!({
        "comment":    "Composed by da-compose from individual gate spec.json files",
        "loci":       loci_map,
        "archetypes": archetypes,
        "gates":      gates,
        "synapses":   synapses
    })
}

/// Patch graph.json with explicit external locus edges and a `sources` array.
///
/// After FA runs and gate spec.json files exist, this computes which pulse types
/// have no producing gate → those are external inputs.  For each one it adds:
///   - a connection `{from: "ext__<pulse>", pulse_type, to: gate}` to `connections`
///   - the locus name to the `sources` array
///
/// This makes external-locus→gate edges explicit so the repair loop can cut them
/// and insert sentinels between the external source and the protected gate —
/// identical to how it handles gate→gate sentinel insertion.
///
/// Returns `true` if graph.json was modified.
pub fn patch_graph_external_loci(
    specs: &[GateSpec],
    graph_path: &std::path::Path,
) -> anyhow::Result<bool> {
    use std::collections::HashSet;

    // Build producers set
    let producers: HashSet<&str> = specs.iter()
        .flat_map(|s| s.outputs.iter().map(|o| o.as_str()))
        .collect();

    // Load graph.json
    let graph_raw = std::fs::read_to_string(graph_path)?;
    let mut graph: serde_json::Value = serde_json::from_str(&graph_raw)?;

    // Snapshot sources before taking the mutable borrow on connections
    let existing_sources: HashSet<String> = graph["sources"].as_array()
        .map(|a| a.iter().filter_map(|v| v.as_str().map(String::from)).collect())
        .unwrap_or_default();
    let mut new_sources: Vec<serde_json::Value> = graph["sources"].as_array()
        .cloned()
        .unwrap_or_default();

    let connections = graph["connections"].as_array_mut()
        .ok_or_else(|| anyhow::anyhow!("graph.json missing 'connections' array"))?;

    let mut added = false;

    for spec in specs {
        for inp in &spec.inputs {
            if producers.contains(inp.as_str()) { continue; }

            let locus_name = format!(
                "ext__{}",
                inp.replace('.', "_").replace('-', "_")
            );

            // Add edge if not already present
            let edge_exists = connections.iter().any(|c| {
                c["from"].as_str() == Some(locus_name.as_str())
                    && c["to"].as_str() == Some(spec.name.as_str())
            });
            if !edge_exists {
                connections.push(serde_json::json!({
                    "from": locus_name, "pulse_type": inp.as_str(), "to": spec.name.as_str()
                }));
                added = true;
                eprintln!("[graph] external locus: {locus_name} --{inp}--> {}", spec.name);
            }

            // Add locus to sources list (deduped)
            let in_existing = existing_sources.contains(&locus_name);
            let in_new = new_sources.iter().any(|s| s.as_str() == Some(locus_name.as_str()));
            if !in_existing && !in_new {
                new_sources.push(serde_json::json!(locus_name));
            }
        }
    }

    if added || graph["sources"].is_null() || graph["sources"].as_array().map(|a| a.is_empty()).unwrap_or(true) {
        graph["sources"] = serde_json::json!(new_sources);
        std::fs::write(graph_path, serde_json::to_string_pretty(&graph)?)?;
        return Ok(true);
    }

    Ok(false)
}

/// Load all gate spec.json files from a directory.
pub fn load_specs(gates_dir: &std::path::Path) -> anyhow::Result<Vec<GateSpec>> {
    let mut specs = vec![];
    for entry in std::fs::read_dir(gates_dir)? {
        let entry = entry?;
        let spec_path = entry.path().join("spec.json");
        if !spec_path.exists() { continue; }
        let raw = std::fs::read_to_string(&spec_path)?;
        if let Ok(spec) = serde_json::from_str::<GateSpec>(&raw) {
            specs.push(spec);
        }
    }
    Ok(specs)
}
