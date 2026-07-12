"""Real-execution adapter — ADR-005 (opis_workbench register, decided
2026-07-12): reality enters the simulation ONLY as recorded facts from
implementation runs at the world boundary. Levels stay separate:

  RECORD (the N=1 implementation run): each exec-map entry's command runs
  for real in a scratch copy of the environment; exit/stdout/duration are
  parsed into the schema-typed body and persisted as a TAPE, hash-pinned
  to the environment document it was cut against.

  SERVE (the simulation consuming recorded facts): a da-twin substitution
  process that answers the gate protocol for mapped resolver instances by
  replaying tape bodies — deterministic by construction (one recorded
  fact per gate, identical outputs every request). Never executes
  anything. Unmapped world-side pulses stay with the statistical wasm
  provider (serve-provider mode delegates to it unchanged).

Doctrine hooks: a stale tape is a quiet lie — replay verifies the tape's
env-doc pin and warns MOVED (advisory, kata-pin style). Failures print
their content and persist (falling trees). Nonzero exit is a FACT, not a
failure: eval.py exit 2 = warnings is a legal real answer.

Usage:
  python -m agents.ca.real_adapter record --kata K --env E
      [--exec-map F] [--tape F] [--scratch D]
  python -m agents.ca.real_adapter serve-gate --gate NAME
      --spec-json '<instance JSON>' --tape F
  python -m agents.ca.real_adapter serve-provider --tape F
      [--fallback-cmd-json '["wasmtime", ...]']

Exec map (workspace/<kata>/exec_map_<env>.json, golden recipe until CA
learns to emit it):
  {"opis_exec_map": 1, "kata": ..., "environment": ...,
   "gates": {"<Instance>": {
       "outcome": "<declared outcome>",
       "response_pulse_type": "<emitted type>",
       "exec": {"cmd": [...], "timeout_s": 120},
       "body": {... literals and "$captures" ...}}},
   "provider": {"<pulse_type>": {"exec": {...}, "body": {...}}}}
Captures: "$exit" (int), "$stdout" (str), "$duration_ms" (float),
"$stdout_json" (whole parsed stdout), "$stdout_json.dotted.path".
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ENVS_DIR = REPO_ROOT / "agents" / "environments"

TAPE_SCHEMA = 1
SCRATCH_IGNORE = shutil.ignore_patterns(
    ".git", "target", "__pycache__", "node_modules", "ca-build-*", "*.wasm")


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── body construction (capture DSL) ─────────────────────────────────────────

def _capture(token: str, facts: dict):
    if token == "$exit":
        return facts["exit"]
    if token == "$stdout":
        return facts["stdout"]
    if token == "$duration_ms":
        return facts["duration_ms"]
    if token == "$stdout_json" or token.startswith("$stdout_json."):
        obj = facts.get("stdout_json")
        if obj is None:
            raise ValueError(
                f"capture {token}: stdout was not parseable JSON "
                f"(first 200 chars: {facts['stdout'][:200]!r})")
        for part in token.split(".")[1:]:
            obj = obj[part]
        return obj
    raise ValueError(f"unknown capture token: {token}")


def build_body(spec, facts: dict):
    """Resolve a body spec: leaf strings starting with '$' are captures,
    everything else is literal. Recursive over dicts/lists."""
    if isinstance(spec, str) and spec.startswith("$"):
        return _capture(spec, facts)
    if isinstance(spec, dict):
        return {k: build_body(v, facts) for k, v in spec.items()}
    if isinstance(spec, list):
        return [build_body(v, facts) for v in spec]
    return spec


# ── record: the N=1 implementation run ──────────────────────────────────────

def make_scratch(scratch: Path) -> Path:
    """The capability bound: commands run in a throwaway copy of the repo,
    never in the real one. (git worktree would be lighter; a copy needs no
    git and cannot touch the origin by construction.)"""
    if scratch.exists():
        shutil.rmtree(scratch)
    print(f"  scratch copy: {REPO_ROOT} -> {scratch} ...")
    shutil.copytree(REPO_ROOT, scratch, ignore=SCRATCH_IGNORE, symlinks=True)
    return scratch


def run_exec(entry: dict, cwd: Path) -> dict:
    cmd = entry["exec"]["cmd"]
    timeout = entry["exec"].get("timeout_s", 120)
    t0 = time.monotonic()
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       timeout=timeout)
    dur = (time.monotonic() - t0) * 1000.0
    facts = {"exit": r.returncode, "stdout": r.stdout,
             "duration_ms": round(dur, 3)}
    try:
        facts["stdout_json"] = json.loads(r.stdout)
    except (json.JSONDecodeError, ValueError):
        facts["stdout_json"] = None
    if r.stderr.strip():
        # loud tree: stderr is content, print it — it may BE the fact
        print(f"    stderr ({len(r.stderr)} chars):")
        for line in r.stderr.strip().splitlines()[:10]:
            print(f"      {line}")
    return facts


def record(kata: str, env: str, exec_map_path: Path, tape_path: Path,
           scratch: Path) -> int:
    env_doc = ENVS_DIR / f"{env}.md"
    if not env_doc.exists():
        print(f"record: environment '{env}' has no document at {env_doc}")
        return 1
    exec_map = json.loads(exec_map_path.read_text())
    make_scratch(scratch)

    tape = {"opis_tape": TAPE_SCHEMA, "kata": kata,
            "environment": {"name": env,
                            "file": str(env_doc.relative_to(REPO_ROOT)),
                            "hash": _sha(env_doc)},
            "exec_map": {"file": str(exec_map_path),
                         "hash": _sha(exec_map_path)},
            "recorded_utc": _now(), "gates": {}, "provider": {}}
    failures = 0
    for section in ("gates", "provider"):
        for name, entry in (exec_map.get(section) or {}).items():
            print(f"  record [{section}] {name}: {' '.join(entry['exec']['cmd'])}")
            try:
                facts = run_exec(entry, scratch)
                body = build_body(entry["body"], facts)
            except Exception as e:  # noqa: BLE001 — record the failure loudly
                print(f"    RECORD FAILED: {e}")
                failures += 1
                continue
            rec = {"body": body,
                   "exec": {"cmd": entry["exec"]["cmd"],
                            "exit": facts["exit"],
                            "duration_ms": facts["duration_ms"],
                            "stdout_sha256": hashlib.sha256(
                                facts["stdout"].encode()).hexdigest(),
                            "stdout_bytes": len(facts["stdout"])}}
            if section == "gates":
                rec["outcome"] = entry["outcome"]
                rec["response_pulse_type"] = entry["response_pulse_type"]
            tape[section][name] = rec
            print(f"    exit {facts['exit']}, {facts['duration_ms']:.0f} ms, "
                  f"body fields: {sorted(body) if isinstance(body, dict) else type(body).__name__}")
    tape_path.parent.mkdir(parents=True, exist_ok=True)
    tape_path.write_text(json.dumps(tape, indent=2))
    n = len(tape["gates"]) + len(tape["provider"])
    print(f"  tape → {tape_path} ({n} entr{'y' if n == 1 else 'ies'}, "
          f"{failures} failure(s), env pin {tape['environment']['hash'][:19]}…)")
    return 1 if failures else 0


# ── tape loading + staleness advisory ────────────────────────────────────────

def load_tape(tape_path: Path) -> dict:
    tape = json.loads(tape_path.read_text())
    pin = tape.get("environment", {})
    doc = REPO_ROOT / pin.get("file", "")
    if doc.exists() and pin.get("hash") and _sha(doc) != pin["hash"]:
        # advisory, kata-pin style — a stale tape is a quiet lie unless loud
        print(f"!! TAPE STALE: env doc {pin['file']} has MOVED since this "
              f"tape was cut ({pin['hash'][:19]}… → {_sha(doc)[:19]}…) — "
              f"re-record before trusting sourced claims", file=sys.stderr)
    return tape


# ── serve-gate: da-twin gate protocol, replay only ───────────────────────────

def serve_gate(gate: str, spec: dict, tape: dict) -> None:
    entry = tape.get("gates", {}).get(gate)
    legal_outcomes = [e.get("outcome") for e in spec.get("emits", [])]
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        t0 = time.monotonic()
        try:
            req = json.loads(line)
            if entry is None:
                raise ValueError(f"gate {gate} not on tape")
            if entry["outcome"] not in legal_outcomes:
                raise ValueError(
                    f"tape outcome '{entry['outcome']}' not among declared "
                    f"outcomes {legal_outcomes}")
            inputs = req.get("inputs") or []
            if not inputs or all(i.get("body") is None for i in inputs):
                # starvation probe: legal response, nothing emitted —
                # replaying a fact nobody asked for would fabricate causality
                resp = {"outcome": entry["outcome"],
                        "service_ms": (time.monotonic() - t0) * 1000.0,
                        "outputs": []}
            else:
                resp = {"outcome": entry["outcome"],
                        "service_ms": (time.monotonic() - t0) * 1000.0,
                        "outputs": [{"pulse_type": entry["response_pulse_type"],
                                     "body": entry["body"]}]}
        except Exception as e:  # noqa: BLE001 — protocol: reply, never exit
            resp = {"error": str(e)}
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


# ── serve-provider: replay mapped pulse types, delegate the rest ─────────────

def serve_provider(tape: dict, fallback_cmd: list[str] | None) -> None:
    child = None
    if fallback_cmd:
        child = subprocess.Popen(fallback_cmd, stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, text=True)
    mapped = tape.get("provider", {})
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        resp: dict
        try:
            req = json.loads(line)
            pt = req.get("pulse_type")
            if pt in mapped:
                resp = {"body": mapped[pt]["body"]}
            elif child is not None:
                child.stdin.write(line + "\n")
                child.stdin.flush()
                out = child.stdout.readline()
                resp = json.loads(out) if out.strip() else {"body": None}
            else:
                resp = {"body": None}
        except Exception:  # noqa: BLE001 — protocol: reply, never exit
            resp = {"body": None}
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()
    if child is not None:
        child.stdin.close()
        child.wait(timeout=10)


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode", required=True)

    r = sub.add_parser("record")
    r.add_argument("--kata", required=True)
    r.add_argument("--env", required=True)
    r.add_argument("--exec-map", type=Path)
    r.add_argument("--tape", type=Path)
    r.add_argument("--scratch", type=Path)

    g = sub.add_parser("serve-gate")
    g.add_argument("--gate", required=True)
    g.add_argument("--spec-json", required=True)
    g.add_argument("--tape", type=Path, required=True)

    p = sub.add_parser("serve-provider")
    p.add_argument("--tape", type=Path, required=True)
    p.add_argument("--fallback-cmd-json")

    args = ap.parse_args()
    if args.mode == "record":
        kata_dir = REPO_ROOT / "workspace" / args.kata
        exec_map = args.exec_map or kata_dir / f"exec_map_{args.env}.json"
        tape = args.tape or kata_dir / f"tape_{args.env}.json"
        scratch = args.scratch or Path("/tmp") / f"opis-scratch-{args.kata}"
        return record(args.kata, args.env, exec_map, tape, scratch)
    if args.mode == "serve-gate":
        serve_gate(args.gate, json.loads(args.spec_json), load_tape(args.tape))
        return 0
    if args.mode == "serve-provider":
        fb = json.loads(args.fallback_cmd_json) if args.fallback_cmd_json else None
        serve_provider(load_tape(args.tape), fb)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
