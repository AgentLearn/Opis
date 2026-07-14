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
    /// FA-derived flow frontmatter (2026-07-14): names the pulse-BODY field
    /// that identifies the domain object this gate's windows are keyed by.
    /// None = keyless gate (single shared queue per input type).
    entity_key: Option<String>,
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
                entity_key: gv.get("entity_key").and_then(|x| x.as_str()).map(String::from),
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

// ── Simulation: multi-admission engine ─────────────────────────────────────────
//
// 2026-07-14 (strategy.md "MULTI-ADMISSION TWIN — DESIGN CLOSED"). Replaces
// the single-admission engine (earliest arrival per (gate, type), fire ≤1×
// per run) with WINDOWED FIFO PER ENTITY KEY:
//
//   - every delivery is a PULSE with identity (id, parents, stimuli, key);
//     pulses queue per (gate, concrete type), ordered by (arrival, id);
//   - the entity key is extracted from the pulse BODY via the TARGET gate's
//     `entity_key` field (FA-derived flow frontmatter); bodiless or keyless
//     pulses share key None — a keyless gate is the None-key special case;
//   - a gate fires once per COMPLETE same-key window: one pulse per required
//     input (earliest matching, subtype-aware), all sharing the key; complete
//     windows drain in ascending (join_time, key) order; a retry (same type,
//     same key, again) = a second window = a second firing — the guard's
//     refusal path;
//   - N=1 reduction: with ≤1 arrival per requirement, the RNG draw sequence
//     (service → outcome → per-synapse hops, in topo-pass order) is identical
//     to the single-admission engine, so seeded reports reproduce
//     byte-identically — verified by the regress "Twin reduction" section;
//     divergence on flows with same-type fan-in is a SURFACED FINDING, never
//     silently absorbed;
//   - causal ledger (--ledger <path>, JSONL): one record per pulse (parents,
//     stimuli) and per firing (consumed → emitted); dynamic scenario claims
//     become a DAG filter by entity key. twin_report.json is UNCHANGED.

/// Per-gate-per-run firing cap: cycle containment. A flow cycle that
/// regenerates its own inputs would otherwise fire forever. Loud on trip.
const FIRE_CAP: u64 = 10_000;

#[derive(Debug, Clone)]
pub struct Pulse {
    id: u64,
    arrival: f64,
    body: Option<Value>,
    parents: Vec<u64>,   // consumed pulse ids of the firing that emitted this
    stimuli: Vec<u64>,   // root pulse ids this pulse descends from
    key: Option<String>, // entity key, per the TARGET gate's entity_key field
}

/// Causal ledger — append-only JSONL, one record per pulse delivery and per
/// gate firing. Pulse/firing ids are per-run (records carry `run`).
pub struct Ledger {
    out: std::io::BufWriter<std::fs::File>,
}

impl Ledger {
    fn open(path: &PathBuf) -> Result<Self> {
        let f = std::fs::File::create(path)
            .with_context(|| format!("creating ledger {:?}", path))?;
        Ok(Ledger { out: std::io::BufWriter::new(f) })
    }
    fn pulse(&mut self, run: usize, to_gate: &str, pulse_type: &str, p: &Pulse) -> Result<()> {
        use std::io::Write;
        writeln!(self.out, "{}", json!({
            "kind": "pulse", "run": run, "id": p.id, "type": pulse_type,
            "to": to_gate, "arrival_ms": p.arrival, "parents": p.parents,
            "stimuli": p.stimuli, "key": p.key,
        }))?;
        Ok(())
    }
    #[allow(clippy::too_many_arguments)]
    fn firing(&mut self, run: usize, firing_id: u64, gate: &str, key: &Option<String>,
              t: f64, consumed: &[u64], outcome: Option<&str>, emitted: &[u64]) -> Result<()> {
        use std::io::Write;
        writeln!(self.out, "{}", json!({
            "kind": "firing", "run": run, "id": firing_id, "gate": gate,
            "key": key, "fire_ms": t, "consumed": consumed,
            "outcome": outcome, "emitted": emitted,
        }))?;
        Ok(())
    }
    fn flush(&mut self) -> Result<()> {
        use std::io::Write;
        self.out.flush()?;
        Ok(())
    }
}

