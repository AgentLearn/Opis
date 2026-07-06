#!/usr/bin/env python3
"""schema_check — CA schema-conformance verifier.

Checks a CA-produced message-schema file against the flow it claims to
translate. This is the mechanical half of CA's translation step: an LLM
derives the schemas, this proves the derivation covers the flow. A schema
that fails here means either a bad translation (CA iterates) or an
untranslatable gate description (falsified contract — escalate).

Usage:
  python3 tools/opis-eval/schema_check.py <schemas.json> <flow_vN.json>

Checks:
  1. WIRE COVERAGE     — every pulse_type on every synapse has a schema
                         (directly or via an ancestor's schema + declared
                         subtype schema; a missing concrete schema is an
                         error, an inherited-only one is a warning).
  2. EXTENDS SOUNDNESS — every schema's `extends` chain matches the flow's
                         archetype DAG merged with the base slot-type
                         taxonomy; a schema may not invent hierarchy.
  3. NO ORPHAN SCHEMAS — every schema names a type that exists in the flow's
                         archetypes, the base taxonomy, or on a synapse
                         (warning: dead translation weight).
  4. FIELD INHERITANCE — a subtype schema never redeclares a parent field
                         with a different spec (silent retyping breaks
                         cross-gate agreement).
  5. ENVELOPE          — the envelope declares the required carrier fields
                         (msg_id, pulse_type, ts_ms, correlation_key,
                         source_locus, body).

Exit codes: 0 clean, 1 errors, 2 warnings only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eval as eval_mod  # build_type_dag, load_base_taxonomy

REQUIRED_ENVELOPE = {"msg_id", "pulse_type", "ts_ms", "correlation_key",
                     "source_locus", "body"}


def parents_map(spec: dict) -> dict[str, str]:
    """type → parent from flow archetypes merged with the base taxonomy.

    SELF-LOOP GUARD (2026-07-06): committed flows may declare an archetype
    as extending ITSELF ("X extends X" = FA's idiom for "this kata term is
    the base type", e.g. flow_v2 silicon routing_decision/payment_failed/
    menu_update). Letting that override the base taxonomy made the extends
    check demand schemas extend themselves — unsatisfiable; CA burned its
    whole iteration budget against it (silicon, 2026-07-06). A self-extends
    is a base-type reference: keep the base taxonomy's parent instead.
    Pinned flows are immutable, so tolerance here is the only fix."""
    parents = dict(eval_mod.load_base_taxonomy())
    for name, aspec in spec.get("archetypes", {}).items():
        if isinstance(aspec, dict) and aspec.get("extends") \
                and aspec["extends"] != name:
            parents[name] = aspec["extends"]
    return parents


def ancestors(t: str, parents: dict[str, str]) -> list[str]:
    out, seen = [], set()
    while t in parents and t not in seen:
        seen.add(t)
        t = parents[t]
        out.append(t)
    return out


def check(schemas_doc: dict, spec: dict) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    schemas: dict = schemas_doc.get("schemas", {})
    parents = parents_map(spec)

    # 5. envelope
    env_fields = set(schemas_doc.get("envelope", {}).get("fields", {}))
    missing_env = REQUIRED_ENVELOPE - env_fields
    if missing_env:
        errors.append(f"envelope missing required fields: {sorted(missing_env)}")

    # wire types
    wire: set[str] = set()
    for syn in spec.get("synapses", []):
        if syn.get("pulse_type"):
            wire.add(syn["pulse_type"])
        for t in syn.get("pulse_types") or []:
            wire.add(t)

    # 1. coverage
    for t in sorted(wire):
        if t in schemas:
            continue
        anc = ancestors(t, parents)
        covered_by = next((a for a in anc if a in schemas), None)
        if covered_by:
            warnings.append(
                f"wire type '{t}' has no schema of its own — inherits "
                f"'{covered_by}' only; add a concrete schema if it carries extra fields")
        else:
            errors.append(
                f"wire type '{t}' has NO schema anywhere in its ancestor chain "
                f"({' → '.join(anc) if anc else 'no ancestors'}) — untranslated message")

    # 2. extends soundness + 3. orphans + 4. field inheritance
    known_types = (set(spec.get("archetypes", {})) | set(parents)
                   | set(parents.values()) | wire)
    for name, sch in schemas.items():
        declared_parent = sch.get("extends")
        true_parent = parents.get(name)
        if declared_parent != true_parent:
            errors.append(
                f"schema '{name}': extends '{declared_parent}' but the type DAG "
                f"says parent is '{true_parent}' — schemas may not invent hierarchy")
        if name not in known_types:
            warnings.append(
                f"schema '{name}' names a type that appears nowhere in this flow "
                f"(archetypes, base taxonomy, or synapses) — dead translation weight")
        # field inheritance: no silent redeclaration up the chain
        fields = sch.get("fields", {})
        for anc in ancestors(name, parents):
            anc_fields = schemas.get(anc, {}).get("fields", {})
            for f in set(fields) & set(anc_fields):
                if fields[f] != anc_fields[f]:
                    errors.append(
                        f"schema '{name}' redeclares field '{f}' of ancestor "
                        f"'{anc}' with a different spec — silent retyping breaks "
                        f"cross-gate agreement")

    return errors, warnings


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    schemas_doc = json.loads(Path(sys.argv[1]).read_text())
    spec = eval_mod.load_spec(Path(sys.argv[2]))

    print(f"\nopis-schema-check  {sys.argv[1]}  vs  {sys.argv[2]}")
    errors, warnings = check(schemas_doc, spec)
    for e in errors:
        print(f"  ✗ {e}")
    for w in warnings:
        print(f"  ⚠ {w}")
    n_wire = len({s.get('pulse_type') for s in spec.get('synapses', []) if s.get('pulse_type')})
    print(f"\n{len(schemas_doc.get('schemas', {}))} schema(s), {n_wire} wire type(s): "
          f"{len(errors)} error(s), {len(warnings)} warning(s)")
    sys.exit(1 if errors else (2 if warnings else 0))


if __name__ == "__main__":
    main()
