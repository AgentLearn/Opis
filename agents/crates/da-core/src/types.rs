use serde::{Deserialize, Serialize};

// ── Names ────────────────────────────────────────────────────────────────────

pub type FlowName = String;
pub type GateName = String;

// ── Gate primitives ───────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum GateArchetype {
    TransactionCoordination,
    StorageScaling,
    EventRouting,
    RateLimiting,
    Custom(String),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum Cardinality {
    OneToOne,
    OneToMany,
    ManyToOne,
    ManyToMany,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum Persistence {
    None,
    Ephemeral,
    Durable,
    Replicated,
}

// ── Flow graph ────────────────────────────────────────────────────────────────

/// A directed pulse edge between two gates.
/// Produced by the FA kata parser and stored in flows/<name>/graph.json.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct FlowEdge {
    pub from: GateName,
    pub pulse_type: FlowName,
    pub to: GateName,
}

// ── Gate request / response ───────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GateRequest {
    pub name: GateName,
    pub archetype: GateArchetype,
    pub cardinality: Cardinality,
    pub persistence: Persistence,
    /// Prose from the kata, forwarded to the model as context.
    pub context: String,
    /// Pulse types this gate MUST accept (from upstream gates in the flow graph).
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub upstream: Vec<FlowEdge>,
    /// Pulse types this gate MUST emit (to downstream gates in the flow graph).
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub downstream: Vec<FlowEdge>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GateSpec {
    pub name: GateName,
    pub description: String,
    pub inputs: Vec<FlowName>,
    pub outputs: Vec<FlowName>,
    pub constraints: Vec<String>,
    /// Archetype string stored at write time so downstream tools (composer, diagram,
    /// twin) don't need to re-read the glossary.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub archetype: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GateResponse {
    pub name: GateName,
    pub spec: GateSpec,
    pub warnings: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum GateError {
    MissingInput(FlowName),
    Exhausted { reason: String },
}

// ── Repair types ──────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SynthesisResult {
    pub flow: FlowName,
    pub rationale: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DiscardedFlow {
    pub flow: FlowName,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RepairAttempt {
    pub iteration: u32,
    pub gaps_in: Vec<FlowName>,
    pub synthesized: Vec<SynthesisResult>,
    pub discarded: Vec<DiscardedFlow>,
    pub gaps_out: Vec<FlowName>,
    pub gates_reexpanded: Vec<GateName>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KataGap {
    pub flow: FlowName,
    pub needed_by: Vec<GateName>,
    /// FA's best guess at what the kata author omitted.
    pub fa_hypothesis: String,
}

// ── Flow-level error ──────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum FlowError {
    KataIncomplete {
        missing: Vec<FlowName>,
        repair_attempts: Vec<RepairAttempt>,
        kata_gaps: Vec<KataGap>,
    },
}

impl std::fmt::Display for GateArchetype {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            GateArchetype::TransactionCoordination => write!(f, "TransactionCoordination"),
            GateArchetype::StorageScaling          => write!(f, "StorageScaling"),
            GateArchetype::EventRouting            => write!(f, "EventRouting"),
            GateArchetype::RateLimiting            => write!(f, "RateLimiting"),
            GateArchetype::Custom(s)               => write!(f, "Custom({s})"),
        }
    }
}

impl std::fmt::Display for FlowError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            FlowError::KataIncomplete { missing, kata_gaps, .. } => {
                writeln!(f, "Kata incomplete. Missing flows: {:?}", missing)?;
                for gap in kata_gaps {
                    writeln!(
                        f,
                        "  - '{}' (needed by {:?}): {}",
                        gap.flow, gap.needed_by, gap.fa_hypothesis
                    )?;
                }
                Ok(())
            }
        }
    }
}

impl std::error::Error for FlowError {}
