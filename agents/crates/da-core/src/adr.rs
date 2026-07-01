/// ADR loader — reads Architecture Decision Records from a directory.
///
/// Each ADR is a markdown file with YAML front-matter:
///   ---
///   id: 001
///   title: Some Decision
///   status: active   # active | draft | superseded
///   date: 2026-06-29
///   ---
///   (body markdown)
///
/// Only `status: active` ADRs are loaded into FA/GA context.
/// Flip to `draft` or `superseded` to exclude from a run.
use std::path::{Path, PathBuf};

#[derive(Debug, Clone)]
pub struct Adr {
    pub id:     String,
    pub title:  String,
    pub status: String,
    pub date:   String,
    pub body:   String,
    pub path:   PathBuf,
}

impl Adr {
    /// Parse an ADR markdown file.
    pub fn load(path: &Path) -> Option<Self> {
        let raw = std::fs::read_to_string(path).ok()?;
        let raw = raw.trim();

        // Must start with front-matter delimiter
        if !raw.starts_with("---") {
            return None;
        }

        let rest = raw.trim_start_matches('-').trim_start();
        let end = rest.find("\n---")?;
        let front = &rest[..end];
        let body  = rest[end..].trim_start_matches('-').trim().to_string();

        let id    = extract(front, "id").unwrap_or_default();
        let title = extract(front, "title").unwrap_or_default();
        let status = extract(front, "status").unwrap_or_else(|| "draft".to_string());
        let date  = extract(front, "date").unwrap_or_default();

        Some(Adr { id, title, status, date, body, path: path.to_path_buf() })
    }

    pub fn is_active(&self) -> bool {
        self.status.trim() == "active"
    }
}

fn extract(front: &str, key: &str) -> Option<String> {
    for line in front.lines() {
        if let Some(rest) = line.strip_prefix(&format!("{key}:")) {
            return Some(rest.trim().to_string());
        }
    }
    None
}

/// Load all active ADRs from a directory, sorted by id.
pub fn load_active(dir: &Path) -> Vec<Adr> {
    let mut adrs: Vec<Adr> = std::fs::read_dir(dir)
        .into_iter()
        .flatten()
        .flatten()
        .filter(|e| e.path().extension().map(|x| x == "md").unwrap_or(false))
        .filter_map(|e| Adr::load(&e.path()))
        .filter(|a| a.is_active())
        .collect();
    adrs.sort_by(|a, b| a.id.cmp(&b.id));
    adrs
}

/// Format active ADRs as a compact prompt block for FA/GA context.
pub fn to_prompt_context(adrs: &[Adr]) -> String {
    if adrs.is_empty() {
        return String::new();
    }
    let mut out = String::from("## Architecture Decision Records (active)\n\n");
    out.push_str("These decisions govern how this flow is structured. Respect them.\n\n");
    for adr in adrs {
        out.push_str(&format!("### ADR-{}: {}\n", adr.id, adr.title));
        out.push_str(&adr.body);
        out.push_str("\n\n");
    }
    out
}
