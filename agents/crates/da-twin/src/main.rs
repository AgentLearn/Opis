/// da-twin — Monte Carlo latency simulator for an Opis flow topology.
///
/// Usage:
///   da-twin --spec <flow.json> [--runs N] [--seed N] [--latencies <latencies.json>]
///           [--report <twin_report.json>] [--diagnose <patterns-dir>]
///           [--substitutions <subs.json>]   (co-sim: real gate implementations
///                                            as subprocesses — see substitute.rs)
///
/// Consumes a flow spec directly (loci/gates/synapses — the same format
/// opis-eval reads; the old separate "composed.json" is no longer required).
///
/// Timing model (GA_PLAN Phase 3):
///   - Gate service time: lognormal from the latency library's `operations`
///     entry for the gate's `gate_template`; gates without an entry fall back
///     to a window-derived lognormal (p50 = 20% of window_ms, p95 = 60%).
///     Without --latencies, the legacy uniform[refractory_ms, window_ms] is
///     used (kept for comparability with old runs).
///   - Synapse traversal: lognormal from the library's `media` entry for the
///     synapse's `medium` (local / lan / internet); zero without --latencies.
///   - Readiness is logic-aware (AND / OR / FIRST / THRESHOLD.n, `optional`
///     excluded) and subtype-aware via the spec's archetype `extends` chains —
///     the same two rules opis-proof applies statically. Join time: AND = max
///     over required arrivals, OR/FIRST = earliest satisfying arrival,
///     THRESHOLD.n = n-th earliest.
///
/// Source loci inject their pulses at t=0.
/// Outputs: per-gate p50/p95/p99/fire%, bottleneck, dead gates; --report
/// writes the same machine-readable (twin_report.json) for twin_check.py.
use anyhow::{Context, Result};
use rand::{rngs::StdRng, Rng, SeedableRng};
use serde_json::{json, Value};
use std::{
    collections::{HashMap, HashSet, VecDeque},
    path::PathBuf,
};

mod diagnose;
mod substitute;

// ── Topology model ─────────────────────────────────────────────────────────────