/// Entity key extraction: `field` names a body field; string/number/bool
/// coerce to string. Missing body, missing field, or other value → None.
fn extract_key(body: Option<&Value>, field: Option<&str>) -> Option<String> {
    match (body, field) {
        (Some(b), Some(f)) => match b.get(f) {
            Some(Value::String(s)) => Some(s.clone()),
            Some(Value::Number(n)) => Some(n.to_string()),
            Some(Value::Bool(x)) => Some(x.to_string()),
            _ => None,
        },
        _ => None,
    }
}

/// queues[gate][concrete pulse_type] = pulses sorted by (arrival, id)
type Queues = HashMap<String, HashMap<String, Vec<Pulse>>>;

/// Deliver one pulse across a synapse: sample the hop, apply wire tamper,
/// assign identity, extract the target gate's entity key, insert in
/// (arrival, id) order. Returns the new pulse id.
#[allow(clippy::too_many_arguments)]
fn deliver(
    queues: &mut Queues,
    syn: &Synapse,
    t_send: f64,
    body: Option<&Value>,
    parents: &[u64],
    stimuli: &[u64],
    entity_key_field: Option<&str>,
    next_pulse: &mut u64,
    lib: Option<&LatencyLib>,
    rng: &mut StdRng,
    tamper_sigs: bool,
    ledger: &mut Option<Ledger>,
    run_idx: usize,
) -> Result<u64> {
    let hop = match (lib, &syn.medium) {
        (Some(l), Some(m)) => l.media.get(m).map_or(0.0, |d| d.sample(rng)),
        _ => 0.0,
    };
    let mut stored = body.cloned();
    // forge-on-the-wire: every signature crossing a synapse is corrupted —
    // real verifiers downstream must visibly reject
    if tamper_sigs {
        if let Some(Value::Object(map)) = stored.as_mut() {
            if map.contains_key("sig") {
                map.insert("sig".into(), Value::String("f0f0f0f0deadbeef".into()));
            }
        }
    }
    *next_pulse += 1;
    let id = *next_pulse;
    // A root pulse (source-locus injection) is its own stimulus.
    let stimuli: Vec<u64> = if stimuli.is_empty() { vec![id] } else { stimuli.to_vec() };
    let p = Pulse {
        id,
        arrival: t_send + hop,
        key: extract_key(stored.as_ref(), entity_key_field),
        body: stored,
        parents: parents.to_vec(),
        stimuli,
    };
    if let Some(l) = ledger.as_mut() {
        l.pulse(run_idx, &syn.to, &syn.pulse_type, &p)?;
    }
    let q = queues
        .entry(syn.to.clone())
        .or_default()
        .entry(syn.pulse_type.clone())
        .or_default();
    let pos = q.partition_point(|x| (x.arrival, x.id) <= (p.arrival, p.id));
    q.insert(pos, p);
    Ok(id)
}

