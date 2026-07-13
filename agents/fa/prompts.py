"""FA prompt bindings — the prompt texts live as repo skills in agents/skills/.

Each constant below is loaded verbatim from its skill file (frontmatter
`binding:` names the constant). Edit the .md files, not this module.
Extraction verified byte-identical to the pre-extraction constants
(2026-07-13); the build_* user-prompt templates remain code because their
sections are inseparable from the argument wiring.
"""

from pathlib import Path

_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def _load_skill(name: str) -> str:
    """Return the skill body verbatim: everything after the frontmatter
    close, minus nothing — no stripping (some prompts end without a
    newline, and bodies may themselves contain `---` lines)."""
    text = (_SKILLS_DIR / f"{name}.md").read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"skill {name}: missing frontmatter")
    close = text.index("\n---\n", 4)
    return text[close + len("\n---\n"):]


SYSTEM_PROMPT = _load_skill("fa_system")
TAXONOMY_PROMPT = _load_skill("fa_taxonomy")
GATE_GENERATION_PROMPT = _load_skill("fa_gate_generation")
GATE_AMENDMENT_PROMPT = _load_skill("fa_gate_amendment")
GATE_INDEX_ROW_PROMPT = _load_skill("fa_gate_index_row")


def build_user_prompt(kata: str, slot_types: str, gates_index: str, version: int,
                      previous_errors: str = "", adr_decisions: str = "",
                      taxonomy: str = "") -> str:
    prompt = f"""## Kata
{kata}

## Available Slot Types
{slot_types}

## Available Gates
{gates_index}

## Task
Produce flow_v{version}.json for this kata.
"""
    if taxonomy:
        prompt += f"""
## Domain Taxonomy (BINDING)
The domain vocabulary below is FIXED. Your flow's `archetypes` section must use
EXACTLY these terms with EXACTLY these `extends` — never invent, rename, or drop
types mid-iteration. `consumed_by`/`produced_by` list the index gates whose
slots accept/emit each term's slot type — use them to select gates. If a term
you need is missing, that is a taxonomy gap: say so in an ADR, do not improvise.
{taxonomy}
"""
    if adr_decisions:
        prompt += f"""
## Decided ADRs for this kata (BINDING — follow their decisions and guidance;
never re-propose a rejected gate)
{adr_decisions}
"""
    if previous_errors:
        prompt += f"""
## Errors from previous version (fix these)
{previous_errors}
"""
    return prompt