#[derive(Debug)]
pub struct GateModel {
    name: String,
    template: Option<String>,       // gate_template, keys the latency library
    requires: Vec<String>,          // pulse types that must co-arrive (minus optional)
    #[allow(dead_code)]
    optional: HashSet<String>,
    logic_op: LogicOp,
    outcomes: Vec<OutcomeModel>,    // exclusive outcome bundles
    window_ms: f64,                 // coincidence window / max service time
    refractory_ms: f64,             // min service time
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum LogicOp {
    And,
    Or,             // OR and FIRST behave identically for timing: earliest wins
    Threshold(usize),
}

#[derive(Debug)]
pub struct OutcomeModel {
    name: Option<String>, // outcome label — substituted gates select by name
    flows: Vec<String>,   // pulse types emitted when this outcome is chosen
    weight: f64,
}

#[derive(Debug, Clone)]
pub struct Synapse {
    from: String,           // gate name or locus name
    to: String,             // gate name
    pulse_type: String,
    medium: Option<String>, // keys the latency library's `media`
}

#[derive(Debug)]
struct Topology {
    gates: Vec<GateModel>,
    source_loci: Vec<String>,
    synapses: Vec<Synapse>,
    /// Topological order (indices into `gates`)
    topo_order: Vec<usize>,
    /// type → all ancestors (transitive, via archetype `extends`)
    ancestors: HashMap<String, HashSet<String>>,
}

fn parse_logic(gv: &Value) -> LogicOp {
    match gv.get("logic") {
        None => LogicOp::And,
        Some(Value::String(s)) => match s.to_uppercase().as_str() {
            "OR" | "FIRST" => LogicOp::Or,
            "THRESHOLD" => LogicOp::Threshold(1),
            _ => LogicOp::And,
        },
        Some(Value::Object(o)) => {
            let op = o.get("op").and_then(|x| x.as_str()).unwrap_or("AND").to_uppercase();
            match op.as_str() {
                "OR" | "FIRST" => LogicOp::Or,
                "THRESHOLD" => {
                    let n = o.get("n").and_then(|x| x.as_u64()).unwrap_or(1) as usize;
                    LogicOp::Threshold(n.max(1))
                }
                _ => LogicOp::And,
            }
        }
        _ => LogicOp::And,
    }
}

impl Topology {
    fn from_json(v: &Value) -> Result<Self> {
        // Source loci: explicit (source: true) OR any synapse `from` that is not a gate.
        // The second form handles specs that don't annotate source loci explicitly.
        let loci = v.get("loci").and_then(|l| l.as_object()).cloned().unwrap_or_default();
        let explicit_sources: HashSet<String> = loci
            .iter()
            .filter(|(_, lv)| lv.get("source").and_then(|s| s.as_bool()).unwrap_or(false))
            .map(|(k, _)| k.clone())
            .collect();

        // Archetype ancestry (transitive closure of `extends`) — subtype matching
        let mut parent: HashMap<String, String> = HashMap::new();
        if let Some(arch) = v.get("archetypes").and_then(|a| a.as_object()) {
            for (name, av) in arch {
                if let Some(p) = av.get("extends").and_then(|x| x.as_str()) {
                    parent.insert(name.clone(), p.to_string());
                }
            }
        }
        let mut ancestors: HashMap<String, HashSet<String>> = HashMap::new();
        for name in parent.keys() {
            let mut anc = HashSet::new();
            let mut cur = name.clone();
            while let Some(p) = parent.get(&cur) {
                if !anc.insert(p.clone()) {
                    break; // defensive: cycle in extends
                }
                cur = p.clone();
            }
            ancestors.insert(name.clone(), anc);
        }

        // Gates
        let gates_obj = v
            .get("gates")
            .and_then(|g| g.as_object())
            .context("missing 'gates'")?;

        let mut gates = Vec::new();
        for (name, gv) in gates_obj {
            let optional: HashSet<String> = gv
                .get("optional")
                .and_then(|r| r.as_array())
                .map(|arr| arr.iter().filter_map(|x| x.as_str().map(String::from)).collect())
                .unwrap_or_default();
            let requires: Vec<String> = gv
                .get("requires")
                .and_then(|r| r.as_array())
                .map(|arr| {
                    arr.iter()
                        .filter_map(|x| x.as_str().map(String::from))
                        .filter(|t| !optional.contains(t))
                        .collect()
                })
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
                    let mut raw: Vec<(Option<String>, Vec<String>, f64)> = arr
                        .iter()
                        .filter_map(|ov| {
                            if let Some(obj) = ov.as_object() {
                                let name = obj.get("outcome").and_then(|x| x.as_str()).map(String::from);
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
                                Some((name, flows, w))
                            } else if let Some(s) = ov.as_str() {
                                total_w += 1.0;
                                Some((None, vec![s.to_string()], 1.0))
                            } else {
                                None
                            }
                        })
                        .collect();
                    // Normalise weights so they sum to 1.0
                    if total_w > 0.0 {
                        for (_, _, w) in &mut raw {
                            *w /= total_w;
                        }
                    }
                    raw.into_iter().map(|(name, flows, weight)| OutcomeModel { name, flows, weight }).collect()
                }
            };

