/// Append-only diary writers for GA and FA.
use std::fmt::Write as FmtWrite;
use std::path::{Path, PathBuf};

pub struct GaDiary {
    path: PathBuf,
}

impl GaDiary {
    pub fn new(gates_dir: &Path, gate_name: &str) -> Self {
        let path = gates_dir.join(gate_name).join("diary.md");
        std::fs::create_dir_all(path.parent().unwrap()).ok();
        Self { path }
    }

    pub fn write_attempt(
        &self,
        attempt: u32,
        prompt_summary: &str,
        kata_context: &str,
        result: &str,
        detail: &str,
    ) {
        let mut entry = String::new();
        writeln!(entry, "\n## Attempt {attempt}").ok();
        writeln!(entry, "model: {prompt_summary}").ok();
        writeln!(entry, "kata_context: |").ok();
        for line in kata_context.lines() {
            writeln!(entry, "  {line}").ok();
        }
        writeln!(entry, "result: {result}").ok();
        writeln!(entry, "detail: {detail}").ok();
        self.append(&entry);
    }

    pub fn write_outcome(&self, status: &str, spec_file: Option<&str>) {
        let mut entry = String::new();
        writeln!(entry, "\n## Outcome").ok();
        writeln!(entry, "status: {status}").ok();
        if let Some(sf) = spec_file {
            writeln!(entry, "spec_file: {sf}").ok();
        }
        self.append(&entry);
    }

    fn append(&self, text: &str) {
        use std::io::Write;
        let mut f = std::fs::OpenOptions::new()
            .create(true).append(true).open(&self.path).unwrap();
        f.write_all(text.as_bytes()).ok();
    }
}

pub struct FaDiary {
    path: PathBuf,
}

impl FaDiary {
    pub fn new(flows_dir: &Path, flow_name: &str) -> Self {
        let path = flows_dir.join(flow_name).join("diary.md");
        std::fs::create_dir_all(path.parent().unwrap()).ok();
        Self { path }
    }

    pub fn write_initial_pass(&self, gates: &[String], missing: &[String]) {
        let mut entry = String::new();
        writeln!(entry, "\n## Initial Pass").ok();
        writeln!(entry, "gates_attempted: {:?}", gates).ok();
        writeln!(entry, "missing_flows: {:?}", missing).ok();
        self.append(&entry);
    }

    pub fn write_repair_cycle(
        &self,
        iteration: u32,
        gaps_in: &[String],
        synthesized: &[(String, String)],
        discarded: &[(String, String)],
        gaps_out: &[String],
        reexpanded: &[String],
    ) {
        let mut entry = String::new();
        writeln!(entry, "\n## Repair Cycle {iteration}").ok();
        writeln!(entry, "gaps_in: {:?}", gaps_in).ok();
        writeln!(entry, "synthesized:").ok();
        for (flow, rationale) in synthesized {
            writeln!(entry, "  - flow: {flow}\n    rationale: {rationale}").ok();
        }
        writeln!(entry, "discarded:").ok();
        for (flow, reason) in discarded {
            writeln!(entry, "  - flow: {flow}\n    reason: {reason}").ok();
        }
        writeln!(entry, "gaps_out: {:?}", gaps_out).ok();
        writeln!(entry, "gates_reexpanded: {:?}", reexpanded).ok();
        self.append(&entry);
    }

    pub fn write_outcome(&self, status: &str, kata_gaps: &[(String, Vec<String>, String)]) {
        let mut entry = String::new();
        writeln!(entry, "\n## Outcome").ok();
        writeln!(entry, "status: {status}").ok();
        if !kata_gaps.is_empty() {
            writeln!(entry, "kata_gaps:").ok();
            for (flow, needed_by, hypothesis) in kata_gaps {
                writeln!(entry, "  - flow: {flow}").ok();
                writeln!(entry, "    needed_by: {:?}", needed_by).ok();
                writeln!(entry, "    hypothesis: {hypothesis}").ok();
            }
        }
        self.append(&entry);
    }

    fn append(&self, text: &str) {
        use std::io::Write;
        let mut f = std::fs::OpenOptions::new()
            .create(true).append(true).open(&self.path).unwrap();
        f.write_all(text.as_bytes()).ok();
    }
}
