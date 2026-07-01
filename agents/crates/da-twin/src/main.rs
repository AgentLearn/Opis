/// da-twin — Monte Carlo latency simulator for a composed Opis gate topology.
///
/// Usage:
///   da-twin --spec <composed.json> [--runs N] [--seed N] [--diagnose <patterns-dir>]
///
/// Default: 1000 runs, uniform[refractory_ms, window_ms] service time per gate.
/// Source loci inject their pulses at t=0.
/// Outputs: per-gate p50/p95/p99, bottleneck, dead gates.
/// With --diagnose: also runs structural anti-pattern detector after simulation.
use anyhow::{Context, Result};
use rand::{rngs::StdRng, Rng, SeedableRng};
use serde_json::Value;
use std::{
    collections::{HashMap, HashSet, VecDeque},
    path::PathBuf,
};

mod diagnose;

// ── Topology model ─────────────────────────────────────────────────────────────

#[derive(Debug)]
pub struct GateModel {
    name: String,
    requires: Vec<String>,          // pulse types that must co-arrive
    outcomes: Vec<OutcomeModel>,    // exclusive outcome bundles
    window_ms: f64,                 // coincidence window / max service time
    refractory_ms: f64,             // min service time
}

#[derive(Debug)]
pub struct OutcomeModel {
    flows: Vec<String>,  // pulse types emitted when this outcome is chosen
    weight: f64,
}

#[derive(Debug, Clone)]
pub struct Synapse {
    from: String,       // gate name or locus name
    to: String,         // gate name
    pulse_type: String,
}

#[derive(Debug)]
struct Topology {
    gates: Vec<GateModel>,
    source_loci: Vec<String>,
    synapses: Vec<Synapse>,
    /// Topological order (indices into `gates`)
    topo_order: Vec<usize>,
    /// (from_name, pulse_type) → Vec<dest_gate_name>
    routes: HashMap<(String, String), Vec<String>>,
}

impl Topology {
    fn from_json(v: &Value) -> Result<Self> {
        // Source loci: explicit (source: true) OR any synapse `from` that is not a gate.
        // The second form handles specs that don't annotate source loci explicitly.
        let loci = v.get("loci").and_then(|l| l.as_object()).cloned().unwrap_or_default();
        let explicit_sources: std::collections::HashSet<String> = loci
            .iter()
            .filter(|(_, lv)| lv.get("source").and_then(|s| s.as_bool()).unwrap_or(false))
            .map(|(k, _)| k.clone())
            .collect();

        // Gates
        let gates_obj = v
            .get("gates")
            .and_then(|g| g.as_object())
            .context("missing 'gates'")?;

        let mut gates = Vec::new();
        for (name, gv) in gates_obj {
            let requires: Vec<String> = gv
                .get("requires")
                .and_then(|r| r.as_array())
                .map(|arr| arr.iter().filter_map(|x| x.as_str().map(String::from)).collect())
                .unwrap_or_default();

            let window_ms = gv.get("window_ms").and_then(|x| x.as_f64()).unwrap_or(5000.0);
            let refractory_ms = gv.get("refractory_ms").and_then(|x| x.as_f64()).unwrap_or(50.0);
            // Ensure range is valid for gen_range (refractory <= window)
            let lo = refractory_ms.min(window_ms);
            let hi = window_ms.max(refractory_ms + 1.0);

            // Outcome bundles — two wire formats:
            //   bundled: [{outcome, flows, weight}, ...]
            //   plain:   ["pulse_type", ...]
            let outcomes: Vec<OutcomeModel> = match gv.get("emits").and_then(|e| e.as_array()) {
                None => vec![],
                Some(arr) => {
                    let mut total_w = 0.0f64;
                    let mut raw: Vec<(Vec<String>, f64)> = arr
                        .iter()
                        .filter_map(|ov| {
                            if let Some(obj) = ov.as_object() {
                                let flows = obj
                                    .get("flows")
                                    .and_then(|f| f.as_array())
                                    .map(|a| {
                                        a.iter()
                                            .filter_map(|x| x.as_str().map(String::from))
                                            .collect()
                                    })
                                    .unwrap_or_default();
                                let w = obj.get("weight").and_then(|w| w.as_f64()).unwrap_or(1.0);
                                total_w += w;
                                Some((flows, w))
                            } else if let Some(s) = ov.as_str() {
                                total_w += 1.0;
                                Some((vec![s.to_string()], 1.0))
                            } else {
                                None
                            }
                        })
                        .collect();
                    // Normalise weights so they sum to 1.0
                    if total_w > 0.0 {
                        for (_, w) in &mut raw {
                            *w /= total_w;
                        }
                    }
                    raw.into_iter().map(|(flows, weight)| OutcomeModel { flows, weight }).collect()
                }
            };

            gates.push(GateModel {
                name: name.clone(),
                requires,
                outcomes,
                window_ms: hi,
                refractory_ms: lo,
            });
        }

        // Synapses
        let synapses: Vec<Synapse> = v
            .get("synapses")
            .and_then(|s| s.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|sv| {
                        let from = sv.get("from").and_then(|x| x.as_str())?.to_string();
                        let to = sv.get("to").and_then(|x| x.as_str())?.to_string();
                        let pulse_type = sv.get("pulse_type").and_then(|x| x.as_str())?.to_string();
                        Some(Synapse { from, to, pulse_type })
                    })
                    .collect()
            })
            .unwrap_or_default();

        // Route index: (from, pulse_type) → [dest_gate]
        let mut routes: HashMap<(String, String), Vec<String>> = HashMap::new();
        for s in &synapses {
            routes
                .entry((s.from.clone(), s.pulse_type.clone()))
                .or_default()
                .push(s.to.clone());
        }

        // Resolve final source loci: explicit sources UNION any synapse `from` that is not a gate
        let gate_names: std::collections::HashSet<&str> = gates.iter().map(|g| g.name.as_str()).collect();
        let mut source_set = explicit_sources;
        for s in &synapses {
            if !gate_names.contains(s.from.as_str()) {
                source_set.insert(s.from.clone());
            }
        }
        let source_loci: Vec<String> = source_set.into_iter().collect();

        // Topological sort (Kahn's BFS over gate→gate synapse edges)
        let topo_order = topo_sort(&gates, &synapses);

        Ok(Topology { gates, source_loci, synapses, topo_order, routes })
    }
}