            gates.push(GateModel {
                name: name.clone(),
                template: gv.get("gate_template").and_then(|x| x.as_str()).map(String::from),
                requires,
                optional,
                logic_op: parse_logic(gv),
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
                        let medium = sv.get("medium").and_then(|x| x.as_str()).map(String::from);
                        Some(Synapse { from, to, pulse_type, medium })
                    })
                    .collect()
            })
            .unwrap_or_default();

        // Resolve final source loci: explicit sources UNION any synapse `from` that is not a gate
        let gate_names: HashSet<&str> = gates.iter().map(|g| g.name.as_str()).collect();
        let mut source_set = explicit_sources;
        for s in &synapses {
            if !gate_names.contains(s.from.as_str()) {
                source_set.insert(s.from.clone());
            }
        }
        let source_loci: Vec<String> = source_set.into_iter().collect();

        // Topological sort (Kahn's BFS over gate→gate synapse edges)
        let topo_order = topo_sort(&gates, &synapses);

        Ok(Topology { gates, source_loci, synapses, topo_order, ancestors })
    }

    /// Does concrete arrived type `t` satisfy requirement `req`? (t == req, or
    /// req is an ancestor of t via archetype extends chains — same rule as
    /// opis-proof's subtype-aware matching.)
    fn matches(&self, t: &str, req: &str) -> bool {
        t == req || self.ancestors.get(t).map_or(false, |a| a.contains(req))
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

// ── Latency library (GA_PLAN Phase 4) ─────────────────────────────────────────

/// Lognormal parameterized by (μ, σ) derived from p50/p95:
/// μ = ln p50, σ = (ln p95 − ln p50) / 1.645.
#[derive(Debug, Clone, Copy)]
struct LogNormal {
    mu: f64,
    sigma: f64,
}

impl LogNormal {
    fn from_p50_p95(p50: f64, p95: f64) -> Self {
        let p50 = p50.max(0.001);
        let p95 = p95.max(p50 * 1.001);
        LogNormal { mu: p50.ln(), sigma: (p95.ln() - p50.ln()) / 1.645 }
    }

    fn sample(&self, rng: &mut StdRng) -> f64 {
        // Box–Muller (rand 0.8 here, no rand_distr dependency)
        let u1: f64 = rng.gen_range(1e-12..1.0);
        let u2: f64 = rng.gen_range(0.0..1.0);
        let z = (-2.0 * u1.ln()).sqrt() * (2.0 * std::f64::consts::PI * u2).cos();
        (self.mu + self.sigma * z).exp()
    }
}

#[derive(Debug, Default)]
struct LatencyLib {
    media: HashMap<String, LogNormal>,
    operations: HashMap<String, LogNormal>,
}

impl LatencyLib {
    fn load(path: &PathBuf) -> Result<Self> {
        let raw = std::fs::read_to_string(path)
            .with_context(|| format!("reading latency library {:?}", path))?;
        let v: Value = serde_json::from_str(&raw)?;
        let mut lib = LatencyLib::default();
        for (section, target) in [("media", &mut lib.media), ("operations", &mut lib.operations)] {
            if let Some(obj) = v.get(section).and_then(|m| m.as_object()) {
                for (k, entry) in obj {
                    let p50 = entry.get("p50_ms").and_then(|x| x.as_f64());
                    let p95 = entry.get("p95_ms").and_then(|x| x.as_f64());
                    if let (Some(p50), Some(p95)) = (p50, p95) {
                        target.insert(k.clone(), LogNormal::from_p50_p95(p50, p95));
                    }
                }
            }
        }
        Ok(lib)
    }
}

/// How a gate's service time was modelled — carried into the report so
/// llm-estimate/fallback numbers are never silently mixed with sourced ones.
#[derive(Debug, Clone, Copy, PartialEq)]
enum ServiceSource {
    Library,        // operations entry for the gate_template
    WindowFallback, // no library entry: lognormal(p50=0.2·window, p95=0.6·window)
    LegacyUniform,  // no --latencies: uniform[refractory, window]
    Substituted,    // real implementation: measured service time, actual outcome
}

fn service_source_str(s: ServiceSource) -> &'static str {
    match s {
        ServiceSource::Library        => "library",
        ServiceSource::WindowFallback => "window-fallback",
        ServiceSource::LegacyUniform  => "uniform",
        ServiceSource::Substituted    => "substituted",
    }
}

fn service_model(gate: &GateModel, lib: Option<&LatencyLib>) -> (ServiceSource, Option<LogNormal>) {
    match lib {
        None => (ServiceSource::LegacyUniform, None),
        Some(l) => {
            if let Some(t) = &gate.template {
                if let Some(d) = l.operations.get(t) {
                    return (ServiceSource::Library, Some(*d));
                }
            }
            (
                ServiceSource::WindowFallback,
                Some(LogNormal::from_p50_p95(0.2 * gate.window_ms, 0.6 * gate.window_ms)),
            )
        }
    }
}

// ── Simulation ─────────────────────────────────────────────────────────────────

