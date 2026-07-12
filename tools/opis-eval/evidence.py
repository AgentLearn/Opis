#!/usr/bin/env python3
"""
opis-evidence — assemble the evidence report for a committed flow.

One JSON report per flow version, append-only, living beside the flow it
describes (evidence_vN.json for flow_vN.json) with a derived human summary
(evidence_vN.md). The report is the persistent residue of a verification run
— for co-sim runs it is the ONLY artifact that persists (CA outputs are
ephemeral).

Doctrine (design 2026-07-04, OpisDescription "Versioning, User Gates, and
Evidence"):
  * Claim grammar — every statement is {claim, verdict, evidence, scope}:
      verdict:  proved | passed | bounded | flagged | failed
      scope:    static | twin | cosim | sourced
    No assertion without an evidence pointer.
  * Falsify confidently, validate weakly — enforced by the format: `failed`
    is conclusive; a dynamic (twin/cosim) pass is always `bounded`, i.e. a
    sandbox lower bound, never production validation.
  * The verdict block is GENERATED from the bounded/flagged claims, never
    hand-written.
  * Evidence has one judge: the User. Lifecycle promotion is a user decision
    through the ADR channel with evidence pointers attached.

Layers:
  1. provenance — kata, flow version, full pin block, twin runs/seed, env.
  2. static     — eval exit, each requirement with witness paths, gate
                  conformance, pin verification.
  3. dynamic    — twin per-gate fire%/p50/p95/p99 + norm judgment (reusing
                  twin_check's norm matching), dead gates; co-sim results
                  when a co-sim report is supplied.
  4. gates      — per-contract slices keyed template@vN: what THIS run
                  demonstrated about each contract, plus its lifecycle tags.

Usage:
  python tools/opis-eval/evidence.py <flow_vN.json>
      [--gates-dir D] [--slot-types F] [--latencies F]
      [--twin-report F] [--cosim-report F] [--out F] [--no-md]
      [--environment NAME] [--env-hash sha256:...]

Exit codes: 0 report written / 1 could not build report.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
DEFAULT_GATES_DIR = REPO_ROOT / "agents" / "gates"
DEFAULT_SLOT_TYPES = REPO_ROOT / "agents" / "slot_types" / "index.md"
DEFAULT_LATENCIES = REPO_ROOT / "agents" / "latencies" / "latencies.json"
ENVS_DIR = REPO_ROOT / "agents" / "environments"

SCHEMA_VERSION = 1


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


proof_mod = _load("opis_proof", HERE / "proof.py")
eval_mod = sys.modules["opis_eval"]
pins_mod = _load("opis_pins", HERE / "pins.py")


# ── claim helpers ─────────────────────────────────────────────────────────────

def claim(text: str, verdict: str, evidence, scope: str, gate: str | None = None) -> dict:
    """Every claim carries an evidence pointer — an empty one is a bug."""
    assert verdict in ("proved", "passed", "bounded", "flagged", "failed"), verdict
    assert scope in ("static", "twin", "cosim", "sourced"), scope
    assert evidence, f"claim without evidence pointer: {text}"
    c: dict = {"claim": text, "verdict": verdict, "evidence": evidence, "scope": scope}
    if gate:
        c["gate"] = gate
    return c


def gate_frontmatter_tags(gates_dir: Path, template: str) -> dict:
    """Lifecycle tags from the contract frontmatter (defaults: draft /
    llm-estimate — absence means nothing has been demonstrated yet)."""
    path = gates_dir / f"{template}.md"
    tags = {"status": "draft", "confidence": "llm-estimate"}
    if path.exists():
        text = path.read_text(errors="replace")
        for key in ("status", "confidence"):
            m = re.search(rf"^{key}:\s*(\S+)\s*$", text, re.MULTILINE)
            if m:
                tags[key] = m.group(1)
    return tags


# ── layer builders ────────────────────────────────────────────────────────────

def static_claims(flow_path: Path, spec: dict, gates_dir: Path,
                  slot_types: Path) -> tuple[list[dict], dict]:
    """Static-scope claims + raw proof results (for the gate slices)."""
    claims: list[dict] = []

    r = subprocess.run([sys.executable, str(HERE / "eval.py"), str(flow_path)],
                       capture_output=True, text=True)
    if r.returncode == 1:
        claims.append(claim("structural eval clean", "failed",
                            "opis-eval exit 1 (structural errors)", "static"))
    elif r.returncode == 2:
        claims.append(claim("structural eval clean", "flagged",
                            "opis-eval exit 2 (warnings only)", "static"))
    else:
        claims.append(claim("structural eval clean", "passed",
                            "opis-eval exit 0", "static"))

    results = proof_mod.verify_requirements(spec, gates_dir)
    for res in results:
        rid = res.get("id", "?")
        target = res.get("target", {})
        if res["status"] == "proved":
            claims.append(claim(
                f"requirement {rid} proved at {target.get('gate')}:"
                f"{target.get('outcome')}", "proved",
                {"witness_paths": res.get("proofs", {}),
                 "notes": res.get("notes", [])},
                "static", gate=target.get("gate")))
        else:
            claims.append(claim(
                f"requirement {rid} proved", "failed",
                {"issues": res.get("issues", [])},
                "static", gate=target.get("gate")))

    conf_issues = proof_mod.check_gate_conformance(spec, gates_dir)
    if conf_issues:
        for ci in conf_issues:
            claims.append(claim("gate conformance", "failed",
                                ci.get("message", str(ci)), "static",
                                gate=ci.get("gate")))
    else:
        claims.append(claim(
            "every gate instance honors its template's contract", "passed",
            f"gate-conformance: 0 violations across "
            f"{len(spec.get('gates', {}))} instances", "static"))

    pin_errors, pin_warnings = pins_mod.verify_pins(spec, gates_dir, slot_types)
    for e in pin_errors:
        claims.append(claim("pins verified", "failed", e, "static"))
    for w in pin_warnings:
        claims.append(claim("pins verified", "flagged", w, "static"))
    if not pin_errors and not pin_warnings:
        claims.append(claim(
            "flow pinned to exact contracts + taxonomy", "passed",
            f"pins: {len((spec.get('pins') or {}).get('gates', {}))} "
            f"contract(s) + taxonomy, all hashes match", "static"))

    return claims, {r_.get("id"): r_ for r_ in results}


def twin_claims(spec: dict, twin_report: dict, latencies: Path) -> list[dict]:
    """Twin-scope claims. Passes are `bounded` — simulated distributions,
    not production. Norm judgment reuses twin_check's matcher."""
    claims: list[dict] = []
    runs = twin_report.get("runs")

    dead = twin_report.get("dead_gates", [])
    for g in dead:
        claims.append(claim(f"gate {g} participates in the flow", "failed",
                            f"twin: never fired in {runs} runs", "twin", gate=g))
    if not dead:
        claims.append(claim("no dead gates", "bounded",
                            f"twin: every gate fired within {runs} runs", "twin"))

    norms = {}
    if latencies.exists():
        norms = json.loads(latencies.read_text()).get("norms", {})
    twin_check = _load("opis_twin_check", HERE / "twin_check.py")

    gates_stats = twin_report.get("gates", {})
    for req in spec.get("requirements", []):
        rid = req.get("id", "?")
        tgate = req.get("target", {}).get("gate")
        stats = gates_stats.get(tgate)
        if stats is None:
            claims.append(claim(f"{rid} end-to-end latency measured", "flagged",
                                f"twin: target gate '{tgate}' missing from twin "
                                f"report", "twin", gate=tgate))
            continue
        p95 = stats.get("p95_ms", 0.0)
        evidence = {"fire_pct": stats.get("fire_pct"),
                    "p50_ms": stats.get("p50_ms"), "p95_ms": p95,
                    "p99_ms": stats.get("p99_ms"),
                    "service_source": stats.get("service_source"),
                    "runs": runs}
        matched = twin_check.norm_for_requirement(req, spec, norms) if norms else None
        if matched is None:
            claims.append(claim(f"{rid} e2e latency (no norm matched — unjudged)",
                                "flagged", evidence, "twin", gate=tgate))
            continue
        norm_key, norm = matched
        expected = float(norm.get("expected_p95_ms", 0))
        evidence["norm"] = {"key": norm_key, "expected_p95_ms": expected,
                            "confidence": norm.get("confidence", "llm-estimate")}
        if expected and p95 > expected:
            claims.append(claim(f"{rid} e2e p95 within norm '{norm_key}'",
                                "flagged", evidence, "twin", gate=tgate))
        else:
            claims.append(claim(f"{rid} e2e p95 within norm '{norm_key}'",
                                "bounded", evidence, "twin", gate=tgate))
    return claims