/// Kahn's topological sort on the gate dependency graph.
/// Edges: A → B when there's a synapse with from=A (gate) to=B.
fn topo_sort(gates: &[GateModel], synapses: &[Synapse]) -> Vec<usize> {
    let n = gates.len();
    let name_to_idx: HashMap<&str, usize> = gates
        .iter()
        .enumerate()
        .map(|(i, g)| (g.name.as_str(), i))
        .collect();

    let mut in_deg = vec![0usize; n];
    let mut adj: Vec<Vec<usize>> = vec![vec![]; n];

    for s in synapses {
        if let (Some(&u), Some(&v)) = (name_to_idx.get(s.from.as_str()), name_to_idx.get(s.to.as_str())) {
            // Avoid self-loops
            if u != v && !adj[u].contains(&v) {
                adj[u].push(v);
                in_deg[v] += 1;
            }
        }
    }

    let mut queue: VecDeque<usize> = (0..n).filter(|&i| in_deg[i] == 0).collect();
    let mut order = Vec::with_capacity(n);

    while let Some(u) = queue.pop_front() {
        order.push(u);
        for &v in &adj[u] {
            in_deg[v] -= 1;
            if in_deg[v] == 0 {
                queue.push_back(v);
            }
        }
    }

    // Cycle fallback: append any nodes not yet in order
    if order.len() < n {
        let seen: HashSet<usize> = order.iter().copied().collect();
        for i in 0..n {
            if !seen.contains(&i) {
                order.push(i);
            }
        }
    }

    order
}

// ── Simulation ─────────────────────────────────────────────────────────────────