/// Run one Monte Carlo pass through the topology.
/// Returns: gate_name → Option<fire_time_ms>
fn run_once(
    topo: &Topology,
    rng: &mut StdRng,
    lib: Option<&LatencyLib>,
    services: &[(ServiceSource, Option<LogNormal>)],
    routes_out: &HashMap<String, Vec<usize>>, // from-node → synapse indices
    subs: &mut Option<substitute::SubPool>,   // co-sim: real gate implementations
    run_idx: usize,
) -> Result<HashMap<String, Option<f64>>> {
    // pulse_avail[gate_name][concrete pulse_type] = earliest arrival time
    let mut pulse_avail: HashMap<String, HashMap<String, f64>> = HashMap::new();

    fn deliver(
        avail: &mut HashMap<String, HashMap<String, f64>>,
        syn: &Synapse,
        t_send: f64,
        lib: Option<&LatencyLib>,
        rng: &mut StdRng,
    ) {
        let hop = match (lib, &syn.medium) {
            (Some(l), Some(m)) => l.media.get(m).map_or(0.0, |d| d.sample(rng)),
            _ => 0.0,
        };
        let entry = avail
            .entry(syn.to.clone())
            .or_default()
            .entry(syn.pulse_type.clone())
            .or_insert(f64::INFINITY);
        let arrival = t_send + hop;
        if arrival < *entry {
            *entry = arrival;
        }
    }

    // Inject from source loci at t = 0
    for locus in &topo.source_loci {
        if let Some(idxs) = routes_out.get(locus) {
            for &i in idxs {
                deliver(&mut pulse_avail, &topo.synapses[i], 0.0, lib, rng);
            }
        }
    }

    let mut fire_times: HashMap<String, Option<f64>> = HashMap::new();

    // Iterate to a fixed point: a single topological pass starves gates inside
    // requires-cycles (a cycle member evaluated before its in-cycle supplier
    // never sees the pulse). Each gate still fires AT MOST ONCE per admission —
    // repeat passes only give not-yet-fired gates another look as pulses
    // propagate around cycles. Bounded by gate count (each extra pass must
    // fire ≥1 new gate to continue).
    let mut passes = 0;
    loop {
        let mut newly_fired = false;
        passes += 1;

    for &idx in &topo.topo_order {
        let gate = &topo.gates[idx];
        if matches!(fire_times.get(&gate.name), Some(Some(_))) {
            continue; // already fired this admission
        }
        let avail = pulse_avail.get(&gate.name).cloned();

        // Per requirement: earliest arrived concrete type that satisfies it
        // (subtype-aware). None if nothing satisfying arrived.
        let arrivals: Vec<Option<f64>> = gate
            .requires
            .iter()
            .map(|req| {
                avail.as_ref().and_then(|a| {
                    a.iter()
                        .filter(|(t, _)| topo.matches(t, req))
                        .map(|(_, &time)| time)
                        .fold(None, |acc: Option<f64>, t| Some(acc.map_or(t, |x: f64| x.min(t))))
                })
            })
            .collect();

        let mut present: Vec<f64> = arrivals.iter().filter_map(|x| *x).collect();
        present.sort_by(|a, b| a.partial_cmp(b).unwrap());

        let join: Option<f64> = if gate.requires.is_empty() {
            Some(0.0) // autonomous — fires at service time
        } else {
            match gate.logic_op {
                LogicOp::And => {
                    if present.len() == gate.requires.len() {
                        present.last().copied() // latest of all required
                    } else {
                        None
                    }
                }
                LogicOp::Or => present.first().copied(), // earliest satisfier
                LogicOp::Threshold(n) => {
                    if present.len() >= n {
                        Some(present[n - 1]) // n-th earliest
                    } else {
                        None
                    }
                }
            }
        };

        let join_time = match join {
            Some(t) => t,
            None => {
                fire_times.insert(gate.name.clone(), None); // may still fire a later pass
                continue;
            }
        };
        newly_fired = true;

        // ── Substituted gate: real decision logic replaces both the service
        //    sample AND the outcome draw ─────────────────────────────────────
        let substituted = subs.as_ref().map_or(false, |p| p.is_substituted(&gate.name));
        if substituted {
            let inputs: Vec<substitute::InputPulse> = avail
                .as_ref()
                .map(|a| {
                    a.iter()
                        .filter(|(t, &time)| {
                            time <= join_time
                                && gate.requires.iter().any(|req| topo.matches(t, req))
                        })
                        .map(|(t, &time)| substitute::InputPulse {
                            pulse_type: t.clone(),
                            arrival_ms: time,
                            body: Value::Null, // payload generators fill this (slice step 3)
                        })
                        .collect()
                })
                .unwrap_or_default();

            let resp = subs
                .as_mut()
                .unwrap()
                .call(&gate.name, run_idx, join_time, &inputs)?;

            let fire_time = join_time + resp.service_ms;
            fire_times.insert(gate.name.clone(), Some(fire_time));

            if !gate.outcomes.is_empty() {
                let outcome_name = resp.outcome.as_deref().with_context(|| {
                    format!(
                        "substituted gate '{}' has declared outcomes but returned none",
                        gate.name
                    )
                })?;
                let chosen = gate
                    .outcomes
                    .iter()
                    .find(|o| o.name.as_deref() == Some(outcome_name))
                    .with_context(|| {
                        format!(
                            "substituted gate '{}' returned undeclared outcome '{}' (declared: {:?})",
                            gate.name,
                            outcome_name,
                            gate.outcomes.iter().filter_map(|o| o.name.as_deref()).collect::<Vec<_>>()
                        )
                    })?;
                // Contract check: actual outputs ⊆ the chosen outcome's declared flows
                for out in &resp.outputs {
                    if !chosen.flows.iter().any(|f| f == &out.pulse_type) {
                        anyhow::bail!(
                            "substituted gate '{}' emitted '{}' not declared under outcome '{}' (flows: {:?})",
                            gate.name, out.pulse_type, outcome_name, chosen.flows
                        );
                    }
                }
                // Propagate what the real code actually emitted (may be a subset);
                // if it returned no outputs, fall back to the declared flows.
                let emitted: Vec<&String> = if resp.outputs.is_empty() {
                    chosen.flows.iter().collect()
                } else {
                    resp.outputs.iter().map(|o| &o.pulse_type).collect()
                };
                for pulse_type in emitted {
                    if let Some(idxs) = routes_out.get(&gate.name) {
                        for &i in idxs {
                            if &topo.synapses[i].pulse_type == pulse_type {
                                deliver(&mut pulse_avail, &topo.synapses[i], fire_time, lib, rng);
                            }
                        }
                    }
                }
            }
            continue;
        }

        let (source, dist) = services[idx];
        let service: f64 = match (source, dist) {
            (ServiceSource::LegacyUniform, _) => {
                if gate.refractory_ms < gate.window_ms {
                    rng.gen_range(gate.refractory_ms..gate.window_ms)
                } else {
                    gate.window_ms
                }
            }
            (_, Some(d)) => d.sample(rng),
            _ => 0.0,
        };
        let fire_time = join_time + service;
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

        // Propagate emitted pulses downstream (with per-synapse medium latency)
        for pulse_type in &chosen.flows {
            if let Some(idxs) = routes_out.get(&gate.name) {
                for &i in idxs {
                    if &topo.synapses[i].pulse_type == pulse_type {
                        deliver(&mut pulse_avail, &topo.synapses[i], fire_time, lib, rng);
                    }
                }
            }
        }
    }

        if !newly_fired || passes > topo.gates.len() {
            break;
        }
    }

    Ok(fire_times)
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

    let lib: Option<LatencyLib> = match &cfg.latencies_path {
        Some(p) => Some(LatencyLib::load(p)?),
        None => None,
    };

    let flow_name = cfg.spec_path.file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("topology");

    eprintln!(
        "opis-twin — {} — {} gate(s), {} run(s), seed: {}, latencies: {}",
        flow_name,
        topo.gates.len(),
        cfg.runs,
        cfg.seed.map_or("random".to_string(), |s| s.to_string()),
        cfg.latencies_path.as_ref().map_or("none (legacy uniform)".to_string(),
                                           |p| p.display().to_string()),
    );

    let mut rng = match cfg.seed {
        Some(s) => StdRng::seed_from_u64(s),
        None    => StdRng::from_entropy(),
    };

    // Substituted gates (co-simulation): spawn real implementations
    let mut subs: Option<substitute::SubPool> = match &cfg.substitutions_path {
        Some(p) => {
            let pool = substitute::SubPool::from_manifest(p)?;
            let names = pool.gate_names();
            for n in &names {
                if !topo.gates.iter().any(|g| &g.name == n) {
                    anyhow::bail!("substitution manifest names unknown gate '{}'", n);
                }
            }
            eprintln!("[substitute] {} gate(s) running real implementations: {}",
                      names.len(), names.join(", "));
            Some(pool)
        }
        None => None,
    };

    // Pre-resolve service models and outgoing-synapse index
    let services: Vec<(ServiceSource, Option<LogNormal>)> = topo
        .gates
        .iter()
        .map(|g| {
            if subs.as_ref().map_or(false, |p| p.is_substituted(&g.name)) {
                (ServiceSource::Substituted, None)
            } else {
                service_model(g, lib.as_ref())
            }
        })
        .collect();
    let mut routes_out: HashMap<String, Vec<usize>> = HashMap::new();
    for (i, s) in topo.synapses.iter().enumerate() {
        routes_out.entry(s.from.clone()).or_default().push(i);
    }

    // Accumulate per-gate fire times across all runs
    let mut gate_times: HashMap<String, Vec<f64>> = HashMap::new();
    let mut gate_miss:  HashMap<String, usize>    = HashMap::new();

    for run_idx in 0..cfg.runs {
        let result = run_once(&topo, &mut rng, lib.as_ref(), &services, &routes_out, &mut subs, run_idx)?;
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
        service:   ServiceSource,
    }

    let mut rows: Vec<Row> = topo
        .gates
        .iter()
        .enumerate()
        .filter(|(_, g)| g.name != "flow_sink" && !g.name.starts_with("__"))
        .map(|(i, gate)| {
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
            Row { name: gate.name.clone(), p50, p95, p99, mean, fire_pct, service: services[i].0 }
        })
        .collect();

    // Sort by p99 desc
    rows.sort_by(|a, b| b.p99.partial_cmp(&a.p99).unwrap_or(std::cmp::Ordering::Equal));

    // ── Report ──────────────────────────────────────────────────────────────────

    println!("\nTwin — {flow_name} — {} run(s)\n", cfg.runs);
    println!("{:<42} {:>8} {:>8} {:>8} {:>8} {:>7}  {}",
        "Gate", "p50 ms", "p95 ms", "p99 ms", "mean ms", "fire%", "service");
    println!("{}", "─".repeat(100));

    let mut bottleneck_name = String::new();
    let mut bottleneck_p99  = 0.0f64;

    for r in &rows {
        let svc = service_source_str(r.service);
        println!("{:<42} {:>8.0} {:>8.0} {:>8.0} {:>8.0} {:>6.1}%  {}",
            r.name, r.p50, r.p95, r.p99, r.mean, r.fire_pct, svc);
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

    // ── Machine-readable report (twin_report.json) ─────────────────────────────
    if let Some(report_path) = &cfg.report_path {
        let gates_json: serde_json::Map<String, Value> = rows
            .iter()
            .map(|r| {
                (r.name.clone(), json!({
                    "fire_pct": r.fire_pct,
                    "p50_ms": r.p50,
                    "p95_ms": r.p95,
                    "p99_ms": r.p99,
                    "mean_ms": r.mean,
                    "service_source": service_source_str(r.service),
                }))
            })
            .collect();
        let report = json!({
            "flow": flow_name,
            "runs": cfg.runs,
            "seed": cfg.seed,
            "latencies": cfg.latencies_path.as_ref().map(|p| p.display().to_string()),
            "substituted_gates": subs.as_ref().map(|p| p.gate_names()).unwrap_or_default(),
            "bottleneck": if bottleneck_name.is_empty() { Value::Null }
                          else { json!({"gate": bottleneck_name, "p99_ms": bottleneck_p99}) },
            "dead_gates": dead,
            "e2e_p99_ms": e2e_p99,
            "gates": Value::Object(gates_json),
        });
        std::fs::write(report_path, serde_json::to_string_pretty(&report)?)
            .with_context(|| format!("writing report {:?}", report_path))?;
        eprintln!("[report] wrote {:?}", report_path);
    }

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
    spec_path:          PathBuf,
    runs:               usize,
    seed:               Option<u64>,
    diagnose_dir:       Option<PathBuf>,
    latencies_path:     Option<PathBuf>,
    report_path:        Option<PathBuf>,
    substitutions_path: Option<PathBuf>,
}

impl Config {
    fn parse(args: &[String]) -> Result<Self> {
        let mut spec_path      = None;
        let mut runs           = 1000usize;
        let mut seed           = None;
        let mut diagnose_dir   = None;
        let mut latencies_path = None;
        let mut report_path    = None;

        let mut substitutions_path = None;
        let mut i = 1;
        while i < args.len() {
            match args[i].as_str() {
                "--spec"          => { spec_path          = Some(PathBuf::from(&args[i + 1])); i += 2; }
                "--runs"          => { runs               = args[i + 1].parse().context("--runs must be a positive integer")?; i += 2; }
                "--seed"          => { seed               = Some(args[i + 1].parse().context("--seed must be an integer")?); i += 2; }
                "--diagnose"      => { diagnose_dir       = Some(PathBuf::from(&args[i + 1])); i += 2; }
                "--latencies"     => { latencies_path     = Some(PathBuf::from(&args[i + 1])); i += 2; }
                "--report"        => { report_path        = Some(PathBuf::from(&args[i + 1])); i += 2; }
                "--substitutions" => { substitutions_path = Some(PathBuf::from(&args[i + 1])); i += 2; }
                other             => anyhow::bail!("unknown argument: {other}"),
            }
        }

        let spec_path = spec_path.context("--spec <flow.json> is required")?;
        Ok(Config { spec_path, runs, seed, diagnose_dir, latencies_path, report_path, substitutions_path })
    }
}