def cosim_claims(cosim_report: dict) -> list[dict]:
    """Co-sim scope. The report format is CA's evidence output: passes are
    `bounded` (sandbox lower bounds), failures conclusive. Accepts a loose
    shape until the CA loop firms it up: {substituted: [templates],
    gates: {name: {...stats}}, failures: [{gate?, detail}], notes: []}."""
    claims: list[dict] = []
    substituted = cosim_report.get("substituted", [])
    if substituted:
        claims.append(claim(
            f"co-sim ran with {len(substituted)} real gate implementation(s)",
            "bounded", {"substituted": substituted}, "cosim"))
    for f in cosim_report.get("failures", []):
        claims.append(claim(f.get("claim", "co-sim check"), "failed",
                            f.get("detail", f), "cosim", gate=f.get("gate")))
    for gname, stats in (cosim_report.get("gates") or {}).items():
        claims.append(claim(f"{gname} measured under co-sim", "bounded",
                            {**stats, "note": "sandbox lower bound only"},
                            "cosim", gate=gname))

    # ── ADR-005: sourced pass — gates fed by RECORDED REAL EXECUTIONS.
    # Scope `sourced` marks claims bought by an implementation run (N=1
    # tape); verdict stays bounded — real facts, sandbox bounds.
    s = cosim_report.get("sourced")
    if s:
        tape = s.get("tape") or {}
        claims.append(claim(
            f"{len(s.get('gates', []))} gate(s) replayed recorded real "
            f"executions ({s.get('runs')} runs)", "bounded",
            {"gates": s.get("gates"), "tape": tape}, "sourced"))
        envpin = tape.get("environment") or {}
        doc = REPO_ROOT / envpin.get("file", "")
        if envpin.get("hash") and doc.exists():
            now = "sha256:" + hashlib.sha256(doc.read_bytes()).hexdigest()
            if now != envpin["hash"]:
                claims.append(claim(
                    "tape current vs environment document", "flagged",
                    f"tape cut against {envpin['hash']}, env doc now {now} "
                    f"— a stale tape is a quiet lie; re-record", "sourced"))
        for g in s.get("gates", []):
            claims.append(claim(
                f"{g} fed by recorded real execution", "bounded",
                {"tape": tape.get("file"),
                 "recorded_utc": tape.get("recorded_utc")},
                "sourced", gate=g))
    return claims


