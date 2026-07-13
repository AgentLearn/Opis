#!/usr/bin/env python3
"""
opis-prompt-pins — hash-pin the agent prompt skills.

FA's and CA's prompts live as repo skills (agents/skills/*.md with a
`binding:` frontmatter field naming the Python constant that loads them —
see agents/{fa,ca}/prompts.py). Every flow, evidence report, and defect
history in the corpus was produced THROUGH those prompts, so they are proof
machinery the same way gate contracts and the taxonomy are: an unnoticed
edit silently changes what every future agent run means.

Same doctrine as pins.py, applied to prompts:
  * agents/skills/pins.json is the committed lock: skill file -> sha256 of
    the FULL file bytes (frontmatter + body — the loader returns the body
    verbatim, so any byte matters).
  * A hash mismatch is ALWAYS an error. There is no legitimate silent
    change to a pinned prompt.
  * Editing a prompt is legitimate and expected — it is just an EXPLICIT
    act: re-run with --write in the same commit. The diff then shows the
    prompt change and the re-pin together, and regress.py stays green.
  * Every binding-bearing skill must be pinned (a new prompt skill that
    was never pinned is an error, not a warning — it is already live in
    the agents the moment prompts.py loads it).

Deliberately NOT covered: agents/{fa,ca}/prompts.py themselves (Python
source, reviewed as code) and non-binding skills (adr/default/transaction
— loaded by no module today; they join the lock the day they gain a
`binding:` field).

Usage:
  python tools/opis-eval/prompt_pins.py            # verify (exit 0 ok / 1 errors)
  python tools/opis-eval/prompt_pins.py --write    # (re)compute the lock file

Exit codes: 0 ok / 1 errors — mismatches are never warnings.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
DEFAULT_SKILLS_DIR = REPO_ROOT / "agents" / "skills"
PINS_NAME = "pins.json"

HASH_PREFIX = "sha256:"

_BINDING_RE = re.compile(r"^binding:\s*(\S+)\s*$", re.MULTILINE)


def file_hash(path: Path) -> str:
    return HASH_PREFIX + hashlib.sha256(path.read_bytes()).hexdigest()


def _frontmatter(text: str) -> str | None:
    """The frontmatter block, or None if the file has none."""
    if not text.startswith("---\n"):
        return None
    close = text.find("\n---\n", 4)
    return text[4:close] if close != -1 else None


def binding_skills(skills_dir: Path) -> dict[str, str]:
    """Every skill file whose frontmatter declares a `binding:` constant.
    Returns {filename: constant_name}, sorted by filename."""
    found: dict[str, str] = {}
    for p in sorted(skills_dir.glob("*.md")):
        fm = _frontmatter(p.read_text(encoding="utf-8"))
        if fm is None:
            continue
        m = _BINDING_RE.search(fm)
        if m:
            found[p.name] = m.group(1)
    return found


def compute_pins(skills_dir: Path) -> dict:
    skills = binding_skills(skills_dir)
    return {
        "_comment": ("prompt-skill lock — sha256 over full file bytes; "
                     "verify/re-pin with tools/opis-eval/prompt_pins.py "
                     "(--write). A mismatch means an agent prompt changed "
                     "without an explicit re-pin."),
        "skills": {
            name: {"binding": skills[name],
                   "hash": file_hash(skills_dir / name)}
            for name in skills
        },
    }


def verify_pins(skills_dir: Path) -> list[str]:
    """Errors only — this check has no warning tier."""
    errors: list[str] = []
    pins_path = skills_dir / PINS_NAME
    if not pins_path.exists():
        return [f"lock file missing: {pins_path} — run prompt_pins.py --write"]
    try:
        pinned = json.loads(pins_path.read_text(encoding="utf-8")).get("skills", {})
    except json.JSONDecodeError as e:
        return [f"lock file unparseable: {pins_path} — {e}"]

    live = binding_skills(skills_dir)

    for name, pin in sorted(pinned.items()):
        path = skills_dir / name
        if not path.exists():
            errors.append(f"pinned skill missing from disk: {name}")
            continue
        actual = file_hash(path)
        if actual != pin.get("hash"):
            errors.append(
                f"hash mismatch: {name} — pinned {pin.get('hash', '?')[:19]}… "
                f"actual {actual[:19]}… (prompt changed without re-pin; if "
                f"intended, run prompt_pins.py --write in the same commit)")
        if name in live and live[name] != pin.get("binding"):
            errors.append(
                f"binding drift: {name} — pinned as {pin.get('binding')}, "
                f"frontmatter now says {live[name]}")
        if name not in live:
            errors.append(
                f"pinned skill lost its binding: {name} — no `binding:` in "
                f"frontmatter; the loader can no longer be feeding it to an agent")

    for name in sorted(set(live) - set(pinned)):
        errors.append(
            f"unpinned prompt skill: {name} (binding: {live[name]}) — already "
            f"live via prompts.py but absent from the lock; run --write")

    return errors


def main() -> None:
    skills_dir = DEFAULT_SKILLS_DIR
    if "--skills-dir" in sys.argv:
        skills_dir = Path(sys.argv[sys.argv.index("--skills-dir") + 1])

    if "--write" in sys.argv:
        pins = compute_pins(skills_dir)
        out = skills_dir / PINS_NAME
        out.write_text(json.dumps(pins, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out} — {len(pins['skills'])} skill(s) pinned")
        for name, pin in pins["skills"].items():
            print(f"  {name:24s} {pin['binding']:24s} {pin['hash'][:19]}…")
        sys.exit(0)

    errors = verify_pins(skills_dir)
    if not errors:
        pinned = json.loads((skills_dir / PINS_NAME).read_text())["skills"]
        print(f"✓ {len(pinned)} prompt skill(s) match the lock")
        sys.exit(0)
    for e in errors:
        print(f"✗ {e}")
    sys.exit(1)


if __name__ == "__main__":
    main()
