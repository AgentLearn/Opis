#!/usr/bin/env python3
"""dep_check — CA dependency-policy verifier.

wasmtime sandboxes gate EXECUTION (capability-based: no net, no fs unless
granted), but `cargo build` still runs on the host — and build scripts and
proc-macros execute arbitrary host code at COMPILE time. This check closes
that hole for CA-generated crates: untrusted code must be buildable without
executing anything.

Usage:
  python3 tools/opis-eval/dep_check.py <crate_dir> [crate_dir ...]

Policy (any violation = error):
  1. no build.rs anywhere in the crate
  2. no [build-dependencies] in any Cargo.toml
  3. every dependency (transitive, via Cargo.lock) is on the allowlist
  4. no allowlisted crate is used with a feature known to pull proc-macros
     (e.g. serde/derive)

The allowlist is deliberately tiny — gates are JSON-in/JSON-out decision
logic. Extending it is a reviewed product change, not a CA decision.

Exit codes: 0 clean, 1 violations.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# crates vetted as: no build.rs of consequence for wasi, no proc-macros,
# pure-Rust. (serde_json vendors no derive; ryu/itoa/memchr are its deps.)
ALLOWLIST = {
    "gates-rs",           # the crate itself
    "serde_json", "serde", "serde_core", "ryu", "zmij", "itoa", "memchr",
    "hmac", "sha2", "hex",
    "digest", "crypto-common", "block-buffer", "generic-array",
    "subtle", "typenum", "cpufeatures", "libc", "cfg-if", "version_check",
}
# features that pull proc-macro machinery
FORBIDDEN_FEATURES = {("serde", "derive")}


def check_crate(crate: Path) -> list[str]:
    errors: list[str] = []

    for br in crate.rglob("build.rs"):
        if "target" not in br.parts:
            errors.append(f"{crate.name}: build script present: {br.relative_to(crate)}")

    for toml in crate.rglob("Cargo.toml"):
        if "target" in toml.parts:
            continue
        text = toml.read_text()
        if re.search(r"^\[build-dependencies", text, re.MULTILINE):
            errors.append(f"{crate.name}: [build-dependencies] in {toml.relative_to(crate)}")
        for dep, feat in FORBIDDEN_FEATURES:
            block = re.search(
                rf'^{dep}\s*=\s*\{{[^}}]*features\s*=\s*\[([^\]]*)\]', text, re.MULTILINE)
            if block and f'"{feat}"' in block.group(1):
                errors.append(
                    f"{crate.name}: dependency '{dep}' uses forbidden feature '{feat}' "
                    f"(proc-macro at build time)")

    # Transitive dependency audit. `cargo tree` reflects actual feature
    # resolution (Cargo.lock over-approximates: it records OPTIONAL deps like
    # serde's derive machinery even when the feature is off and they never
    # compile). Both normal and build edges are audited for the wasi target.
    import subprocess
    try:
        r = subprocess.run(
            ["cargo", "tree", "--prefix", "none", "-e", "normal,build",
             "--target", "wasm32-wasip1"],
            cwd=crate, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            errors.append(f"{crate.name}: cargo tree failed — {r.stderr.strip()[:200]}")
        else:
            pkgs = {line.split()[0] for line in r.stdout.splitlines() if line.strip()}
            off = sorted(pkgs - ALLOWLIST)
            if off:
                errors.append(
                    f"{crate.name}: crates outside the allowlist (resolved deps): {off} "
                    f"— extending the allowlist is a reviewed product change")
    except FileNotFoundError:
        errors.append(f"{crate.name}: cargo not available — dependency audit requires "
                      f"a build environment")
    except subprocess.TimeoutExpired:
        errors.append(f"{crate.name}: cargo tree timed out")

    return errors


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    all_errors: list[str] = []
    for arg in sys.argv[1:]:
        all_errors += check_crate(Path(arg).resolve())
    print(f"\nopis-dep-check  {len(sys.argv) - 1} crate(s)")
    for e in all_errors:
        print(f"  ✗ {e}")
    if not all_errors:
        print("  ✓ no build scripts, no build-deps, all dependencies allowlisted")
    sys.exit(1 if all_errors else 0)


if __name__ == "__main__":
    main()