def gate_slices(spec: dict, all_claims: list[dict], gates_dir: Path) -> dict:
    """Per-contract evidence slices keyed template@vN — what this run
    demonstrated about each contract. Harvested for promotion decisions."""
    pins = (spec.get("pins") or {}).get("gates", {})
    instance_to_template = {name: g.get("gate_template")
                            for name, g in (spec.get("gates") or {}).items()
                            if g.get("gate_template")}
    slices: dict[str, dict] = {}
    for template in sorted(set(instance_to_template.values())):
        version = pins.get(template, {}).get("version", 1)
        key = f"{template}@v{version}"
        instances = sorted(n for n, t in instance_to_template.items()
                           if t == template)
        related = [i for i, cl in enumerate(all_claims)
                   if cl.get("gate") in instances]
        slices[key] = {
            "instances": instances,
            "tags": gate_frontmatter_tags(gates_dir, template),
            "claims": related,   # indices into the claims array
        }
    return slices


def verdict_block(spec: dict, all_claims: list[dict]) -> dict:
    """Generated, never hand-written."""
    n_reqs = len(spec.get("requirements", []))
    proved = sum(1 for c in all_claims
                 if c["verdict"] == "proved" and c["claim"].startswith("requirement"))
    failed = [c["claim"] for c in all_claims if c["verdict"] == "failed"]
    caveats = [f"[{c['scope']}] {c['claim']}"
               for c in all_claims if c["verdict"] in ("bounded", "flagged")]
    if failed:
        overall = "failed"
    elif proved == n_reqs and n_reqs > 0:
        overall = "proved (static) / bounded (dynamic)" \
            if any(c["scope"] in ("twin", "cosim") for c in all_claims) \
            else "proved (static only — no dynamic evidence)"
    else:
        overall = "incomplete"
    return {"overall": overall,
            "requirements": f"{proved}/{n_reqs} proved",
            "failed": failed,
            "caveats": caveats}


