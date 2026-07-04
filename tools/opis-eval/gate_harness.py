#!/usr/bin/env python3
"""gate_harness — CA gate protocol verifier (unit level, no twin).

Probes each substituted gate through the SAME manifest da-twin uses, so what
passes here is exactly what the twin will spawn. Deterministic, no LLM: this
is the cheap inner check in CA's loop — a gate must survive the harness
before it earns a full co-sim run.

Usage:
  python3 tools/opis-eval/gate_harness.py <manifest.json> <flow_vN.json> [gate ...]

Probes per gate (contract read from the flow instance):
  1. LIVENESS      — spawns, answers a well-formed request within timeout
  2. SHAPE         — response has finite service_ms ≥ 0, outputs is a list of
                     {pulse_type, body}
  3. OUTCOME       — declared outcome name; outputs ⊆ that outcome's flows
  4. DETERMINISM   — identical request twice → identical outcome + outputs
                     (bodies included; service_ms may vary). Hermeticity's
                     cheap observable: wall-clock leakage shows up here.
  5. STARVATION    — request with NO inputs → still answers, doesn't crash
  6. GARBAGE       — malformed line → gate survives; next request answered

Input bodies come from the manifest's body_provider when present (mirroring
the twin), else null. Exit codes: 0 clean, 1 failures.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


class Proc:
    def __init__(self, cmd: list[str]):
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  text=True, bufsize=1)

    def ask(self, line: str, timeout: float = 10.0) -> str | None:
        try:
            self.p.stdin.write(line + "\n")
            self.p.stdin.flush()
        except (BrokenPipeError, OSError):
            return None
        import select
        r, _, _ = select.select([self.p.stdout], [], [], timeout)
        if not r:
            return None
        return self.p.stdout.readline().strip() or None

    def alive(self) -> bool:
        return self.p.poll() is None

    def kill(self):
        try:
            self.p.kill()
            self.p.wait(timeout=5)
        except Exception:
            pass


def make_request(gate: str, gspec: dict, provider: Proc | None, run: int = 0,
                 t_ms: float = 100.5) -> dict:
    inputs = []
    for req_type in gspec.get("requires", []):
        body = None
        if provider:
            resp = provider.ask(json.dumps({
                "v": 1, "run": run, "pulse_type": req_type,
                "t_ms": t_ms - 10.0, "consumer": gate}))
            if resp:
                try:
                    body = json.loads(resp).get("body")
                except json.JSONDecodeError:
                    body = None
        inputs.append({"pulse_type": req_type, "arrival_ms": t_ms - 10.0, "body": body})
    return {"v": 1, "run": run, "gate": gate, "t_ms": t_ms, "inputs": inputs}


def probe_gate(name: str, cmd: list[str], gspec: dict, provider: Proc | None) -> list[str]:
    fails: list[str] = []
    declared = {o.get("outcome"): o.get("flows", []) for o in gspec.get("emits", [])}

    try:
        g = Proc(cmd)
    except FileNotFoundError as e:
        return [f"spawn failed: {e}"]

    try:
        req = make_request(name, gspec, provider)
        line = json.dumps(req)

        # 1. liveness
        resp_raw = g.ask(line)
        if resp_raw is None:
            return [f"no response to well-formed request within timeout"
                    + ("" if g.alive() else " (process died)")]

        # 2. shape
        try:
            resp = json.loads(resp_raw)
        except json.JSONDecodeError:
            return [f"response is not JSON: {resp_raw[:120]}"]
        svc = resp.get("service_ms")
        if not isinstance(svc, (int, float)) or svc < 0:
            fails.append(f"invalid service_ms: {svc!r}")
        outputs = resp.get("outputs", [])
        if not isinstance(outputs, list) or any(
                not isinstance(o, dict) or "pulse_type" not in o for o in outputs):
            fails.append(f"outputs malformed: {outputs!r:.120}")
            outputs = []

        # 3. outcome legality + output conformance
        outcome = resp.get("outcome")
        if declared:
            if outcome not in declared:
                fails.append(f"undeclared outcome '{outcome}' (declared: {sorted(declared)})")
            else:
                stray = [o["pulse_type"] for o in outputs
                         if o["pulse_type"] not in declared[outcome]]
                if stray:
                    fails.append(f"outputs {stray} not in outcome '{outcome}' flows "
                                 f"{declared[outcome]}")

        # 4. determinism (same request, bodies included)
        resp2_raw = g.ask(line)
        if resp2_raw is None:
            fails.append("no response on repeat request")
        else:
            try:
                resp2 = json.loads(resp2_raw)
                a = (resp.get("outcome"), json.dumps(resp.get("outputs"), sort_keys=True))
                b = (resp2.get("outcome"), json.dumps(resp2.get("outputs"), sort_keys=True))
                if a != b:
                    fails.append("nondeterministic: identical request produced different "
                                 "outcome/outputs — wall-clock or hidden-state leakage")
            except json.JSONDecodeError:
                fails.append("repeat response not JSON")

        # 5. starvation
        starved = dict(req, inputs=[])
        r5 = g.ask(json.dumps(starved))
        if r5 is None:
            fails.append("crashed or hung on empty-inputs request")

        # 6. garbage resilience
        g.ask("{this is not json", timeout=2.0)  # response optional
        r6 = g.ask(line)
        if r6 is None:
            fails.append("died after malformed input line — must skip and continue")

    finally:
        g.kill()
    return fails


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    manifest = json.loads(Path(sys.argv[1]).read_text())
    flow = json.loads(Path(sys.argv[2]).read_text())
    selected = sys.argv[3:] or list(manifest.get("gates", {}))

    provider = None
    bp = manifest.get("body_provider", {}).get("cmd")
    if bp:
        try:
            provider = Proc(bp)
        except FileNotFoundError:
            print("  ⚠ body provider failed to spawn — probing with null bodies")

    print(f"\nopis-gate-harness  {len(selected)} gate(s)")
    total_fails = 0
    for name in selected:
        entry = manifest["gates"].get(name)
        gspec = flow["gates"].get(name)
        if not entry or not gspec:
            print(f"  ✗ {name}: missing from manifest or flow")
            total_fails += 1
            continue
        fails = probe_gate(name, entry["cmd"], gspec, provider)
        if fails:
            total_fails += len(fails)
            for f in fails:
                print(f"  ✗ {name}: {f}")
        else:
            print(f"  ✓ {name}: liveness, shape, outcome, determinism, starvation, garbage")

    if provider:
        provider.kill()
    print(f"\n{total_fails} failure(s)")
    sys.exit(1 if total_fails else 0)


if __name__ == "__main__":
    main()
