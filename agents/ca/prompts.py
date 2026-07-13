"""CA — Component Architect (dev lead) prompts.

CA is flow-scoped, not gate-scoped: it takes a PROVED flow (flow_vN.json,
pinned) plus the gate contracts it pins, and turns them into a runnable
co-sim stack. Two LLM stages, everything else deterministic:

  1. SCHEMA TRANSLATION — gates + flow → shared per-archetype message
     schemas. Every field must be justified by a consuming gate's decision
     logic. A decision that cannot be carried by any derivable field is a
     FALSIFIED gate description — reported, never papered over. This is the
     cheap pre-code feasibility test.
  2. GATE CODEGEN — one Rust source implementing every substituted template
     against those schemas, compiled to wasm32-wasip1 and run under
     wasmtime (capability-denial by construction).

All CA outputs are EPHEMERAL (regenerated per run, gitignored); only
evidence reports persist.

The prompt texts live as repo skills in agents/skills/ (frontmatter
`binding:` names the constant); edit the .md files, not this module.
Extraction verified byte-identical to the pre-extraction constants
(2026-07-13). The build_* user-prompt templates remain code because their
sections are inseparable from the argument wiring.
"""

from pathlib import Path

_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def _load_skill(name: str) -> str:
    """Return the skill body verbatim: everything after the frontmatter
    close — no stripping (some prompts end without a newline)."""
    text = (_SKILLS_DIR / f"{name}.md").read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"skill {name}: missing frontmatter")
    close = text.index("\n---\n", 4)
    return text[close + len("\n---\n"):]


# The ontology rule, verbatim — it decides what a schema is ABOUT:
ONTOLOGY_RULE = (
    "Things that act are loci; facts that travel are terms; matter never "
    "flows — only descriptions of it (payload content = CA schema layer)."
)

# ── Stage 1: schema translation ──────────────────────────────────────────────

SCHEMA_PROMPT = _load_skill("ca_schema")

# ── Stage 2: gate implementation (Rust → wasm32-wasip1) ─────────────────────

GATE_CODEGEN_PROMPT = _load_skill("ca_codegen")

# Drift guard: the rule is embedded in the schema skill; if someone edits
# ca_schema.md and loses or rewords it, fail at import, not at review.
if ONTOLOGY_RULE not in SCHEMA_PROMPT:
    raise ValueError("ca_schema.md no longer embeds ONTOLOGY_RULE verbatim")


def build_schema_user_prompt(flow_json: str, gate_contracts: str,
                             slot_types: str, errors: str = "",
                             env_doc: str = "") -> str:
    parts = [
        f"## Proved flow (binding)\n```json\n{flow_json}\n```",
        f"## Pinned gate contracts\n{gate_contracts}",
        f"## Base slot-type taxonomy\n{slot_types}",
    ]
    if env_doc:
        parts.append(
            "## Environment (descriptive facts — binding; rule 8 applies)\n"
            + env_doc)
    if errors:
        parts.append(
            "## Defects in your previous schema document — ALL must be resolved "
            "at once, and none reintroduced\n" + errors)
    return "\n\n".join(parts)


def build_codegen_user_prompt(flow_json: str, schemas_json: str,
                              gate_contracts: str, errors: str = "",
                              env_doc: str = "") -> str:
    parts = [
        f"## Proved flow — instances, templates, outcomes (binding)\n```json\n{flow_json}\n```",
        f"## Shared message schemas (binding — code against these)\n```json\n{schemas_json}\n```",
        f"## Gate contracts (the decisions to implement)\n{gate_contracts}",
    ]
    if env_doc:
        parts.append(
            "## Environment (descriptive facts — binding constraints)\n"
            "Decision logic and derived values must be consistent with these "
            "facts (artifact shapes, invariants, exit-code semantics). Assume "
            "NOTHING the document does not state. The process model above is "
            "unchanged — bodies remain schema-derived and deterministic.\n\n"
            + env_doc)
    if errors:
        parts.append(
            "## Defects in your previous implementation — ALL must be resolved "
            "at once, and none reintroduced. Respond with the COMPLETE corrected "
            "file, not a patch.\n" + errors)
    return "\n\n".join(parts)
