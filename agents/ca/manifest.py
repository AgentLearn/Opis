"""Deterministic substitution-manifest derivation (no LLM).

flow spec + built wasm module → the manifest da-twin's SubPool consumes:

  {"gates": {"<Instance>": {"cmd": [...]}},
   "body_provider": {"cmd": [...]}}

Every substituted gate runs the SAME multi-template wasm module under
wasmtime (capability-denial: the guest sees only the env vars we pass),
parameterised by --gate + --spec-json from the flow instance. The body
provider is the same module in --provider mode. gate_harness.py probes
through this exact manifest, so what passes the harness is what the twin
spawns — one derivation, no drift.
"""
from __future__ import annotations

import json
from pathlib import Path


def _guest_cmd(wasmtime: str, wasm: Path, env: dict[str, str],
               guest_args: list[str]) -> list[str]:
    cmd = [wasmtime, "run"]
    for k, v in env.items():
        cmd.append(f"--env={k}={v}")
    cmd.append(str(wasm))
    cmd += guest_args
    return cmd


def derive_manifest(spec: dict, wasm: Path, run_secret: str,
                    wasmtime: str = "wasmtime",
                    gates: list[str] | None = None,
                    tamper_tokens: bool = False) -> dict:
    """gates=None → substitute every gate instance in the flow (full co-sim);
    pass a subset for progressive-substitution ladders."""
    env = {"DA_RUN_SECRET": run_secret}
    provider_env = dict(env)
    if tamper_tokens:
        provider_env["DA_TAMPER_TOKENS"] = "1"

    manifest: dict = {"gates": {}}
    for name, gspec in spec.get("gates", {}).items():
        if gates is not None and name not in gates:
            continue
        manifest["gates"][name] = {"cmd": _guest_cmd(
            wasmtime, wasm, env,
            ["--gate", name, "--spec-json", json.dumps(gspec, sort_keys=True)])}

    manifest["body_provider"] = {"cmd": _guest_cmd(
        wasmtime, wasm, provider_env, ["--provider"])}
    return manifest


def write_manifest(manifest: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2))
    return path


# ── crate scaffold ───────────────────────────────────────────────────────────
# Cargo.toml is POLICY, not creativity: the dependency set is exactly
# dep_check.py's allowlist intent (serde_json + HMAC stack, no proc-macros,
# no build.rs). The LLM only ever writes src/main.rs.

CARGO_TOML = """[package]
name = "gates-rs"
version = "0.1.0"
edition = "2021"

[[bin]]
name = "opis_gate"
path = "src/main.rs"

[dependencies]
serde_json = { version = "1", default-features = false, features = ["std"] }
hmac = "0.12"
sha2 = "0.10"
hex = "0.4"

[profile.release]
opt-level = "s"
strip = true
"""


def scaffold_crate(crate_dir: Path, main_rs: str) -> Path:
    (crate_dir / "src").mkdir(parents=True, exist_ok=True)
    (crate_dir / "Cargo.toml").write_text(CARGO_TOML)
    (crate_dir / "src" / "main.rs").write_text(main_rs)
    return crate_dir
