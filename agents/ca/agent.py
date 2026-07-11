"""CA — Component Architect agent (dev lead).

Flow-scoped, not gate-scoped. Takes a PROVED flow version (pins and all)
and drives it to a running co-sim with real decision logic:

  schemas → schema_check → gate codegen → dep_check → wasm build
          → gate_harness → co-sim (da-twin) → evidence report

Doctrine (see OpisDescription):
- Translation failure = falsified gate description. CA never invents a
  field to make a contract implementable; it reports and stops. That report
  is the product, not the failure.
- All CA outputs are EPHEMERAL (workspace/<kata>/ca/, gitignored) —
  regenerated per run. Only evidence reports persist.
- CA-generated code executes ONLY as wasm32-wasip1 under wasmtime;
  dep_check closes the compile-time hole (no build.rs / proc-macros).
- Sandbox measurements are a feasibility verdict + lower bounds: falsify
  confidently, validate weakly.
"""

import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from .prompts import (SCHEMA_PROMPT, GATE_CODEGEN_PROMPT,
                      build_schema_user_prompt, build_codegen_user_prompt)
from .manifest import derive_manifest, write_manifest, scaffold_crate

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "agents"
TOOLS_DIR = REPO_ROOT / "tools"

MODEL = os.environ.get("CA_MODEL", "claude-fable-5")  # translation + codegen: the hard reasoning

MAX_SCHEMA_ITERATIONS = 3
MAX_CODE_ITERATIONS = 4   # dep_check + build + harness failures all feed this loop
COSIM_RUNS = int(os.environ.get("CA_COSIM_RUNS", "1000"))
COSIM_SEED = int(os.environ.get("CA_COSIM_SEED", "42"))
WASM_TARGET = "wasm32-wasip1"