# ── environment-doc pin (2026-07-06 decision: env hash-pinned into EVIDENCE,
#    never into the flow pin block — flows stay infra-blind; a translation is
#    keyed flow_vN × env_vM and each keying pins separately) ───────────────────

def environment_doc_pin(env_name: str, env_hash: str | None) -> tuple[dict, dict]:
    """Returns (provenance block, claim). Verification is ADVISORY, kata-pin
    style: a doc that moved mid-run flags the evidence, never voids it."""
    path = ENVS_DIR / f"{env_name}.md"
    file_rel = str(path.relative_to(REPO_ROOT))
    if not path.exists():
        return ({"name": env_name, "file": file_rel, "hash": env_hash,
                 "note": "document missing at evidence time"},
                claim("translation pinned to environment document", "flagged",
                      f"environment doc {file_rel} MISSING at evidence time "
                      f"(run-start hash: {env_hash})", "static"))
    now_hash = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    pin = {"name": env_name, "file": file_rel, "hash": env_hash or now_hash}
    if env_hash and env_hash != now_hash:
        return (pin, claim(
            "translation pinned to environment document", "flagged",
            f"environment doc {file_rel} MOVED during the run — translation "
            f"read {env_hash}, on disk now {now_hash}; re-run CA against the "
            f"current document", "static"))
    return (pin, claim(
        "translation pinned to environment document", "passed",
        f"environment doc {file_rel} {pin['hash']} (verified on disk)",
        "static"))


# ── report assembly ───────────────────────────────────────────────────────────

def build_report(flow_path: Path, gates_dir: Path, slot_types: Path,
                 latencies: Path, twin_report: dict | None,
                 cosim_report: dict | None, kata: str | None,
                 env_name: str | None = None,
                 env_hash: str | None = None) -> dict:
    spec = eval_mod.load_spec(flow_path)

    claims, _proof_raw = static_claims(flow_path, spec, gates_dir, slot_types)
    env_pin = None
    if env_name:
        env_pin, env_claim = environment_doc_pin(env_name, env_hash)
        claims.append(env_claim)
    if twin_report:
        claims += twin_claims(spec, twin_report, latencies)
    if cosim_report:
        claims += cosim_claims(cosim_report)

    provenance = {
        "kata": kata or flow_path.parent.parent.name,
        "flow": flow_path.name,
        "flow_version": spec.get("version"),
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pins": spec.get("pins"),
        "environment": "sandbox",   # measurement scope — always sandbox-bounded
    }
    if env_pin:
        # the TARGET environment of this translation (kata × env keying) —
        # distinct from the measurement scope above
        provenance["environment_doc"] = env_pin
    if twin_report:
        provenance["twin"] = {"runs": twin_report.get("runs"),
                              "seed": twin_report.get("seed")}

    return {
        "opis_evidence": SCHEMA_VERSION,
        "provenance": provenance,
        "verdict": verdict_block(spec, claims),
        "claims": claims,
        "gates": gate_slices(spec, claims, gates_dir),
    }


