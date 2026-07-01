/// Pattern detector — runs after the Monte Carlo simulation and identifies
/// known anti-patterns by combining structural graph analysis with simulation signals.
///
/// Patterns are loaded from a `patterns/` directory (simple .md files with front-matter).
/// This is the "RAG as a file" phase: one file per pattern, looked up by ID.
use std::{collections::{HashMap, HashSet}, path::Path};

// ── Pattern loader ─────────────────────────────────────────────────────────────

pub struct Pattern {
    pub id:                  String,
    pub name:                String,
    pub threshold_fire_pct:  f64,
    pub remedy:              String,   // full body text for FA context
    pub fa_instruction:      String,   // the ## FA instruction section
}

impl Pattern {
    pub fn load(path: &Path) -> Option<Self> {
        let raw = std::fs::read_to_string(path).ok()?;

        // Parse front-matter between --- delimiters
        let inner = raw.trim_start_matches("---");
        let (fm, body) = inner.split_once("---")?;

        let mut id = String::new();
        let mut name = String::new();
        let mut threshold_fire_pct = 80.0_f64;

        for line in fm.lines() {
            if let Some(v) = line.strip_prefix("id:") {
                id = v.trim().to_string();
            } else if let Some(v) = line.strip_prefix("name:") {
                name = v.trim().to_string();
            } else if let Some(v) = line.strip_prefix("threshold_fire_pct:") {
                threshold_fire_pct = v.trim().parse().unwrap_or(80.0);
            }
        }

        if id.is_empty() { return None; }

        // Extract ## FA instruction section
        let fa_instruction = body
            .split("\n## ")
            .find(|s| s.starts_with("FA instruction"))
            .map(|s| s.trim_start_matches("FA instruction").trim().to_string())
            .unwrap_or_default();

        Some(Pattern { id, name, threshold_fire_pct, remedy: body.trim().to_string(), fa_instruction })
    }
}

pub fn load_patterns(dir: &Path) -> Vec<Pattern> {
    let mut patterns = vec![];
    let Ok(entries) = std::fs::read_dir(dir) else { return patterns };
    let mut paths: Vec<_> = entries.filter_map(|e| e.ok()).map(|e| e.path()).collect();
    paths.sort();
    for p in paths {
        if p.extension().map_or(false, |e| e == "md") {
            if let Some(pat) = Pattern::load(&p) {
                patterns.push(pat);
            }
        }
    }
    patterns
}

// ── Finding ────────────────────────────────────────────────────────────────────

pub struct Finding {
    pub pattern_id:    String,
    pub pattern_name:  String,
    pub gate:          String,
    pub fire_pct:      f64,
    /// Upstream producers that are causing the coincidence fan-in
    pub producers:     Vec<String>,
    pub fa_instruction: String,
}

// ── Structural analysis ────────────────────────────────────────────────────────

/// For each gate, find the set of immediate upstream gate producers per required pulse type.
/// Returns: gate_name → Vec<(pulse_type, producer_gate_or_locus)>
pub fn upstream_producers(
    _gates: &[crate::GateModel],
    synapses: &[crate::Synapse],
) -> HashMap<String, Vec<(String, String)>> {
    // (from, pulse_type) → [to] is already in routes; we need the inverse per gate
    // synapse: from → to via pulse_type
    // For gate G: find all synapses with to == G.name
    let mut result: HashMap<String, Vec<(String, String)>> = HashMap::new();

    for s in synapses {
        result
            .entry(s.to.clone())
            .or_default()
            .push((s.pulse_type.clone(), s.from.clone()));
    }

    result
}

/// Detect coincidence-drop: a gate has multiple required pulses from *different*
/// upstream gate producers (not loci — loci are external sources, always present).
fn has_independent_producers(
    gate_name: &str,
    producers_map: &HashMap<String, Vec<(String, String)>>,
    gate_names: &HashSet<&str>,
) -> Option<Vec<String>> {
    let producers = producers_map.get(gate_name)?;

    // Keep only producers that are gates (not external loci)
    let gate_producers: Vec<String> = producers
        .iter()
        .filter(|(_, from)| gate_names.contains(from.as_str()))
        .map(|(_, from)| from.clone())
        .collect::<HashSet<_>>()   // dedup
        .into_iter()
        .collect();

    if gate_producers.len() >= 2 {
        Some(gate_producers)
    } else {
        None
    }
}

// ── Main entry point ───────────────────────────────────────────────────────────

pub fn run(
    gates: &[crate::GateModel],
    synapses: &[crate::Synapse],
    fire_pcts: &HashMap<String, f64>,
    patterns: &[Pattern],
) -> Vec<Finding> {
    let gate_names: HashSet<&str> = gates.iter().map(|g| g.name.as_str()).collect();
    let producers_map = upstream_producers(gates, synapses);

    let mut findings = vec![];

    for pat in patterns {
        match pat.id.as_str() {
            "coincidence-drop" => {
                for gate in gates {
                    if gate.name == "flow_sink" || gate.name.starts_with("__") {
                        continue;
                    }
                    let fire_pct = fire_pcts.get(&gate.name).copied().unwrap_or(0.0);
                    if fire_pct >= pat.threshold_fire_pct {
                        continue;
                    }
                    // Check structural condition: 2+ upstream gate producers
                    if let Some(producers) =
                        has_independent_producers(&gate.name, &producers_map, &gate_names)
                    {
                        findings.push(Finding {
                            pattern_id:    pat.id.clone(),
                            pattern_name:  pat.name.clone(),
                            gate:          gate.name.clone(),
                            fire_pct,
                            producers,
                            fa_instruction: pat.fa_instruction.clone(),
                        });
                    }
                }
            }
            other => {
                eprintln!("[diagnose] unknown pattern id '{other}' — skipped");
            }
        }
    }

    findings
}

pub fn print_findings(findings: &[Finding]) {
    if findings.is_empty() {
        println!("Diagnosis:        no anti-patterns detected");
        return;
    }

    println!("\n── Anti-pattern findings ────────────────────────────────────────────────────\n");
    for f in findings {
        println!(
            "  [{}]  {}  (fire% = {:.1}%)",
            f.pattern_id, f.gate, f.fire_pct
        );
        println!("  Independent upstream producers: {}", f.producers.join(", "));
        println!("  Remedy → {}", f.fa_instruction.lines().next().unwrap_or("see pattern file"));
        println!();
    }
}