/// Run one Monte Carlo pass through the topology.
/// Returns: gate_name → Option<fire_time_ms>
fn run_once(topo: &Topology, rng: &mut StdRng) -> HashMap<String, Option<f64>> {
    // pulse_avail[gate_name][pulse_type] = arrival time
    let mut pulse_avail: HashMap<String, HashMap<String, f64>> = HashMap::new();

    // Inject from source loci at t = 0
    for locus in &topo.source_loci {
        for s in &topo.synapses {
            if &s.from == locus {
                pulse_avail
                    .entry(s.to.clone())
                    .or_default()
                    .insert(s.pulse_type.clone(), 0.0);
            }
        }
    }

    let mut fire_times: HashMap<String, Option<f64>> = HashMap::new();

    for &idx in &topo.topo_order {
        let gate = &topo.gates[idx];

        // Can this gate fire?
        let avail = pulse_avail.get(&gate.name);
        let ready = if gate.requires.is_empty() {
            true // autonomous — fires at service time
        } else {
            gate.requires.iter().all(|req| {
                avail.map_or(false, |a| a.contains_key(req))
            })
        };

        if !ready {
            fire_times.insert(gate.name.clone(), None);
            continue;
        }

        // fire_time = max arrival + service time ~ U[refractory_ms, window_ms]
        let max_arrival: f64 = if gate.requires.is_empty() {
            0.0
        } else {
            gate.requires
                .iter()
                .filter_map(|req| avail.unwrap().get(req).copied())
                .fold(0.0_f64, f64::max)
        };

        let service: f64 = if gate.refractory_ms < gate.window_ms {
            rng.gen_range(gate.refractory_ms..gate.window_ms)
        } else {
            gate.window_ms
        };
        let fire_time = max_arrival + service;
        fire_times.insert(gate.name.clone(), Some(fire_time));

        // Choose outcome (normalised weights → cumulative draw)
        if gate.outcomes.is_empty() {
            continue;
        }
        let r: f64 = rng.gen_range(0.0..1.0);
        let mut cum = 0.0;
        let chosen = gate.outcomes.iter().find(|o| {
            cum += o.weight;
            r < cum
        }).unwrap_or(&gate.outcomes[gate.outcomes.len() - 1]);

        // Propagate emitted pulses downstream
        for pulse_type in &chosen.flows {
            let key = (gate.name.clone(), pulse_type.clone());
            if let Some(dests) = topo.routes.get(&key) {
                for dest in dests {
                    // Earlier pulse wins (deterministic in topological order)
                    pulse_avail
                        .entry(dest.clone())
                        .or_default()
                        .entry(pulse_type.clone())
                        .or_insert(fire_time);
                }
            }
        }
    }

    fire_times
}

// ── Statistics ─────────────────────────────────────────────────────────────────

fn percentile(sorted: &[f64], p: f64) -> f64 {
    if sorted.is_empty() { return 0.0; }
    let idx = ((sorted.len() as f64 - 1.0) * p / 100.0).round() as usize;
    sorted[idx.min(sorted.len() - 1)]
}

// ── Main ────────────────────────────────────────────────────────────────────────