/// Find the EARLIEST complete window for `gate`: per required input, the
/// earliest queued pulse (subtype-aware) sharing one entity key. Deterministic
/// across HashMap orders: all selections are min-folds tie-broken on
/// (arrival, pulse id), and the winning window is min over (join, key).
/// Returns (key, join_time, consumed pulse ids).
fn find_window(
    topo: &Topology,
    gate: &GateModel,
    queues: &Queues,
) -> Option<(Option<String>, f64, Vec<u64>)> {
    let qmap = queues.get(&gate.name)?;
    // Candidate keys: distinct keys among pulses of requirement-matching types.
    let mut keys: std::collections::BTreeSet<Option<String>> = Default::default();
    for (t, q) in qmap {
        if gate.requires.iter().any(|r| topo.matches(t, r)) {
            for p in q {
                keys.insert(p.key.clone());
            }
        }
    }
    let mut best: Option<(f64, Option<String>, Vec<u64>)> = None;
    for key in keys {
        // Per requirement: earliest matching pulse carrying this key.
        let mut per_req: Vec<Option<(f64, u64)>> = Vec::with_capacity(gate.requires.len());
        for req in &gate.requires {
            let mut found: Option<(f64, u64)> = None;
            for (t, q) in qmap {
                if !topo.matches(t, req) {
                    continue;
                }
                if let Some(p) = q.iter().find(|p| p.key == key) {
                    let cand = (p.arrival, p.id);
                    if found.map_or(true, |f| cand < f) {
                        found = Some(cand);
                    }
                }
            }
            per_req.push(found);
        }
        let mut present: Vec<(f64, u64)> = per_req.iter().filter_map(|x| *x).collect();
        present.sort_by(|a, b| a.partial_cmp(b).unwrap());
        // One pulse may satisfy two requirements (subtype fan-in) — consume
        // it once (dedup) but count it per requirement, as the static prover
        // and the old engine both did.
        let window: Option<(f64, Vec<u64>)> = match gate.logic_op {
            LogicOp::And => {
                if present.len() == gate.requires.len() {
                    let join = present.last().unwrap().0;
                    let mut ids: Vec<u64> = present.iter().map(|x| x.1).collect();
                    ids.sort_unstable();
                    ids.dedup();
                    Some((join, ids))
                } else {
                    None
                }
            }
            LogicOp::Or => present.first().map(|&(t, id)| (t, vec![id])),
            LogicOp::Threshold(n) => {
                if present.len() >= n {
                    let join = present[n - 1].0;
                    let mut ids: Vec<u64> = present[..n].iter().map(|x| x.1).collect();
                    ids.sort_unstable();
                    ids.dedup();
                    Some((join, ids))
                } else {
                    None
                }
            }
        };
        if let Some((join, ids)) = window {
            let better = match &best {
                None => true,
                Some((bj, bk, _)) => join < *bj || (join == *bj && key < *bk),
            };
            if better {
                best = Some((join, key, ids));
            }
        }
    }
    best.map(|(j, k, ids)| (k, j, ids))
}

