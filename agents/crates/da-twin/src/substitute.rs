//! Gate substitution — the co-simulation boundary.
//!
//! A substituted gate is a real implementation running as a child process,
//! speaking line-delimited JSON over stdio (protocol v1). The twin keeps the
//! virtual clock: at fire time it sends the gate its arrived inputs, the real
//! decision logic runs, and the response carries the ACTUAL outcome (which
//! replaces the twin's sampled outcome draw), the output payloads, and the
//! measured service time (which replaces the sampled service distribution).
//!
//! Manifest format (`--substitutions subs.json`) — ephemeral CA artifact,
//! never checked in:
//!
//! ```json
//! { "gates": { "PaymentProcessor": { "cmd": ["target/release/payment_processor"] } } }
//! ```
//!
//! Request (one line):
//!   {"v":1,"run":17,"gate":"PaymentProcessor","t_ms":123.4,
//!    "inputs":[{"pulse_type":"sandwich_payment","arrival_ms":100.2,"body":null}]}
//!
//! Response (one line):
//!   {"outcome":"payment_confirmed","service_ms":2.1,
//!    "outputs":[{"pulse_type":"sandwich_payment_confirmed","body":{...}}]}
//!
//! Rules the twin enforces (protocol violations fail the whole twin run —
//! a misbehaving implementation is a defect, not noise to be smoothed over):
//!   - `outcome` must name one of the gate's declared outcomes.
//!   - every `outputs[].pulse_type` must be among that outcome's declared flows.
//!   - `service_ms` must be finite and ≥ 0.

use anyhow::{bail, Context, Result};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::io::{BufRead, BufReader, BufWriter, Write};
use std::path::Path;
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::time::Instant;

pub const PROTOCOL_VERSION: u32 = 1;

pub struct InputPulse {
    pub pulse_type: String,
    pub arrival_ms: f64,
    pub body: Value, // Null until payload generators (slice step 3) fill it
}

pub struct OutputPulse {
    pub pulse_type: String,
    #[allow(dead_code)] // carried for downstream substituted gates / generators
    pub body: Value,
}

pub struct SubResponse {
    pub outcome: Option<String>,
    pub service_ms: f64,
    pub outputs: Vec<OutputPulse>,
    /// Wall-clock round trip including IPC — recorded, never used for the
    /// virtual clock (service_ms, the gate's own measurement, drives that).
    pub roundtrip_ms: f64,
}

struct SubProc {
    child: Child,
    stdin: BufWriter<ChildStdin>,
    stdout: BufReader<ChildStdout>,
}

#[derive(Default)]
pub struct SubPool {
    procs: HashMap<String, SubProc>,
}

impl SubPool {
    /// Load the manifest and spawn one child per substituted gate.
    pub fn from_manifest(path: &Path) -> Result<Self> {
        let raw = std::fs::read_to_string(path)
            .with_context(|| format!("reading substitutions manifest {:?}", path))?;
        let v: Value = serde_json::from_str(&raw)
            .with_context(|| format!("parsing substitutions manifest {:?}", path))?;
        let gates = v
            .get("gates")
            .and_then(|g| g.as_object())
            .context("manifest missing 'gates' object")?;

        let mut pool = SubPool::default();
        for (gate, spec) in gates {
            let cmd: Vec<String> = spec
                .get("cmd")
                .and_then(|c| c.as_array())
                .map(|a| a.iter().filter_map(|x| x.as_str().map(String::from)).collect())
                .unwrap_or_default();
            if cmd.is_empty() {
                bail!("substitution for gate '{}' has empty 'cmd'", gate);
            }
            let mut child = Command::new(&cmd[0])
                .args(&cmd[1..])
                .stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .stderr(Stdio::inherit())
                .spawn()
                .with_context(|| format!("spawning substituted gate '{}' ({:?})", gate, cmd))?;
            let stdin = BufWriter::new(child.stdin.take().context("child stdin")?);
            let stdout = BufReader::new(child.stdout.take().context("child stdout")?);
            pool.procs.insert(gate.clone(), SubProc { child, stdin, stdout });
        }
        Ok(pool)
    }

    pub fn is_substituted(&self, gate: &str) -> bool {
        self.procs.contains_key(gate)
    }

    pub fn gate_names(&self) -> Vec<String> {
        self.procs.keys().cloned().collect()
    }

    /// One fire: send inputs at virtual time `t_ms`, get the real decision.
    pub fn call(
        &mut self,
        gate: &str,
        run: usize,
        t_ms: f64,
        inputs: &[InputPulse],
    ) -> Result<SubResponse> {
        let proc = self
            .procs
            .get_mut(gate)
            .with_context(|| format!("gate '{}' is not substituted", gate))?;

        let req = json!({
            "v": PROTOCOL_VERSION,
            "run": run,
            "gate": gate,
            "t_ms": t_ms,
            "inputs": inputs.iter().map(|i| json!({
                "pulse_type": i.pulse_type,
                "arrival_ms": i.arrival_ms,
                "body": i.body,
            })).collect::<Vec<_>>(),
        });

        let started = Instant::now();
        serde_json::to_writer(&mut proc.stdin, &req)?;
        proc.stdin.write_all(b"\n")?;
        proc.stdin.flush()?;

        let mut line = String::new();
        let n = proc
            .stdout
            .read_line(&mut line)
            .with_context(|| format!("reading response from substituted gate '{}'", gate))?;
        if n == 0 {
            bail!(
                "substituted gate '{}' closed its stdout (crashed?) at run {}",
                gate, run
            );
        }
        let roundtrip_ms = started.elapsed().as_secs_f64() * 1000.0;

        let resp: Value = serde_json::from_str(line.trim())
            .with_context(|| format!("parsing response from '{}': {}", gate, line.trim()))?;

        let service_ms = resp
            .get("service_ms")
            .and_then(|x| x.as_f64())
            .with_context(|| format!("substituted gate '{}': response missing service_ms", gate))?;
        if !service_ms.is_finite() || service_ms < 0.0 {
            bail!("substituted gate '{}': invalid service_ms {}", gate, service_ms);
        }

        let outcome = resp.get("outcome").and_then(|x| x.as_str()).map(String::from);
        let outputs = resp
            .get("outputs")
            .and_then(|o| o.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|ov| {
                        ov.get("pulse_type").and_then(|t| t.as_str()).map(|t| OutputPulse {
                            pulse_type: t.to_string(),
                            body: ov.get("body").cloned().unwrap_or(Value::Null),
                        })
                    })
                    .collect()
            })
            .unwrap_or_default();

        Ok(SubResponse { outcome, service_ms, outputs, roundtrip_ms })
    }
}

impl Drop for SubPool {
    fn drop(&mut self) {
        for (_, p) in self.procs.iter_mut() {
            let _ = p.child.kill();
            let _ = p.child.wait();
        }
    }
}
