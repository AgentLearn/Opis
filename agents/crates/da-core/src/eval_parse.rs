/// Parse opis-eval text output into structured findings.
///
/// opis-eval emits lines like:
///   ⚠ gate 'delivery-dispatch': no sentinel/regulator — unprotected gate
///   ✗ gate 'order-routing': pulse type 'x' unreachable
///   ✓ all gate requires are reachable
use std::fmt;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Severity {
    Error,
    Warning,
}

impl fmt::Display for Severity {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Severity::Error   => write!(f, "error"),
            Severity::Warning => write!(f, "warning"),
        }
    }
}

#[derive(Debug, Clone)]
pub struct EvalFinding {
    pub check:    u32,
    pub severity: Severity,
    pub gate:     Option<String>,
    pub message:  String,
}

impl fmt::Display for EvalFinding {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let gate_part = self.gate.as_deref().map(|g| format!(" gate '{g}'")).unwrap_or_default();
        write!(f, "check {}{}: {}", self.check, gate_part, self.message)
    }
}

/// Parse opis-eval stdout into a list of findings.
/// Only warnings and errors are returned (passes are ignored).
pub fn parse_eval_output(text: &str) -> Vec<EvalFinding> {
    let mut findings = Vec::new();
    let mut current_check: u32 = 0;

    for line in text.lines() {
        let trimmed = line.trim();

        // Section header: "5. Sentinel / regulator coverage"
        if let Some(dot_pos) = trimmed.find(". ") {
            let prefix = &trimmed[..dot_pos];
            if prefix.chars().all(|c| c.is_ascii_digit()) {
                current_check = prefix.parse().unwrap_or(current_check);
                continue;
            }
        }

        // Warning: ⚠ ...
        // Error:   ✗ ...  (opis-eval may use ✗ or × or similar — check for non-✓ marker)
        let (severity, rest) = if let Some(r) = trimmed.strip_prefix("⚠") {
            (Severity::Warning, r.trim())
        } else if trimmed.starts_with("✗") || trimmed.starts_with("×") {
            let r = &trimmed[trimmed.char_indices().nth(1).map(|(i,_)| i).unwrap_or(1)..];
            (Severity::Error, r.trim())
        } else {
            continue; // pass line or non-finding
        };

        // Try to extract gate name: `gate 'name': message`
        let (gate, message) = if let Some(after_gate) = rest.strip_prefix("gate '") {
            if let Some(end_quote) = after_gate.find('\'') {
                let name = after_gate[..end_quote].to_string();
                let msg = after_gate[end_quote + 1..].trim_start_matches(':').trim().to_string();
                (Some(name), msg)
            } else {
                (None, rest.to_string())
            }
        } else {
            (None, rest.to_string())
        };

        findings.push(EvalFinding { check: current_check, severity, gate, message });
    }

    findings
}

/// Return only findings that the FA repair loop should act on.
/// Currently: all errors + check-5 (sentinel coverage) warnings.
pub fn actionable(findings: &[EvalFinding]) -> Vec<&EvalFinding> {
    findings.iter().filter(|f| {
        f.severity == Severity::Error
            || (f.severity == Severity::Warning && f.check == 5)
    }).collect()
}