/// Run one Monte Carlo pass through the topology.
/// Returns: gate_name → firing times (empty/absent = did not fire this run).
#[allow(clippy::too_many_arguments)]
fn run_once(
    topo: &Topology,
    rng: &mut StdRng,
    lib: Option<&LatencyLib>,
    services: &[(ServiceSource, Option<LogNormal>)],
    routes_out: &HashMap<String, Vec<usize>>, // from-node → synapse indices
    entity_key_of: &HashMap<String, String>,  // gate → its entity_key body field
    subs: &mut Option<substitute::SubPool>,   // co-sim: real gate implementations
    provider: &mut Option<substitute::BodyProvider>, // CA payload generator
    run_idx: usize,
    // per-gate outcome tally across runs — fire% alone is blind to a gate
    // that fires identically but DECIDES differently (tamper runs, 2026-07-06)
    outcome_counts: &mut HashMap<String, HashMap<String, u64>>,
    tamper_sigs: bool,
    ledger: &mut Option<Ledger>,
) -> Result<HashMap<String, Vec<f64>>> {
    let mut queues: Queues = HashMap::new();
    let mut next_pulse: u64 = 0;
    let mut next_firing: u64 = 0;

    // Inject from source loci at t = 0 (root pulses: their own stimuli)
    for locus in &topo.source_loci {
        if let Some(idxs) = routes_out.get(locus) {
            for &i in idxs {
                let key_field = entity_key_of.get(&topo.synapses[i].to).map(|s| s.as_str());
                deliver(&mut queues, &topo.synapses[i], 0.0, None, &[], &[], key_field,
                        &mut next_pulse, lib, rng, tamper_sigs, ledger, run_idx)?;
            }
        }
    }

    let mut firings: HashMap<String, Vec<f64>> = HashMap::new();
    let mut fire_count: Vec<u64> = vec![0; topo.gates.len()];

    // Iterate to a fixed point: a single topological pass starves gates inside
    // requires-cycles. Each pass, every gate drains ALL its complete windows;
    // extra passes only matter while new pulses propagate around cycles.
    let mut passes = 0;
    loop {
        let mut newly_fired = false;
        passes += 1;

        for &idx in &topo.topo_order {
            let gate = &topo.gates[idx];

            loop {
                // Autonomous gates (no required inputs) fire exactly once per
                // run at t=0 — unchanged from the single-admission engine.
                let win: Option<(Option<String>, f64, Vec<u64>)> = if gate.requires.is_empty() {
                    if fire_count[idx] == 0 { Some((None, 0.0, vec![])) } else { None }
                } else {
                    find_window(topo, gate, &queues)
                };
                let Some((key, join_time, consumed_ids)) = win else { break };

                if fire_count[idx] >= FIRE_CAP {
                    eprintln!(
                        "[twin] LOUD: gate '{}' hit FIRE_CAP={} in run {} — \
                         self-regenerating cycle? containment engaged, windows dropped",
                        gate.name, FIRE_CAP, run_idx
                    );
                    break;
                }

                // Consume the window's pulses (clone out, remove from queues).
                let mut consumed: Vec<(String, Pulse)> = Vec::new();
                if let Some(qm) = queues.get_mut(&gate.name) {
                    for (t, q) in qm.iter_mut() {
                        let mut i = 0;
                        while i < q.len() {
                            if consumed_ids.contains(&q[i].id) {
                                consumed.push((t.clone(), q.remove(i)));
                            } else {
                                i += 1;
                            }
                        }
                    }
                }
                consumed.sort_by(|a, b| {
                    (a.1.arrival, a.1.id).partial_cmp(&(b.1.arrival, b.1.id)).unwrap()
                });

                fire_count[idx] += 1;
                next_firing += 1;
                newly_fired = true;

                let parent_ids: Vec<u64> = consumed.iter().map(|(_, p)| p.id).collect();
                let mut stimuli: Vec<u64> =
                    consumed.iter().flat_map(|(_, p)| p.stimuli.clone()).collect();
                stimuli.sort_unstable();
                stimuli.dedup();

                // ── Substituted gate: real decision logic replaces both the
                //    service sample AND the outcome draw ─────────────────────
                let substituted = subs.as_ref().map_or(false, |p| p.is_substituted(&gate.name));
                if substituted {
                    let mut inputs: Vec<substitute::InputPulse> = Vec::new();
                    for (t, p) in &consumed {
                        // Real body if the upstream was substituted; otherwise
                        // ask CA's body provider to synthesize one.
                        let body = match (&p.body, provider.as_mut()) {
                            (Some(b), _) => b.clone(),
                            (None, Some(pr)) => pr.body_for(run_idx, t, p.arrival, &gate.name)?,
                            (None, None) => Value::Null,
                        };
                        inputs.push(substitute::InputPulse {
                            pulse_type: t.clone(),
                            arrival_ms: p.arrival,
                            body,
                        });
                    }

                    let resp = subs
                        .as_mut()
                        .unwrap()
                        .call(&gate.name, run_idx, join_time, &inputs)?;

                    let fire_time = join_time + resp.service_ms;
                    firings.entry(gate.name.clone()).or_default().push(fire_time);

                    let mut emitted_ids: Vec<u64> = Vec::new();
                    let mut outcome_label: Option<String> = None;
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
                        *outcome_counts
                            .entry(gate.name.clone())
                            .or_default()
                            .entry(outcome_name.to_string())
                            .or_insert(0) += 1;
                        outcome_label = Some(outcome_name.to_string());
                        // Contract check: actual outputs ⊆ chosen outcome's declared flows
                        for out in &resp.outputs {
                            if !chosen.flows.iter().any(|f| f == &out.pulse_type) {
                                anyhow::bail!(
                                    "substituted gate '{}' emitted '{}' not declared under outcome '{}' (flows: {:?})",
                                    gate.name, out.pulse_type, outcome_name, chosen.flows
                                );
                            }
                        }
                        // Propagate what the real code actually emitted (with
                        // its real body); if it returned no outputs, fall back
                        // to declared flows with no body.
                        let emitted: Vec<(&String, Option<&Value>)> = if resp.outputs.is_empty() {
                            chosen.flows.iter().map(|f| (f, None)).collect()
                        } else {
                            resp.outputs.iter().map(|o| (&o.pulse_type, Some(&o.body))).collect()
                        };
                        for (pulse_type, body) in emitted {
                            if let Some(idxs) = routes_out.get(&gate.name) {
                                for &i in idxs {
                                    if &topo.synapses[i].pulse_type == pulse_type {
                                        let key_field = entity_key_of
                                            .get(&topo.synapses[i].to)
                                            .map(|s| s.as_str());
                                        let pid = deliver(&mut queues, &topo.synapses[i], fire_time,
                                                          body, &parent_ids, &stimuli, key_field,
                                                          &mut next_pulse, lib, rng, tamper_sigs,
                                                          ledger, run_idx)?;
                                        emitted_ids.push(pid);
                                    }
                                }
                            }
                        }
                    }
                    if let Some(l) = ledger.as_mut() {
                        l.firing(run_idx, next_firing, &gate.name, &key, fire_time,
                                 &parent_ids, outcome_label.as_deref(), &emitted_ids)?;
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
                firings.entry(gate.name.clone()).or_default().push(fire_time);

                // Choose outcome (normalised weights → cumulative draw)
                if gate.outcomes.is_empty() {
                    if let Some(l) = ledger.as_mut() {
                        l.firing(run_idx, next_firing, &gate.name, &key, fire_time,
                                 &parent_ids, None, &[])?;
                    }
                    continue;
                }
                let r: f64 = rng.gen_range(0.0..1.0);
                let mut cum = 0.0;
                let chosen = gate.outcomes.iter().find(|o| {
                    cum += o.weight;
                    r < cum
                }).unwrap_or(&gate.outcomes[gate.outcomes.len() - 1]);
                *outcome_counts
                    .entry(gate.name.clone())
                    .or_default()
                    .entry(chosen.name.clone().unwrap_or_else(|| "_unnamed".into()))
                    .or_insert(0) += 1;

                // Propagate emitted pulses downstream (per-synapse medium latency)
                let mut emitted_ids: Vec<u64> = Vec::new();
                for pulse_type in &chosen.flows {
                    if let Some(idxs) = routes_out.get(&gate.name) {
                        for &i in idxs {
                            if &topo.synapses[i].pulse_type == pulse_type {
                                let key_field = entity_key_of
                                    .get(&topo.synapses[i].to)
                                    .map(|s| s.as_str());
                                let pid = deliver(&mut queues, &topo.synapses[i], fire_time, None,
                                                  &parent_ids, &stimuli, key_field, &mut next_pulse,
                                                  lib, rng, tamper_sigs, ledger, run_idx)?;
                                emitted_ids.push(pid);
                            }
                        }
                    }
                }
                if let Some(l) = ledger.as_mut() {
                    l.firing(run_idx, next_firing, &gate.name, &key, fire_time, &parent_ids,
                             chosen.name.as_deref(), &emitted_ids)?;
                }
            }
        }

        if !newly_fired || passes > topo.gates.len() {
            break;
        }
    }

    Ok(firings)
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
    let mut provider: Option<substitute::BodyProvider> = match &cfg.substitutions_path {
        Some(p) => {
            let bp = substitute::body_provider_from_manifest(p)?;
            if bp.is_some() {
                eprintln!("[substitute] body provider active");
            }
            bp
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
    // gate → its declared entity_key body field (multi-admission windows)
    let entity_key_of: HashMap<String, String> = topo
        .gates
        .iter()
        .filter_map(|g| g.entity_key.as_ref().map(|k| (g.name.clone(), k.clone())))
        .collect();
    if !entity_key_of.is_empty() {
        eprintln!("[twin] {} entity-keyed gate(s)", entity_key_of.len());
    }

    let mut ledger: Option<Ledger> = match &cfg.ledger_path {
        Some(p) => Some(Ledger::open(p)?),
        None => None,
    };

    // Accumulate per-gate fire times across all runs. A gate may fire more
    // than once per run (multi-admission); fire% counts runs with ≥1 firing.
    let mut gate_times: HashMap<String, Vec<f64>> = HashMap::new();
    let mut gate_runs_fired: HashMap<String, usize> = HashMap::new();
    let mut gate_miss:  HashMap<String, usize>    = HashMap::new();
    let mut outcome_counts: HashMap<String, HashMap<String, u64>> = HashMap::new();

    for run_idx in 0..cfg.runs {
        let result = run_once(&topo, &mut rng, lib.as_ref(), &services, &routes_out, &entity_key_of, &mut subs, &mut provider, run_idx, &mut outcome_counts, cfg.tamper_sigs, &mut ledger)?;
        for g in &topo.gates {
            match result.get(&g.name) {
                Some(v) if !v.is_empty() => {
                    gate_times.entry(g.name.clone()).or_default().extend_from_slice(v);
                    *gate_runs_fired.entry(g.name.clone()).or_default() += 1;
                }
                _ => *gate_miss.entry(g.name.clone()).or_default() += 1,
            }
        }
    }
    if let Some(l) = ledger.as_mut() {
        l.flush()?;
        eprintln!("[ledger] wrote {:?}", cfg.ledger_path.as_ref().unwrap());
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
            // runs with ≥1 firing — NOT total firings (multi-admission)
            let fired  = gate_runs_fired.get(&gate.name).copied().unwrap_or(0);
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
                let outcomes: serde_json::Map<String, Value> = outcome_counts
                    .get(&r.name)
                    .map(|m| {
                        m.iter()
                            .map(|(k, v)| (k.clone(), json!(v)))
                            .collect()
                    })
                    .unwrap_or_default();
                (r.name.clone(), json!({
                    "fire_pct": r.fire_pct,
                    "p50_ms": r.p50,
                    "p95_ms": r.p95,
                    "p99_ms": r.p99,
                    "mean_ms": r.mean,
                    "service_source": service_source_str(r.service),
                    // what the gate DECIDED, not just whether it fired —
                    // tamper comparisons diff these (2026-07-06)
                    "outcomes": Value::Object(outcomes),
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
    ledger_path:        Option<PathBuf>,  // causal ledger JSONL (2026-07-14)
    substitutions_path: Option<PathBuf>,
    // forge-on-the-wire (2026-07-06): corrupt every `sig` field as bodies
    // cross synapses. Provider-side tampering can't forge against a REAL
    // substituted sentinel chain (it signs valid tokens with the real
    // secret in both runs) — the attacker must live on the wire.
    tamper_sigs:        bool,
}

impl Config {
    fn parse(args: &[String]) -> Result<Self> {
        let mut spec_path      = None;
        let mut runs           = 1000usize;
        let mut seed           = None;
        let mut diagnose_dir   = None;
        let mut latencies_path = None;
        let mut report_path    = None;
        let mut ledger_path    = None;

        let mut substitutions_path = None;
        let mut tamper_sigs = false;
        let mut i = 1;
        while i < args.len() {
            match args[i].as_str() {
                "--spec"          => { spec_path          = Some(PathBuf::from(&args[i + 1])); i += 2; }
                "--runs"          => { runs               = args[i + 1].parse().context("--runs must be a positive integer")?; i += 2; }
                "--seed"          => { seed               = Some(args[i + 1].parse().context("--seed must be an integer")?); i += 2; }
                "--diagnose"      => { diagnose_dir       = Some(PathBuf::from(&args[i + 1])); i += 2; }
                "--latencies"     => { latencies_path     = Some(PathBuf::from(&args[i + 1])); i += 2; }
                "--report"        => { report_path        = Some(PathBuf::from(&args[i + 1])); i += 2; }
                "--ledger"        => { ledger_path        = Some(PathBuf::from(&args[i + 1])); i += 2; }
                "--substitutions" => { substitutions_path = Some(PathBuf::from(&args[i + 1])); i += 2; }
                "--tamper-sigs"   => { tamper_sigs        = true; i += 1; }
                other             => anyhow::bail!("unknown argument: {other}"),
            }
        }

        let spec_path = spec_path.context("--spec <flow.json> is required")?;
        Ok(Config { spec_path, runs, seed, diagnose_dir, latencies_path, report_path, ledger_path, substitutions_path, tamper_sigs })
    }
}
