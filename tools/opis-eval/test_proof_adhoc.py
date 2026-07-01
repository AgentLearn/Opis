#!/usr/bin/env python3
"""
Ad-hoc tester for opis-proof (proof.py).

Not a pytest suite — a standalone, dependency-free script that exercises the
path-reconstruction engine deterministically against a real flow (flow_v1.json
for silicon_sandwiches), with synthetic `requirements` injected in-memory.
No LLM calls. Run directly:

  python3 tools/opis-eval/test_proof_adhoc.py

Purpose: prove the proof engine itself is trustworthy before FA starts relying
on it inside its iteration loop — both the happy path (a real requirement gets
a real path) and every failure mode it's supposed to catch (missing gate,
missing outcome, phantom gate_template, genuinely unreachable requirement).
"""

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proof as proof_mod  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
FLOW_PATH = REPO_ROOT / "agents" / "output" / "silicon_sandwiches" / "flow" / "flow_v1.json"
GATES_DIR = REPO_ROOT / "agents" / "gates"

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"

failures = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global failures
    status = PASS if condition else FAIL
    print(f"  [{status}] {label}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures += 1


def run_case(title: str, spec: dict, requirements: list[dict]):
    print(f"\n--- {title} ---")
    spec = copy.deepcopy(spec)
    spec["requirements"] = requirements
    return proof_mod.verify_requirements(spec, GATES_DIR)


def main():
    base_spec = json.loads(FLOW_PATH.read_text())
    print(f"loaded: {FLOW_PATH}")
    print(f"gates dir: {GATES_DIR}")

    # ── Case 1: real, true requirements — should all prove ──────────────────
    good_requirements = [
        {"id": "REQ-1", "text": "customers can submit an order via mobile or kiosk",
         "target": {"gate": "OrderIntake", "outcome": "accepted"}},
        {"id": "REQ-2", "text": "customers can pay for their order",
         "target": {"gate": "PaymentProcessor", "outcome": "confirmed"}},
        {"id": "REQ-3", "text": "franchise owners can update the menu",
         "target": {"gate": "MenuManager", "outcome": "updated"}},
        {"id": "REQ-4", "text": "customers receive a pickup time estimate",
         "target": {"gate": "PickupEstimator", "outcome": "estimated"}},
    ]
    results = run_case("Case 1: real requirements (expect all proved)", base_spec, good_requirements)
    for r, req in zip(results, good_requirements):
        proved = r["status"] == "proved"
        check(f"{req['id']} proved", proved, json.dumps(r["issues"]))
        check(f"{req['id']} has no fallback/cyclic notes", proved and not r["notes"], json.dumps(r["notes"]))
        if proved:
            for t, path in r["proofs"].items():
                print(f"         [{t}] {proof_mod.format_path(path)}")

    # ── Case 2: target gate doesn't exist ────────────────────────────────────
    results = run_case(
        "Case 2: nonexistent target gate (expect unproved)",
        base_spec,
        [{"id": "REQ-X", "text": "bogus requirement",
          "target": {"gate": "NotAGate", "outcome": "whatever"}}],
    )
    r = results[0]
    check("flagged as unproved", r["status"] == "unproved")
    check("issue mentions missing gate", any("does not exist in this flow" in i for i in r["issues"]),
          r["issues"])

    # ── Case 3: outcome doesn't exist on a real gate ─────────────────────────
    results = run_case(
        "Case 3: invalid outcome name (expect unproved)",
        base_spec,
        [{"id": "REQ-Y", "text": "order intake has a 'teleported' outcome",
          "target": {"gate": "OrderIntake", "outcome": "teleported"}}],
    )
    r = results[0]
    check("flagged as unproved", r["status"] == "unproved")
    check("issue mentions missing outcome", any("outcome" in i and "not found" in i for i in r["issues"]),
          r["issues"])

    # ── Case 4: phantom gate_template (gate references a .md that doesn't exist) ─
    phantom_spec = copy.deepcopy(base_spec)
    phantom_spec["gates"]["OrderIntake"]["gate_template"] = "nonexistent_template_xyz"
    results = run_case(
        "Case 4: phantom gate_template (expect unproved)",
        phantom_spec,
        [{"id": "REQ-Z", "text": "order intake uses a real gate template",
          "target": {"gate": "OrderIntake", "outcome": "accepted"}}],
    )
    r = results[0]
    check("flagged as unproved", r["status"] == "unproved")
    check("issue mentions phantom gate", any("phantom gate" in i for i in r["issues"]), r["issues"])

    # ── Case 5: genuinely unreachable requirement (remove the wiring) ───────
    broken_spec = copy.deepcopy(base_spec)
    broken_spec["synapses"] = [
        s for s in broken_spec["synapses"]
        if not (s["to"] == "OrderIntake" and s["pulse_type"] == "sandwich_order")
    ]
    results = run_case(
        "Case 5: requirement with no structural path (expect unproved)",
        broken_spec,
        [{"id": "REQ-W", "text": "customers can submit an order (wiring removed)",
          "target": {"gate": "OrderIntake", "outcome": "accepted"}}],
    )
    r = results[0]
    check("flagged as unproved", r["status"] == "unproved")
    check("issue mentions unreachable", any("not reachable" in i for i in r["issues"]),
          r["issues"])

    print(f"\n{'='*60}")
    if failures:
        print(f"\033[31m{failures} check(s) FAILED\033[0m — proof engine is not trustworthy yet")
        sys.exit(1)
    else:
        print("\033[32mAll checks passed\033[0m — proof engine behaves correctly on both real and broken input")
        sys.exit(0)


if __name__ == "__main__":
    main()