class CAAgent:
    def __init__(self, kata_name: str):
        self.kata_name = kata_name
        self.kata_dir = REPO_ROOT / "workspace" / kata_name
        self.flow_path, self.flow_version = self._resolve_flow()
        self.spec = json.loads(self.flow_path.read_text())
        # ephemeral record dir (gitignored); actual cargo build happens in a
        # host temp dir — cargo cannot build inside a restricted mount, and
        # ephemerals don't belong in the workspace repo anyway.
        self.ca_dir = self.kata_dir / "ca" / f"v{self.flow_version}"
        self.ca_dir.mkdir(parents=True, exist_ok=True)
        self.build_dir = Path(os.environ.get("CA_BUILD_DIR",
                              tempfile.gettempdir())) / f"ca-build-{kata_name}"
        self.run_secret = secrets.token_hex(16)
        # One run id per invocation, shared by every spend-ledger line
        # (2026-07-11, REQ-20: spend was persisted nowhere — CA falsified it).
        self._run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        self.client = anthropic.Anthropic(
            http_client=httpx.Client(verify=False, proxy=proxy))

    def _record_spend(self, stage: str, response, iteration: int | None = None) -> None:
        """Append one line per LLM call to the kata's append-only spend
        ledger (workspace/<kata>/spend_ledger.jsonl) — same shape and file
        as FA's. Best-effort, loud-on-fail, never kills a run."""
        try:
            u = getattr(response, "usage", None)
            line = json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "agent": "ca",
                "run_id": self._run_id,
                "kata": self.kata_name,
                "stage": stage,
                "iteration": iteration,
                "model": getattr(response, "model", None),
                "input_tokens": getattr(u, "input_tokens", None),
                "output_tokens": getattr(u, "output_tokens", None),
                "stop_reason": getattr(response, "stop_reason", None),
            })
            path = self.kata_dir / "spend_ledger.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a") as fh:
                fh.write(line + "\n")
        except Exception as e:  # noqa: BLE001 — ledger must not fail a run
            print(f"  ⚠ spend ledger write failed (run continues): {e}")

    # ── flow resolution ────────────────────────────────────────────────────

    def _resolve_flow(self) -> tuple[Path, int]:
        """CA only ever works a COMMITTED, proved flow version. The scratch
        _iterating.json is FA's business — refusing it here keeps CA from
        implementing a flow that never passed proof."""
        flow_dir = self.kata_dir / "flow"
        cur = flow_dir / "flow_current.json"
        if cur.exists():
            target = cur.resolve()
            m = re.match(r"flow_v(\d+)$", target.stem)
            if m:
                return target, int(m.group(1))
        versions = []
        for p in flow_dir.glob("flow_v*.json"):
            m = re.match(r"flow_v(\d+)$", p.stem)
            if m:
                versions.append((int(m.group(1)), p))
        if versions:
            v, p = max(versions)
            return p, v
        raise SystemExit(
            f"CA: no committed flow for kata '{self.kata_name}' "
            f"(only FA's scratch file, if anything). Run FA to a proved "
            f"flow_vN.json first — CA implements proved flows only.")

    # ── shared plumbing (same trio FA uses: pin, guard, extractor) ─────────

    @staticmethod
    def _response_text(response) -> str:
        """Concatenate TEXT blocks. Fable-class models prepend ThinkingBlocks;
        content[0].text blows up on those."""
        return "".join(
            b.text for b in response.content if getattr(b, "type", "") == "text")

    _model_verified = False

    def _verify_served_model(self, response) -> None:
        if CAAgent._model_verified:
            return
        served = getattr(response, "model", "")
        if not served.startswith(MODEL):
            print(f"  !! MODEL MISMATCH: pinned '{MODEL}' but API served "
                  f"'{served}' — check the model string / account access")
        else:
            print(f"  model verified: {served}")
        CAAgent._model_verified = True

    def _llm(self, system: str, user: str, max_tokens: int = 64000,
             stage: str = "llm", iteration: int | None = None) -> str:
        # Streaming mandatory at this budget; thinking + a full Rust file
        # must both fit (8192 starved FA's text entirely — same trap here;
        # 32000 truncated codegen mid-expression when thinking ran long,
        # 2026-07-06 — a full multi-template main.rs is ~30KB of text ALONE).
        with self.client.messages.stream(
            model=MODEL, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            response = stream.get_final_message()
        self._record_spend(stage, response, iteration=iteration)
        self._verify_served_model(response)
        text = self._response_text(response)
        if not text.strip():
            kinds = [getattr(b, "type", "?") for b in response.content]
            print(f"  !! empty text from model — stop_reason="
                  f"{response.stop_reason}, blocks={kinds}")
        elif response.stop_reason == "max_tokens":
            # loud tree: a truncated file WILL fail the compiler with a
            # misleading "unclosed delimiter" — name the real cause here
            print(f"  !! response TRUNCATED at max_tokens={max_tokens} "
                  f"({len(text)} chars of text) — output incomplete")
        return text

    def _extract_json(self, text: str) -> dict:
        match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
        if match:
            return json.loads(match.group(1))
        stripped = text.strip()
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
        decoder = json.JSONDecoder()
        for i, ch in enumerate(stripped):
            if ch != "{":
                continue
            try:
                obj, _ = decoder.raw_decode(stripped, i)
                return obj
            except json.JSONDecodeError:
                continue
        return json.loads(stripped)

    @staticmethod
    def _extract_rust(text: str) -> str:
        """The codegen prompt forbids fences, but strip one if it sneaks in."""
        m = re.search(r"```(?:rust)?\s*\n([\s\S]+?)\n```", text)
        return (m.group(1) if m else text).strip() + "\n"

    def _workspace_commit(self, message: str) -> None:
        """Local workspace-repo bookkeeping — never fails the run."""
        root = self.kata_dir.parent
        if not (root / ".git").exists():
            print("  (workspace repo not initialised — skipping local commit)")
            return
        try:
            subprocess.run(["git", "-C", str(root), "add", "-A"],
                           check=True, capture_output=True, timeout=30)
            r = subprocess.run(["git", "-C", str(root), "commit", "-m", message],
                               capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                print(f"  workspace repo: committed — {message}")
            elif "nothing to commit" in (r.stdout + r.stderr):
                print("  workspace repo: nothing new to commit")
            else:
                print(f"  workspace repo: commit failed — {r.stderr.strip()[:200]}")
        except Exception as e:  # noqa: BLE001
            print(f"  workspace repo: git unavailable — {e}")

    # ── defect history (persisted across CA invocations, FA pattern) ───────

    def _history_path(self) -> Path:
        return self.kata_dir / "ca_defect_history.json"

    def _load_history(self) -> dict:
        try:
            return json.loads(self._history_path().read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_history(self, h: dict) -> None:
        self._history_path().write_text(json.dumps(h, indent=2, sort_keys=True))

    @staticmethod
    def _defect_key(stage: str, line: str) -> str:
        norm = re.sub(r"\d+", "N", line.strip().lower())
        return f"{stage}:{hashlib.md5(norm.encode()).hexdigest()[:12]}"

    def _touch(self, history: dict, stage: str, line: str, run_id: str) -> None:
        key = self._defect_key(stage, line)
        now = datetime.now(timezone.utc).isoformat()
        e = history.get(key)
        if e is None:
            history[key] = {"stage": stage, "line": line, "status": "outstanding",
                            "times_seen": 1, "reopened_count": 0,
                            "first_seen": now, "last_seen": now, "runs_seen": [run_id]}
            return
        e.update(line=line, last_seen=now, times_seen=e.get("times_seen", 0) + 1)
        if run_id not in e.get("runs_seen", []):
            e.setdefault("runs_seen", []).append(run_id)
        if e["status"] == "fixed":
            e["reopened_count"] = e.get("reopened_count", 0) + 1
        e["status"] = "outstanding"

    @staticmethod
    def _close_stage(history: dict, stage: str, run_id: str) -> int:
        n = 0
        for e in history.values():
            if e.get("stage") == stage and e["status"] == "outstanding":
                e["status"] = "fixed"
                e["last_fixed"] = datetime.now(timezone.utc).isoformat()
                e.setdefault("runs_fixed", []).append(run_id)
                n += 1
        return n

    @staticmethod
    def _format_errors(lines: list[str]) -> str:
        return "\n".join(f"- {l}" for l in lines)

    # ── context loading ────────────────────────────────────────────────────

    def _used_templates(self) -> list[str]:
        return sorted({g.get("gate_template") for g in
                       self.spec.get("gates", {}).values() if g.get("gate_template")})

    @staticmethod
    def _pins_module():
        """Load tools/opis-eval/pins.py by file path (hyphen-dir, same dance
        as FA's loaders)."""
        import importlib.util
        pins_path = TOOLS_DIR / "opis-eval" / "pins.py"
        spec = importlib.util.spec_from_file_location("opis_pins", pins_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules.setdefault("opis_pins", mod)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod

    def _load_gate_contracts(self) -> str:
        """The contracts CA implements are the ones the flow was PROVED
        against — resolved through the pin block (archive-aware), never
        blindly the current files. An amendment landing between FA's commit
        and CA's run must not silently change what CA builds."""
        pins_mod = self._pins_module()
        pinned = (self.spec.get("pins") or {}).get("gates") or {}
        chunks, missing = [], []
        for t in self._used_templates():
            pin = pinned.get(t)
            p = pins_mod.contract_path(AGENTS_DIR / "gates", t,
                                       pin.get("version") if pin else None)
            if p.exists():
                chunks.append(f"### {t}\n{p.read_text()}")
            else:
                missing.append(f"{t} (v{pin.get('version') if pin else '?'})")
        if missing:
            raise SystemExit(f"CA: pinned contract(s) unresolvable: {missing}")
        return "\n\n".join(chunks)

    # ── preflight ──────────────────────────────────────────────────────────

    def preflight(self) -> dict:
        caps = {"cargo": shutil.which("cargo"), "wasmtime": shutil.which("wasmtime"),
                "wasm_target": False, "twin": None}
        if caps["cargo"]:
            r = subprocess.run(["rustup", "target", "list", "--installed"],
                               capture_output=True, text=True)
            caps["wasm_target"] = WASM_TARGET in (r.stdout or "")
        for cand in [os.environ.get("DA_TWIN_BIN"),
                     REPO_ROOT / "agents" / "target" / "release" / "da-twin",
                     Path("/tmp/da-build/target/release/da-twin")]:
            if cand and Path(cand).exists():
                caps["twin"] = str(cand)
                break
        missing = [k for k in ("cargo", "wasmtime", "wasm_target", "twin") if not caps[k]]
        if missing:
            print(f"  preflight: MISSING {missing} — recipe:")
            print("    cargo:       curl https://sh.rustup.rs -sSf | sh -s -- -y --profile minimal")
            print(f"    wasm_target: rustup target add {WASM_TARGET}")
            print("    wasmtime:    brew install wasmtime  (or https://wasmtime.dev)")
            print("    twin:        cargo build -p da-twin --release  "
                  "(outside the mount if sandboxed; export DA_TWIN_BIN=<path>)")
        else:
            print("  preflight: cargo, wasm target, wasmtime, da-twin all present")
        return caps

    # ── stage 1: schema translation ────────────────────────────────────────

    def _schemas_path(self) -> Path:
        return self.ca_dir / "schemas.json"

    def _run_schema_check(self) -> tuple[bool, str]:
        r = subprocess.run(
            [sys.executable, str(TOOLS_DIR / "opis-eval" / "schema_check.py"),
             str(self._schemas_path()), str(self.flow_path)],
            capture_output=True, text=True)
        return r.returncode != 1, (r.stdout + r.stderr)

    def stage_schemas(self, contracts: str, history: dict, run_id: str) -> dict | None:
        """Returns the schema doc, or None (falsified / exhausted)."""
        slot_types = (AGENTS_DIR / "slot_types" / "index.md").read_text()
        flow_json = json.dumps(self.spec, indent=1)
        errors = ""
        for it in range(1, MAX_SCHEMA_ITERATIONS + 1):
            print(f"  schemas: iteration {it}/{MAX_SCHEMA_ITERATIONS}...")
            raw = self._llm(SCHEMA_PROMPT, build_schema_user_prompt(
                flow_json, contracts, slot_types, errors),
                stage="schemas", iteration=it)
            try:
                doc = self._extract_json(raw)
            except json.JSONDecodeError as e:
                errors = self._format_errors([f"response was not parseable JSON: {e}"])
                continue

            if doc.get("falsified"):
                # The cheap pre-code test fired: a contract decision can't be
                # carried. This is a RESULT — escalate to the user, stop.
                # evidence-class, so OUTSIDE the gitignored ca/ dir: a
                # falsification survives even though the run's artifacts don't
                path = self.kata_dir / f"ca_falsification_v{self.flow_version}.md"
                lines = [f"# CA falsification report — {self.kata_name} "
                         f"flow_v{self.flow_version}",
                         "", "Schema translation found gate-contract decisions that no",
                         "derivable message field can carry. The contract(s) below are",
                         "candidates for demotion/amendment (ADR), not for implementation.", ""]
                for f in doc["falsified"]:
                    lines += [f"## {f.get('gate_template')}",
                              f"- decision: {f.get('decision')}",
                              f"- why untranslatable: {f.get('why_untranslatable')}", ""]
                path.write_text("\n".join(lines))
                print(f"  FALSIFIED — {len(doc['falsified'])} contract decision(s) "
                      f"untranslatable. Report: {path}")
                self._workspace_commit(
                    f"CA: {self.kata_name} v{self.flow_version} — falsification report")
                return None

            self._schemas_path().write_text(json.dumps(doc, indent=2))
            ok, out = self._run_schema_check()
            print("\n".join(f"    {l}" for l in out.strip().splitlines()[-4:]))
            if ok:
                self._close_stage(history, "schema", run_id)
                self._save_history(history)
                return doc
            err_lines = [l.strip() for l in out.splitlines() if "✗" in l]
            for l in err_lines:
                self._touch(history, "schema", l, run_id)
            self._save_history(history)
            errors = self._format_errors(err_lines)
        print("  schemas: iteration budget exhausted — outstanding defects persisted")
        return None

    # ── stage 2: codegen → dep_check → wasm build → harness ────────────────

    def _wasm_path(self) -> Path:
        return self.build_dir / "target" / WASM_TARGET / "release" / "opis_gate.wasm"

    def _build_wasm(self) -> tuple[bool, str]:
        r = subprocess.run(
            ["cargo", "build", "--release", "--target", WASM_TARGET],
            cwd=self.build_dir, capture_output=True, text=True, timeout=600)
        return r.returncode == 0, (r.stdout + r.stderr)

    def _run_dep_check(self) -> tuple[bool, str]:
        r = subprocess.run(
            [sys.executable, str(TOOLS_DIR / "opis-eval" / "dep_check.py"),
             str(self.build_dir)],
            capture_output=True, text=True)
        return r.returncode == 0, (r.stdout + r.stderr)

    def _run_harness(self, manifest_path: Path) -> tuple[bool, str]:
        env = dict(os.environ, DA_RUN_SECRET=self.run_secret)
        r = subprocess.run(
            [sys.executable, str(TOOLS_DIR / "opis-eval" / "gate_harness.py"),
             str(manifest_path), str(self.flow_path)],
            capture_output=True, text=True, env=env, timeout=600)
        return r.returncode == 0, (r.stdout + r.stderr)

    def stage_code(self, schemas: dict, contracts: str, caps: dict,
                   history: dict, run_id: str) -> Path | None:
        """Returns the harness-passing manifest path, or None."""
        # PRE-CODE FALSIFICATION CHECK (2026-07-06, silent-rejection class):
        # an auth-verifying instance whose declared outcomes offer no
        # rejection channel CANNOT reject visibly — generated code is forced
        # into success-named-outcome-with-empty-outputs (flow_v3 MenuWriter:
        # HMAC verified correctly, forgery invisible to every observer).
        # This is a flow/contract translation defect; refuse before codegen.
        silent = []
        for name, g in self.spec.get("gates", {}).items():
            if not g.get("auth_required"):
                continue
            if len(g.get("emits", [])) < 2:
                only = [e.get("outcome") for e in g.get("emits", [])]
                silent.append(f"{name} (outcomes: {only})")
        if silent:
            for s in silent:
                print(f"    ✗ auth-verifying instance has NO rejection outcome "
                      f"— rejection would be silent: {s}")
                self._touch(history, "code",
                            f"silent-rejection: {s}", run_id)
            self._save_history(history)
            print("    codegen REFUSED — the flow must wire a rejection "
                  "outcome for every auth-verifying instance (contract "
                  "already demands one); FA-level fix, not codegen's")
            return None
        flow_json = json.dumps(self.spec, indent=1)
        schemas_json = json.dumps(schemas, indent=1)
        manifest_path = self.ca_dir / "manifest.json"
        errors = ""
        for it in range(1, MAX_CODE_ITERATIONS + 1):
            print(f"  codegen: iteration {it}/{MAX_CODE_ITERATIONS}...")
            raw = self._llm(GATE_CODEGEN_PROMPT, build_codegen_user_prompt(
                flow_json, schemas_json, contracts, errors),
                stage="codegen", iteration=it)
            # raw persisted BEFORE extraction — when extraction/compile goes
            # wrong, the model's actual output is the primary evidence
            (self.ca_dir / f"response_codegen_iter{it}.txt").write_text(raw)
            main_rs = self._extract_rust(raw)
            scaffold_crate(self.build_dir, main_rs)
            (self.ca_dir / "main.rs").write_text(main_rs)  # ephemeral record
            # per-iteration copy so persisted failure outputs point at the
            # exact code that produced them (main.rs is overwritten each round)
            (self.ca_dir / f"main_iter{it}.rs").write_text(main_rs)

            if not (caps["cargo"] and caps["wasm_target"]):
                # a missing toolchain is an ENVIRONMENT problem, not a code
                # defect — don't burn LLM iterations on it
                print("    build BLOCKED — toolchain missing (see preflight); "
                      "main.rs + schemas written, stopping here")
                return None

            ok, out = self._run_dep_check()
            if not ok:
                errs = [l.strip() for l in out.splitlines() if l.strip()][-10:]
                print(f"    dep_check FAILED ({len(errs)} line(s))")
                for l in errs[:5]:
                    print(f"      {l}")
                # evidence discipline applies to failures most of all
                # (2026-07-06): full output persisted per iteration
                (self.ca_dir / f"depcheck_failure_iter{it}.txt").write_text(out)
                for l in errs:
                    self._touch(history, "code", f"dep_check: {l}", run_id)
                self._save_history(history)
                errors = "dep_check violations (dependency policy is not "\
                         "negotiable):\n" + self._format_errors(errs)
                continue
            ok, out = self._build_wasm()
            if not ok:
                # feed back only error lines — full cargo noise drowns the model
                errs = [l for l in out.splitlines()
                        if re.match(r"\s*(error|warning: unused)", l)][:30]
                print(f"    wasm build FAILED ({len(errs)} error line(s))")
                for l in errs[:5]:
                    print(f"      {l}")
                # full cargo output persisted per iteration — the console
                # count alone made failures undiagnosable (2026-07-06)
                (self.ca_dir / f"build_failure_iter{it}.txt").write_text(out)
                self._touch(history, "code", errs[0] if errs else "build failed", run_id)
                self._save_history(history)
                errors = "cargo build --target " + WASM_TARGET + \
                         " failed:\n" + self._format_errors(errs or [out[-2000:]])
                continue

            write_manifest(derive_manifest(
                self.spec, self._wasm_path(), self.run_secret,
                wasmtime=caps["wasmtime"] or "wasmtime"), manifest_path)
            ok, out = self._run_harness(manifest_path)
            (self.ca_dir / "harness_report.txt").write_text(out)
            if ok:
                print("    gate_harness: all probes pass")
                self._close_stage(history, "code", run_id)
                self._save_history(history)
                return manifest_path
            fails = [l.strip() for l in out.splitlines()
                     if "FAIL" in l or "✗" in l][:20]
            print(f"    gate_harness FAILED ({len(fails)} probe(s))")
            for l in fails[:5]:
                print(f"      {l}")
            (self.ca_dir / f"harness_failure_iter{it}.txt").write_text(out)
            for l in fails:
                self._touch(history, "code", f"harness: {l}", run_id)
            self._save_history(history)
            errors = "gate_harness probe failures (liveness/shape/outcome-"\
                     "legality/determinism/starvation/garbage):\n" + \
                     self._format_errors(fails)
        print("  codegen: iteration budget exhausted — outstanding defects persisted")
        return None

    # ── stage 3: co-sim + evidence ──────────────────────────────────────────

    def _run_twin(self, twin: str, report: Path,
                  manifest: Path | None = None,
                  tamper_sigs: bool = False) -> tuple[bool, str]:
        cmd = [twin, "--spec", str(self.flow_path), "--runs", str(COSIM_RUNS),
               "--seed", str(COSIM_SEED), "--report", str(report)]
        if manifest:
            cmd += ["--substitutions", str(manifest)]
        if tamper_sigs:
            # forge on the WIRE, not at the provider: a real substituted
            # sentinel signs valid tokens with the real secret in both runs,
            # so provider-level tampering never forges anything (2026-07-06)
            cmd += ["--tamper-sigs"]
        env = dict(os.environ, DA_RUN_SECRET=self.run_secret)
        r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=900)
        return r.returncode == 0, (r.stdout + r.stderr)

    def stage_cosim(self, manifest_path: Path, caps: dict) -> Path | None:
        twin = caps["twin"]
        baseline = self.ca_dir / "twin_baseline.json"
        cosim = self.ca_dir / "twin_cosim.json"
        print(f"  co-sim: baseline twin run ({COSIM_RUNS} runs, seed {COSIM_SEED})...")
        ok, out = self._run_twin(twin, baseline)
        if not ok:
            print(f"    baseline twin FAILED: {out[-400:]}")
            return None
        print("  co-sim: full-substitution run...")
        ok, out = self._run_twin(twin, cosim, manifest_path)
        if not ok:
            print(f"    co-sim twin FAILED: {out[-400:]}")
            return None

        base = json.loads(baseline.read_text())
        real = json.loads(cosim.read_text())
        dead = real.get("dead_gates", [])
        failures = [f"dead gate under substitution: {g}" for g in dead]

        # negative path: if the flow claims auth, tampered tokens MUST change
        # behavior. Identical fire% under tampering = the auth isn't real.
        auth_gates = [n for n, g in self.spec.get("gates", {}).items()
                      if g.get("auth_required")]
        tamper_delta = None
        outcome_delta = None
        if auth_gates:
            print("  co-sim: negative-path run (tampered tokens)...")
            tampered_manifest = self.ca_dir / "manifest_tampered.json"
            write_manifest(derive_manifest(
                self.spec, self._wasm_path(), self.run_secret,
                wasmtime=caps["wasmtime"] or "wasmtime", tamper_tokens=True),
                tampered_manifest)
            tampered = self.ca_dir / "twin_tampered.json"
            ok, out = self._run_twin(twin, tampered, tampered_manifest,
                                     tamper_sigs=True)
            if ok:
                tamp = json.loads(tampered.read_text())
                def fires(rep):
                    return {n: g.get("fire_pct", 0.0)
                            for n, g in rep.get("gates", {}).items()}
                def outcomes(rep):
                    return {n: g.get("outcomes", {})
                            for n, g in rep.get("gates", {}).items()}
                fr, ft = fires(real), fires(tamp)
                tamper_delta = sum(abs(fr.get(n, 0) - ft.get(n, 0)) for n in fr)
                # OUTCOME diff, not just fire%: a verifying gate may fire
                # identically but DECIDE differently (silent-rejection class,
                # 2026-07-06 — MenuWriter verified HMAC yet Δfire%=0). Needs
                # a twin that reports per-gate outcome tallies.
                oreal, otamp = outcomes(real), outcomes(tamp)
                outcome_delta = sum(
                    abs(oreal.get(n, {}).get(o, 0) - otamp.get(n, {}).get(o, 0))
                    for n in set(oreal) | set(otamp)
                    for o in set(oreal.get(n, {})) | set(otamp.get(n, {})))
                have_outcomes = any(oreal.values()) or any(otamp.values())
                # DEGENERATE-BASELINE GUARD: if the co-sim itself is half dead,
                # "tampering changed nothing" is expected and proves nothing.
                degenerate = bool(dead)
                if tamper_delta == 0 and outcome_delta == 0:
                    if degenerate:
                        failures.append(
                            "tamper check INCONCLUSIVE: no behavior change, but "
                            f"the co-sim baseline is degenerate ({len(dead)} dead "
                            "gate(s)) — fix the flow first, then re-judge authZ")
                    elif not have_outcomes:
                        failures.append(
                            "tamper check INCONCLUSIVE: Δfire%=0 and the twin "
                            "report carries no outcome tallies — rebuild da-twin "
                            "(outcome counts added 2026-07-06) and re-run")
                    else:
                        failures.append(
                            "tampered tokens changed NOTHING (fire% and outcome "
                            "tallies identical) — authZ verification is not "
                            "actually enforced")
                elif tamper_delta == 0 and outcome_delta > 0:
                    print(f"    tamper check: fire% unchanged but outcomes shifted "
                          f"(Σ|Δoutcome|={outcome_delta}) — authZ enforced, "
                          f"rejection visible only in decisions")
            else:
                failures.append(f"tampered-token twin run failed: {out[-200:]}")

        report = {
            "substituted": sorted(self.spec.get("gates", {})),
            "runs": COSIM_RUNS, "seed": COSIM_SEED,
            "gates": real.get("gates", {}),
            "baseline_gates": base.get("gates", {}),
            "tamper_fire_delta_sum": tamper_delta,
            "tamper_outcome_delta_sum": outcome_delta,
            "failures": failures,
            "note": "sandbox measurements — feasibility verdict + lower bounds only",
        }
        path = self.ca_dir / "cosim_report.json"
        path.write_text(json.dumps(report, indent=2))
        for f in failures:
            print(f"    ✗ {f}")
        if failures:
            return None
        print(f"    co-sim clean: {len(report['substituted'])} gate(s) substituted, "
              f"0 dead, tamper Δ={'n/a' if tamper_delta is None else round(tamper_delta, 1)}")
        return path

    def stage_evidence(self, cosim_report: Path) -> None:
        r = subprocess.run(
            [sys.executable, str(TOOLS_DIR / "opis-eval" / "evidence.py"),
             str(self.flow_path), "--kata", self.kata_name,
             "--twin-report", str(self.ca_dir / "twin_baseline.json"),
             "--cosim-report", str(cosim_report)],
            capture_output=True, text=True, timeout=300)
        for line in (r.stdout or "").strip().splitlines():
            print(f"  {line.strip()}")
        if r.returncode != 0:
            print(f"  WARNING: evidence report failed (exit {r.returncode}): "
                  f"{(r.stderr or '').strip()[:300]}")

    # ── main ────────────────────────────────────────────────────────────────

    def run(self) -> None:
        print(f"CA starting — kata: {self.kata_name}, "
              f"flow: {self.flow_path.name} (v{self.flow_version})")
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        caps = self.preflight()
        history = self._load_history()
        outstanding = [e for e in history.values() if e["status"] == "outstanding"]
        if outstanding:
            print(f"  resuming with {len(outstanding)} outstanding defect(s) "
                  f"from a previous run")

        contracts = self._load_gate_contracts()

        schemas = self.stage_schemas(contracts, history, run_id)
        if schemas is None:
            return
        print(f"  schemas: {len(schemas.get('schemas', {}))} schema(s) conformant")

        manifest_path = self.stage_code(schemas, contracts, caps, history, run_id)
        if manifest_path is None:
            return

        if not caps["twin"]:
            print("  co-sim BLOCKED — da-twin binary not found (see preflight recipe)")
            return
        cosim_report = self.stage_cosim(manifest_path, caps)
        if cosim_report is None:
            print("  co-sim surfaced failures — see cosim_report.json / above")
            return

        self.stage_evidence(cosim_report)
        self._workspace_commit(
            f"CA: {self.kata_name} v{self.flow_version} — co-sim clean, "
            f"evidence updated ({COSIM_RUNS} runs)")
        print("CA run complete.")
