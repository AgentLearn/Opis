/// Reader/writer for `gates_glossary.md`.
///
/// Format:
/// ```markdown
/// # Gates Glossary
///
/// ## <gate-name>
/// operation: <one-line description>
/// inputs: [flow-a, flow-b]
/// outputs: [flow-c]
/// archetype: TransactionCoordination
/// added: 2026-06-28
/// ```
use anyhow::Result;
use std::{
    io::Write as _,
    path::{Path, PathBuf},
};

#[derive(Debug, Clone)]
pub struct GlossaryEntry {
    pub name: String,
    pub operation: String,
    pub inputs: Vec<String>,
    pub outputs: Vec<String>,
    pub archetype: String,
    pub added: String,
}

pub struct Glossary {
    path: PathBuf,
    pub entries: Vec<GlossaryEntry>,
}

impl Glossary {
    pub fn load(path: &Path) -> Result<Self> {
        let raw = std::fs::read_to_string(path).unwrap_or_default();
        let entries = parse(&raw);
        Ok(Self { path: path.to_path_buf(), entries })
    }

    /// Append a new entry (no-op if name already exists).
    pub fn add(&mut self, entry: GlossaryEntry) -> bool {
        if self.entries.iter().any(|e| e.name == entry.name) {
            return false;
        }
        self.entries.push(entry);
        true
    }

    /// Persist the whole glossary back to disk.
    pub fn save(&self) -> Result<()> {
        let mut f = std::fs::OpenOptions::new()
            .create(true)
            .write(true)
            .truncate(true)
            .open(&self.path)?;

        writeln!(f, "# Gates Glossary")?;
        for e in &self.entries {
            writeln!(f)?;
            writeln!(f, "## {}", e.name)?;
            writeln!(f, "operation: {}", e.operation)?;
            writeln!(f, "inputs: [{}]", e.inputs.join(", "))?;
            writeln!(f, "outputs: [{}]", e.outputs.join(", "))?;
            writeln!(f, "archetype: {}", e.archetype)?;
            writeln!(f, "added: {}", e.added)?;
        }
        Ok(())
    }

    /// Render as a compact string suitable for inclusion in a prompt.
    pub fn to_prompt_context(&self) -> String {
        let mut out = String::from("Gates Glossary:\n");
        for e in &self.entries {
            out.push_str(&format!(
                "- {} ({}): {} | in: {:?} | out: {:?}\n",
                e.name, e.archetype, e.operation, e.inputs, e.outputs
            ));
        }
        out
    }
}

// ── Parser ────────────────────────────────────────────────────────────────────

fn parse(raw: &str) -> Vec<GlossaryEntry> {
    let mut entries = vec![];
    let mut current: Option<GlossaryEntry> = None;

    for line in raw.lines() {
        let line = line.trim();

        if let Some(name) = line.strip_prefix("## ") {
            if let Some(e) = current.take() {
                entries.push(e);
            }
            current = Some(GlossaryEntry {
                name: name.trim().to_string(),
                operation: String::new(),
                inputs: vec![],
                outputs: vec![],
                archetype: String::new(),
                added: String::new(),
            });
            continue;
        }

        if let Some(ref mut e) = current {
            if let Some(v) = line.strip_prefix("operation:") {
                e.operation = v.trim().to_string();
            } else if let Some(v) = line.strip_prefix("inputs:") {
                e.inputs = parse_list(v);
            } else if let Some(v) = line.strip_prefix("outputs:") {
                e.outputs = parse_list(v);
            } else if let Some(v) = line.strip_prefix("archetype:") {
                e.archetype = v.trim().to_string();
            } else if let Some(v) = line.strip_prefix("added:") {
                e.added = v.trim().to_string();
            }
        }
    }

    if let Some(e) = current {
        entries.push(e);
    }

    entries
}

fn parse_list(s: &str) -> Vec<String> {
    s.trim()
        .trim_start_matches('[')
        .trim_end_matches(']')
        .split(',')
        .map(|x| x.trim().to_string())
        .filter(|x| !x.is_empty())
        .collect()
}
