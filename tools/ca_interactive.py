#!/usr/bin/env python3
"""Interactive CA driver — token-conservation run (opis_workbench v1, 2026-07-06).

The two LLM stages are BYPASSED: schemas.json and main.rs were authored
interactively by Claude playing the model role, and are read from
workspace/opis_workbench/ca/v1/. Every verifier is the real machinery,
unchanged: schema_check, dep_check, wasm32-wasip1 build, gate harness,
da-twin baseline + full-substitution co-sim, evidence attach, commit.

This run is NOT agent-benchmark evidence: it proves the flow + contracts +
implementation, not the CA agent's prompts.

Run from repo root (needs cargo + wasm32-wasip1 + wasmtime + da-twin, all
present since the silicon v4 gauntlet):

    python tools/ca_interactive.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.ca.agent import CAAgent  # noqa: E402

KATA = "opis_workbench"


def main() -> None:
    agent = CAAgent(KATA)
    canned_main_rs = (agent.ca_dir / "main.rs").read_text()
    calls = {"n": 0}

    def fake_llm(system: str, user: str, max_tokens: int = 64000) -> str:
        calls["n"] += 1
        if calls["n"] > 1:
            print("  interactive run: a verifier rejected the canned main.rs — "
                  "stopping (no blind retry); paste the failure back to Claude")
            raise SystemExit(1)
        return canned_main_rs

    def load_schemas(contracts: str, history: dict, run_id: str) -> dict | None:
        doc = json.loads((agent.ca_dir / "schemas.json").read_text())
        ok, out = agent._run_schema_check()
        print("\n".join(f"    {l}" for l in out.strip().splitlines()[-2:]))
        if not ok:
            print("  schema_check FAILED — paste the output back to Claude")
            raise SystemExit(1)
        return doc

    agent._llm = fake_llm
    agent.stage_schemas = load_schemas
    agent.run()


if __name__ == "__main__":
    main()