fn main() -> Result<()> {
    let args: Vec<String> = std::env::args().collect();
    let cfg = Config::parse(&args)?;

    let raw = std::fs::read_to_string(&cfg.spec_path)
        .with_context(|| format!("reading {:?}", cfg.spec_path))?;
    let spec: Value = serde_json::from_str(&raw)?;
    let topo = Topology::from_json(&spec)?;

    let flow_name = cfg.spec_path.file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("topology");

    eprintln!(
        "opis-twin — {} — {} gate(s), {} run(s), seed: {}",
        flow_name,
        topo.gates.len(),
        cfg.runs,
        cfg.seed.map_or("random".to_string(), |s| s.to_string()),
    );

    let mut rng = match cfg.seed {
        Some(s) => StdRng::seed_from_u64(s),
        None    => StdRng::from_entropy(),
    };

    // Accumulate per-gate fire times across all runs
    let mut gate_times: HashMap<String, Vec<f64>> = HashMap::new();
    let mut gate_miss:  HashMap<String, usize>    = HashMap::new();

    for _ in 0..cfg.runs {
        let result = run_once(&topo, &mut rng);
        for (gate, ft) in result {
            match ft {
                Some(t) => gate_times.entry(gate).or_default().push(t),
                None    => *gate_miss.entry(gate).or_default() += 1,
            }
        }
    }

    // Sort and compute stats for each gate
    struct Row {
        name:      String,
        p50:       f64,
        p95:       f64,
        p99:       f64,
        mean:      f64,
        fire_pct:  f64,   // fraction of runs that fired
    }

    let mut rows: Vec<Row> = topo
        .gates
        .iter()
        .filter(|g| g.name != "flow_sink" && !g.name.starts_with("__"))
        .map(|gate| {
            let mut times = gate_times.get(&gate.name).cloned().unwrap_or_default();
            let misses = gate_miss.get(&gate.name).copied().unwrap_or(0);
            let fired  = times.len();
            let total  = fired + misses;
            times.sort_by(|a, b| a.partial_cmp(b).unwrap());
            let mean     = if fired > 0 { times.iter().sum::<f64>() / fired as f64 } else { 0.0 };
            let p50      = percentile(&times, 50.0);
            let p95      = percentile(&times, 95.0);
            let p99      = percentile(&times, 99.0);
            let fire_pct = if total > 0 { 100.0 * fired as f64 / total as f64 } else { 0.0 };
            Row { name: gate.name.clone(), p50, p95, p99, mean, fire_pct }
        })
        .collect();

    // Sort by p99 desc
    rows.sort_by(|a, b| b.p99.partial_cmp(&a.p99).unwrap_or(std::cmp::Ordering::Equal));

    // ── Report ──────────────────────────────────────────────────────────────────

    println!("\nTwin — {flow_name} — {} run(s)\n", cfg.runs);
    println!("{:<42} {:>8} {:>8} {:>8} {:>8} {:>7}",
        "Gate", "p50 ms", "p95 ms", "p99 ms", "mean ms", "fire%");
    println!("{}", "─".repeat(87));

    let mut bottleneck_name = String::new();
    let mut bottleneck_p99  = 0.0f64;

    for r in &rows {
        println!("{:<42} {:>8.0} {:>8.0} {:>8.0} {:>8.0} {:>6.1}%",
            r.name, r.p50, r.p95, r.p99, r.mean, r.fire_pct);
        if r.fire_pct > 0.0 && r.p99 > bottleneck_p99 {
            bottleneck_p99  = r.p99;
            bottleneck_name = r.name.clone();
        }
    }

    println!();

    if !bottleneck_name.is_empty() {
        println!("Bottleneck (p99): {} ({:.0} ms)", bottleneck_name, bottleneck_p99);
    }

    let dead: Vec<&str> = rows
        .iter()
        .filter(|r| r.fire_pct == 0.0)
        .map(|r| r.name.as_str())
        .collect();

    if dead.is_empty() {
        println!("Dead gates:       none");
    } else {
        println!("Dead gates:       {}", dead.join(", "));
    }

    // End-to-end: latest p99 fire time across all fired gates
    let e2e_p99 = rows.iter().filter(|r| r.fire_pct > 0.0).map(|r| r.p99).fold(0.0_f64, f64::max);
    if e2e_p99 > 0.0 {
        println!("E2E p99:          {:.0} ms", e2e_p99);
    }

    println!();

    // ── Anti-pattern detector ──────────────────────────────────────────────────
    if let Some(patterns_dir) = &cfg.diagnose_dir {
        let patterns = diagnose::load_patterns(patterns_dir);
        if patterns.is_empty() {
            eprintln!("[diagnose] no patterns found in {:?}", patterns_dir);
        } else {
            eprintln!("[diagnose] {} pattern(s) loaded", patterns.len());
            // Build fire_pct map from simulation rows
            let fire_pcts: HashMap<String, f64> = rows.iter()
                .map(|r| (r.name.clone(), r.fire_pct))
                .collect();
            let findings = diagnose::run(&topo.gates, &topo.synapses, &fire_pcts, &patterns);
            diagnose::print_findings(&findings);
        }
    }

    Ok(())
}

// ── Config ─────────────────────────────────────────────────────────────────────

struct Config {
    spec_path:    PathBuf,
    runs:         usize,
    seed:         Option<u64>,
    diagnose_dir: Option<PathBuf>,
}

impl Config {
    fn parse(args: &[String]) -> Result<Self> {
        let mut spec_path    = None;
        let mut runs         = 1000usize;
        let mut seed         = None;
        let mut diagnose_dir = None;

        let mut i = 1;
        while i < args.len() {
            match args[i].as_str() {
                "--spec"     => { spec_path    = Some(PathBuf::from(&args[i + 1])); i += 2; }
                "--runs"     => { runs         = args[i + 1].parse().context("--runs must be a positive integer")?; i += 2; }
                "--seed"     => { seed         = Some(args[i + 1].parse().context("--seed must be an integer")?); i += 2; }
                "--diagnose" => { diagnose_dir = Some(PathBuf::from(&args[i + 1])); i += 2; }
                other        => anyhow::bail!("unknown argument: {other}"),
            }
        }

        let spec_path = spec_path.context("--spec <composed.json> is required")?;
        Ok(Config { spec_path, runs, seed, diagnose_dir })
    }
}