def render_md(report: dict) -> str:
    p, v = report["provenance"], report["verdict"]
    env_line = f"Generated {p['generated_utc']} · environment: {p['environment']}"
    if p.get("environment_doc"):
        ed = p["environment_doc"]
        env_line += (f" · target environment: {ed['name']} "
                     f"({(ed.get('hash') or '?')[:19]}…)")
    lines = [f"# Evidence — {p['kata']} {p['flow']}",
             "",
             env_line,
             "",
             f"**Overall: {v['overall']}** — requirements {v['requirements']}",
             ""]
    if v["failed"]:
        lines.append("## Falsified (conclusive — these assertions are FALSE)")
        lines.append("")
        lines += [f"- ✗ {f}" for f in v["failed"]]
        lines.append("")
    if v["caveats"]:
        lines.append("## Caveats (bounded / flagged — sandbox limits and advisories)")
        lines.append("")
        lines += [f"- {cv}" for cv in v["caveats"]]
        lines.append("")
    lines.append("## Contracts exercised")
    lines.append("")
    for key, sl in report["gates"].items():
        tags = sl["tags"]
        lines.append(f"- `{key}` ({tags['status']}, {tags['confidence']}) — "
                     f"instances: {', '.join(sl['instances'])}; "
                     f"{len(sl['claims'])} claim(s)")
    lines.append("")
    lines.append(f"_{len(report['claims'])} claims total; every claim carries "
                 f"an evidence pointer (see evidence JSON)._")
    return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("flow", type=Path)
    ap.add_argument("--gates-dir", type=Path, default=DEFAULT_GATES_DIR)
    ap.add_argument("--slot-types", type=Path, default=DEFAULT_SLOT_TYPES)
    ap.add_argument("--latencies", type=Path, default=DEFAULT_LATENCIES)
    ap.add_argument("--twin-report", type=Path)
    ap.add_argument("--cosim-report", type=Path)
    ap.add_argument("--kata")
    ap.add_argument("--environment",
                    help="target environment name (agents/environments/<name>.md) "
                         "— pinned into provenance.environment_doc")
    ap.add_argument("--env-hash",
                    help="sha256:… of the env doc AS THE TRANSLATION READ IT; "
                         "a mismatch with the on-disk doc flags the evidence "
                         "(advisory, kata-pin style)")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--no-md", action="store_true")
    args = ap.parse_args()

    twin = json.loads(args.twin_report.read_text()) if args.twin_report else None
    cosim = json.loads(args.cosim_report.read_text()) if args.cosim_report else None

    report = build_report(args.flow.resolve(), args.gates_dir, args.slot_types,
                          args.latencies, twin, cosim, args.kata,
                          env_name=args.environment, env_hash=args.env_hash)

    m = re.match(r"flow_v(\d+)$", args.flow.resolve().stem)
    suffix = f"_v{m.group(1)}" if m else ""
    out = args.out or args.flow.resolve().parent / f"evidence{suffix}.json"
    out.write_text(json.dumps(report, indent=1))
    print(f"  evidence report → {out}")
    if not args.no_md:
        md = out.with_suffix(".md")
        md.write_text(render_md(report))
        print(f"  summary         → {md}")
    print(f"  {report['verdict']['overall']} — "
          f"requirements {report['verdict']['requirements']}, "
          f"{len(report['claims'])} claims")
    return 0


if __name__ == "__main__":
    sys.exit(main())
