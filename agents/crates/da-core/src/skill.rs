/// A skill loaded from a `skills/<name>.md` file.
/// The file uses a simple YAML front-matter block followed by the system prompt body.
///
/// ```markdown
/// ---
/// name: transaction-coordination
/// handles:
///   - TransactionCoordination
/// ---
/// You specialise in transaction coordination gates.
/// Pay attention to atomicity, rollback paths, and timeout cardinality.
/// ```
use crate::types::GateArchetype;
use anyhow::{anyhow, Result};
use std::path::Path;

#[derive(Debug, Clone)]
pub struct Skill {
    pub name: String,
    pub handles: Vec<GateArchetype>,
    pub system_prompt: String,
}

impl Skill {
    pub fn load(path: &Path) -> Result<Self> {
        let raw = std::fs::read_to_string(path)?;

        // Split on the second "---"
        let mut parts = raw.splitn(3, "---");
        parts.next(); // empty before first ---
        let front = parts.next().ok_or_else(|| anyhow!("missing front-matter in {:?}", path))?;
        let body = parts.next().unwrap_or("").trim().to_string();

        let name = extract_field(front, "name")
            .ok_or_else(|| anyhow!("skill missing 'name' field"))?;

        let handles = extract_list(front, "handles")
            .into_iter()
            .map(|s| parse_archetype(&s))
            .collect::<Result<Vec<_>>>()?;

        Ok(Skill { name, handles, system_prompt: body })
    }
}

fn extract_field(front: &str, key: &str) -> Option<String> {
    front.lines()
        .find(|l| l.trim_start().starts_with(&format!("{key}:")))
        .map(|l| l.splitn(2, ':').nth(1).unwrap_or("").trim().to_string())
}

fn extract_list(front: &str, key: &str) -> Vec<String> {
    let mut in_list = false;
    let mut items = vec![];
    for line in front.lines() {
        if line.trim_start().starts_with(&format!("{key}:")) {
            in_list = true;
            continue;
        }
        if in_list {
            if line.trim_start().starts_with("- ") {
                items.push(line.trim_start_matches(|c: char| c.is_whitespace() || c == '-').trim().to_string());
            } else {
                break;
            }
        }
    }
    items
}

fn parse_archetype(s: &str) -> Result<GateArchetype> {
    match s {
        "TransactionCoordination" => Ok(GateArchetype::TransactionCoordination),
        "StorageScaling"          => Ok(GateArchetype::StorageScaling),
        "EventRouting"            => Ok(GateArchetype::EventRouting),
        "RateLimiting"            => Ok(GateArchetype::RateLimiting),
        other                     => Ok(GateArchetype::Custom(other.to_string())),
    }
}
