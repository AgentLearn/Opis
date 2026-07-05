#!/usr/bin/env python3
"""
opis-pins — flow pin block: compute + verify.

A committed flow_vN.json is a proof artifact. Its proofs were run against
specific gate contracts and a specific slot-type taxonomy, so the flow pins
them — versions AND content hashes — in a `pins` block:

    "pins": {
      "gates":    { "<template>": {"version": 1, "hash": "sha256:<hex>"} },
      "taxonomy": {"version": 1, "hash": "sha256:<hex>"}
    }

Doctrine (design 2026-07-04, OpisDescription "Versioning, User Gates, and
Evidence"):
  * Official contracts are append-only. Any version ever pinned by a committed
    flow is immutable; the hash catches in-place edits.
  * A new contract version never moves a pinned flow. Upgrade = manual
    re-prove -> new flow version with fresh pins.
  * Pin scope = gates + taxonomy. Verifier versions are a separate problem
    (may join the pin later — deliberately NOT included now).

File layout (since the first real amendment, 2026-07-05): the CURRENT
contract lives as agents/gates/<template>.md with a `version:` frontmatter
field (default 1 when absent). Every superseded version is archived verbatim
at agents/gates/archive/<template>_v<N>.md — append-only, immutable. A pin
resolves to the current file when versions match, else into the archive;
a hash mismatch against the resolved file is ALWAYS an error — there is no
legitimate in-place change to a pinned contract version.

Usage:
  python tools/opis-eval/pins.py <flow.json> [--gates-dir D] [--slot-types F]
  python tools/opis-eval/pins.py <flow.json> --write   # compute + insert pins

Exit codes: 0 ok / 1 errors / 2 warnings-only (matches eval.py's tiering).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
DEFAULT_GATES_DIR = REPO_ROOT / "agents" / "gates"
DEFAULT_SLOT_TYPES = REPO_ROOT / "agents" / "slot_types" / "index.md"

HASH_PREFIX = "sha256:"


# ── primitives ────────────────────────────────────────────────────────────────

def file_hash(path: Path) -> str:
    return HASH_PREFIX + hashlib.sha256(path.read_bytes()).hexdigest()


def frontmatter_version(path: Path) -> int:
    """`version:` from YAML frontmatter (gate .md) or a `Version:` line
    (slot_types index). Default 1 — absence means first version."""
    text = path.read_text(errors="replace")
    m = re.search(r"^[Vv]ersion:\s*(\d+)\s*$", text, re.MULTILINE)
    return int(m.group(1)) if m else 1


ARCHIVE_DIR_NAME = "archive"


def contract_path(gates_dir: Path, template: str,
                  version: int | None = None) -> Path:
    """Resolve a template's contract file. version=None → the current file.
    A pinned version that doesn't match the current file's frontmatter
    resolves into the append-only archive (gates/archive/<t>_v<N>.md) —
    where the amendment path parked it."""
    current = gates_dir / f"{template}.md"
    if version is None:
        return current
    if current.exists() and frontmatter_version(current) == version:
        return current
    return gates_dir / ARCHIVE_DIR_NAME / f"{template}_v{version}.md"


def flow_templates(flow: dict) -> set[str]:
    """Every gate template the flow instantiates."""
    out: set[str] = set()
    for _name, g in (flow.get("gates") or {}).items():
        t = g.get("gate_template")
        if t:
            out.add(t)
    return out


# ── compute ───────────────────────────────────────────────────────────────────

def compute_pins(flow: dict, gates_dir: Path = DEFAULT_GATES_DIR,
                 slot_types: Path = DEFAULT_SLOT_TYPES) -> tuple[dict, list[str]]:
    """Pin block for a flow from current on-disk state. Returns (pins, errors);
    errors are templates the flow uses but no contract file covers — a flow
    with compute errors must NOT be committed."""
    errors: list[str] = []
    gates: dict[str, dict] = {}
    for t in sorted(flow_templates(flow)):
        contract = gates_dir / f"{t}.md"
        if not contract.exists():
            errors.append(f"pin compute: no contract file for template '{t}' "
                          f"({contract})")
            continue
        gates[t] = {"version": frontmatter_version(contract),
                    "hash": file_hash(contract)}
    if not slot_types.exists():
        errors.append(f"pin compute: slot-type taxonomy missing ({slot_types})")
        taxonomy = None
    else:
        taxonomy = {"version": frontmatter_version(slot_types),
                    "hash": file_hash(slot_types)}
    return {"gates": gates, "taxonomy": taxonomy}, errors


# ── verify ────────────────────────────────────────────────────────────────────

def verify_pins(flow: dict, gates_dir: Path = DEFAULT_GATES_DIR,
                slot_types: Path = DEFAULT_SLOT_TYPES
                ) -> tuple[list[str], list[str]]:
    """(errors, warnings) for a committed flow's pin block.

    * no pins block            -> warning (legacy flow, predates pinning)
    * used template unpinned   -> error
    * pinned contract missing  -> error
    * hash mismatch            -> error (in-place edit of a pinned contract)
    * version mismatch w/ same hash -> error (metadata tampering)
    * pinned-but-unused template    -> warning (stale pin)
    * taxonomy hash/version checks mirror the gate checks
    """
    errors: list[str] = []
    warnings: list[str] = []

    pins = flow.get("pins")
    if not pins:
        warnings.append("flow has no pins block (legacy, pre-pinning) — "
                        "re-prove to pin it")
        return errors, warnings

    used = flow_templates(flow)
    pinned = pins.get("gates") or {}

    for t in sorted(used - set(pinned)):
        errors.append(f"template '{t}' used by flow but not pinned")
    for t in sorted(set(pinned) - used):
        warnings.append(f"template '{t}' pinned but not used by flow")

    for t in sorted(used & set(pinned)):
        pin = pinned[t]
        contract = contract_path(gates_dir, t, pin.get("version"))
        if not contract.exists():
            errors.append(
                f"pinned contract '{t}' v{pin.get('version')} missing on disk "
                f"(neither current file at that version nor {contract.name} "
                f"in the archive) — superseded versions are archived, never deleted")
            continue
        actual_hash = file_hash(contract)
        actual_version = frontmatter_version(contract)
        if actual_hash != pin.get("hash"):
            errors.append(
                f"contract '{t}' hash mismatch: pinned v{pin.get('version')} "
                f"{str(pin.get('hash'))[:19]}… but on-disk file differs — "
                f"pinned contracts are immutable; an amendment must be a new "
                f"version + a re-proved flow")
        elif actual_version != pin.get("version"):
            errors.append(
                f"contract '{t}' version mismatch with identical content: "
                f"pinned v{pin.get('version')}, frontmatter says "
                f"v{actual_version}")

    tax_pin = pins.get("taxonomy")
    if not tax_pin:
        errors.append("pins block has no taxonomy pin")
    elif not slot_types.exists():
        errors.append(f"pinned taxonomy missing on disk ({slot_types})")
    else:
        if file_hash(slot_types) != tax_pin.get("hash"):
            errors.append(
                f"slot-type taxonomy hash mismatch: flow proved against "
                f"v{tax_pin.get('version')} but index.md differs — taxonomy "
                f"changes require a re-prove")
        elif frontmatter_version(slot_types) != tax_pin.get("version"):
            errors.append(
                f"taxonomy version mismatch with identical content: pinned "
                f"v{tax_pin.get('version')}, file says "
                f"v{frontmatter_version(slot_types)}")

    return errors, warnings


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="verify (default) or write a "
                                             "flow's pin block")
    ap.add_argument("flow", type=Path)
    ap.add_argument("--gates-dir", type=Path, default=DEFAULT_GATES_DIR)
    ap.add_argument("--slot-types", type=Path, default=DEFAULT_SLOT_TYPES)
    ap.add_argument("--write", action="store_true",
                    help="compute pins from current disk state and insert "
                         "into the flow file")
    args = ap.parse_args()

    flow = json.loads(args.flow.read_text())

    if args.write:
        pins, errs = compute_pins(flow, args.gates_dir, args.slot_types)
        if errs:
            for e in errs:
                print(f"  ERROR  {e}")
            return 1
        flow["pins"] = pins
        args.flow.write_text(json.dumps(flow, indent=2))
        print(f"  pins written: {len(pins['gates'])} gate contract(s) + "
              f"taxonomy v{pins['taxonomy']['version']}")
        return 0

    errors, warnings = verify_pins(flow, args.gates_dir, args.slot_types)
    for w in warnings:
        print(f"  WARN   {w}")
    for e in errors:
        print(f"  ERROR  {e}")
    if errors:
        return 1
    print(f"  pins OK" if not warnings else "  pins: warnings only")
    return 2 if warnings else 0


if __name__ == "__main__":
    sys.exit(main())
