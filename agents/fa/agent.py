"""FA — Flow Architect agent."""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from .prompts import SYSTEM_PROMPT, GATE_GENERATION_PROMPT, GATE_AMENDMENT_PROMPT, build_user_prompt

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "agents"
AGENT_DIR = AGENTS_DIR
TOOLS_DIR = REPO_ROOT / "tools"

MAX_ITERATIONS = 5
MODEL = "claude-opus-4-8"

# Once the same defect fingerprint has been observed this many times (across
# iterations AND prior runs, via persisted defect history) without being
# resolved by rewiring, FA is nudged to propose a NEW gate via ADR instead of
# burning the remaining iterations rewiring around a need that doesn't fit any
# existing gate. Tunable — lower is more eager to escalate to an ADR.
ADR_NUDGE_THRESHOLD = 3


class FAAgent:
    def __init__(self, kata_path: Path):
        self.kata_path = kata_path
        self.kata_name = kata_path.stem
        self.output_dir = AGENT_DIR / "output" / self.kata_name
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        self.client = anthropic.Anthropic(
            http_client=httpx.Client(verify=False, proxy=proxy)
        )
        self.version = self._next_version()

    # ── setup ──────────────────────────────────────────────────────────────

    def _next_version(self) -> int:
        flow_dir = self.output_dir / "flow"
        if not flow_dir.exists():
            return 1
        versions = []
        for p in flow_dir.glob("flow_v*.json"):
            m = re.match(r"flow_v(\d+)$", p.stem)
            if m:
                versions.append(int(m.group(1)))
        if not versions:
            return 1
        return max(versions) + 1  # numeric, not lexical (avoids v10 < v2 bug)

    def _load_context(self) -> tuple[str, str, str]:
        kata = self.kata_path.read_text()
        slot_types = (AGENT_DIR / "slot_types" / "index.md").read_text()
        gates_index = (AGENT_DIR / "gates" / "index.md").read_text()
        return kata, slot_types, gates_index

    # ── output paths ───────────────────────────────────────────────────────

    def _flow_path(self, v: int) -> Path:
        return self.output_dir / "flow" / f"flow_v{v}.json"

    def _scratch_flow_path(self) -> Path:
        """Working file for in-progress iteration attempts. Never versioned —
        only a structurally clean AND fully-proved flow becomes a real
        flow_vN.json. Doesn't match the `flow_v*.json` glob _next_version()
        scans, so it can't collide with or be mistaken for a real version."""
        return self.output_dir / "flow" / "_iterating.json"

    def _adr_dir(self) -> Path:
        return self.output_dir / "adrs"

    def _log_dir(self) -> Path:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return self.output_dir / "logs" / "fa" / ts

    def _workspace_commit(self, message: str) -> None:
        """Commit this run's results into the LOCAL workspace repo
        (agents/output/ is its own git repo, never pushed — the product repo
        on GitHub ignores it entirely). Agents manage this repo themselves;
        a missing repo or git failure is reported but never fails the run."""
        import subprocess
        root = self.output_dir.parent  # agents/output
        if not (root / ".git").exists():
            print("  (workspace repo not initialised — skipping local commit; "
                  "run `git init` in agents/output to enable)")
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
        except Exception as e:  # never fail the run over local bookkeeping
            print(f"  workspace repo: git unavailable — {e}")

    # ── LLM call ──────────────────────────────────────────────────────────

    def _decided_adr_context(self, max_chars: int = 6000) -> str:
        """Concatenate the Context + Decision of every decided (processed) ADR
        for this kata. Injected into every flow iteration so decisions bind
        future drafts too — a rejected proposal must never be re-proposed."""
        adr_dir = self._adr_dir()
        if not adr_dir.exists():
            return ""
        chunks = []
        for path in sorted(adr_dir.glob("*.md")):
            if not self._processed_marker(path).exists():
                continue
            content = path.read_text()
            ctx = re.search(r"## Context\s*\n(.*?)(?=\n## )", content, re.DOTALL)
            dec = re.search(r"## Decision\s*\n(.*)", content, re.DOTALL)
            if dec:
                chunks.append(
                    f"### {path.stem}\nContext: {ctx.group(1).strip() if ctx else '(none)'}\n"
                    f"Decision: {dec.group(1).strip()}")
        text = "\n\n".join(chunks)
        return text[:max_chars]

    def _call_llm(self, kata: str, slot_types: str, gates_index: str, errors: str = "") -> str:
        user_prompt = build_user_prompt(kata, slot_types, gates_index, self.version,
                                        errors, self._decided_adr_context())
        response = self.client.messages.create(
            model=MODEL,
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text

    # ── parse response ─────────────────────────────────────────────────────

    def _extract_json(self, text: str) -> dict:
        """Extract JSON from LLM response, tolerating markdown fences AND
        leading prose before the JSON object (the model sometimes "thinks
        out loud" — e.g. "Let me map the kata requirements..." — before
        emitting the actual JSON, with no code fence around it)."""
        # 1) fenced ```json ... ``` block, if present
        match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
        if match:
            return json.loads(match.group(1))
        # 2) the whole trimmed text is valid JSON
        stripped = text.strip()
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
        # 3) scan for the first top-level JSON object anywhere in the text —
        # find each '{' and try to decode starting there, keeping the first
        # one that parses (handles leading prose with no fence at all).
        decoder = json.JSONDecoder()
        for i, ch in enumerate(stripped):
            if ch != "{":
                continue
            try:
                obj, _ = decoder.raw_decode(stripped, i)
                return obj
            except json.JSONDecodeError:
                continue
        # nothing parsed — raise the original error against the full text
        # so the caller's error message still shows something useful.
        return json.loads(stripped)

    # ── eval ───────────────────────────────────────────────────────────────

    def _run_eval(self, flow_path: Path) -> tuple[bool, str]:
        import subprocess
        eval_script = TOOLS_DIR / "opis-eval" / "eval.py"
        result = subprocess.run(
            [sys.executable, str(eval_script), str(flow_path)],
            capture_output=True, text=True
        )
        # exit codes: 0=clean, 1=errors (structural failure), 2=warnings only.
        # FA tolerates warnings — only a hard error blocks structural pass.
        passed = result.returncode != 1
        output = result.stdout + result.stderr
        return passed, output

    # ── requirement coverage proofs ──────────────────────────────────────────

    @staticmethod
    def _proof_module():
        """Load tools/opis-eval/proof.py by file path (sibling dir has a
        hyphen, can't `import` it normally)."""
        import importlib.util
        proof_path = TOOLS_DIR / "opis-eval" / "proof.py"
        spec = importlib.util.spec_from_file_location("opis_proof", proof_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules.setdefault("opis_proof", mod)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod

    def _verify_requirements(self, spec: dict) -> tuple[bool, list[dict], str]:
        """Run opis-proof against the flow's `requirements` array. Returns
        (all_proved, results, human-readable report of what's wrong)."""
        requirements = spec.get("requirements", [])
        if not requirements:
            return False, [], (
                "No `requirements` array in the flow spec. Every kata requirement "
                "must appear in `requirements` with a target {gate, outcome} — "
                "this is checked structurally, not just described in prose."
            )
        proof_mod = self._proof_module()
        gates_dir = AGENT_DIR / "gates"
        results = proof_mod.verify_requirements(spec, gates_dir)
        unproved = [r for r in results if r["status"] != "proved"]

        lines = []
        for r in unproved:
            lines.append(f"- {r['id']}: {r['text']} (target: {r['target']})")
            for issue in r["issues"]:
                lines.append(f"    · {issue}")
        report = "\n".join(lines)
        return (len(unproved) == 0), results, report

    def _verify_gate_conformance(self, spec: dict) -> tuple[bool, list[dict], str]:
        """Check that every gate instance claiming a gate_template actually
        covers that template's declared required input slots — not just that
        the flow is internally reachable. Catches a gate being stretched onto
        a need its template doesn't really cover (e.g. reusing delivery_router
        but never wiring its required `location` input)."""
        proof_mod = self._proof_module()
        gates_dir = AGENT_DIR / "gates"
        issues = proof_mod.check_gate_conformance(spec, gates_dir)
        lines = [f"- {i['message']}" for i in issues]
        return (len(issues) == 0), issues, "\n".join(lines)

    def _enrich_eval_errors(self, spec: dict, error_lines: list[str]) -> list[str]:
        """For each opis-eval 'requires [...] but no upstream path produces'
        line, append a wiring-gap vs no-domain-source diagnosis — tells FA
        whether the fix is 'add a synapse' or 'this type doesn't exist
        anywhere in the flow, reconsider the gate / propose a new one'."""
        proof_mod = self._proof_module()
        try:
            return proof_mod.enrich_reachability_errors(spec, error_lines)
        except Exception:
            return error_lines

    @staticmethod
    def _format_proof_path(path: list[dict]) -> str:
        parts = []
        for hop in path:
            label = f"{hop['node']}({hop['pulse_type']})"
            if hop.get("fired") == "fired":
                label += " [fired]"
            elif hop.get("fired") == "fallback":
                label += " [fallback-cyclic]"
            parts.append(label)
        return " → ".join(parts)

    def _write_proofs(self, proof_results: list[dict]) -> Path:
        tests_dir = self.output_dir / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        path = tests_dir / "requirements_proof.json"
        path.write_text(json.dumps(proof_results, indent=2))
        print(f"  requirement proofs written: {path}")
        return path

    # ── ADR handling ───────────────────────────────────────────────────────

    def _write_adr(self, adr: dict, index: int) -> Path:
        self._adr_dir().mkdir(parents=True, exist_ok=True)
        topic_slug = re.sub(r"[^a-z0-9]+", "_", adr["topic"].lower()).strip("_")
        adr_path = self._adr_dir() / f"{index:03d}_{topic_slug}.md"
        lines = [
            f"# ADR-{index:03d}: {adr['topic']}\n",
            f"## Context\n{adr['context']}\n",
            "## Options\n",
        ]
        for opt in adr.get("options", []):
            lines.append(f"### Option {opt['label']}\n{opt['description']}\n\n**Tradeoffs:** {opt.get('tradeoffs','')}\n")
        lines.append("## Decision\n\n<!-- Fill in your choice here before re-running FA -->\n")
        adr_path.write_text("\n".join(lines))
        return adr_path

    # ── flow write ─────────────────────────────────────────────────────────

    def _write_scratch(self, spec: dict) -> Path:
        """Write an in-progress iteration attempt to the scratch file. Not a
        real version — opis-eval and proof verification run against this."""
        flow_path = self._scratch_flow_path()
        flow_path.parent.mkdir(parents=True, exist_ok=True)
        flow_path.write_text(json.dumps(spec, indent=2))
        return flow_path

    def _commit_flow(self, spec: dict) -> Path:
        """Promote a structurally-clean, fully-proved spec to a real
        flow_vN.json. Called exactly once per successful run — failed
        iterations never produce a permanent version."""
        flow_path = self._flow_path(self.version)
        flow_path.parent.mkdir(parents=True, exist_ok=True)
        spec["version"] = self.version
        flow_path.write_text(json.dumps(spec, indent=2))
        # update symlink to point to current version
        symlink = self.output_dir / "flow" / "flow_current.json"
        if symlink.exists() or symlink.is_symlink():
            symlink.unlink()
        symlink.symlink_to(flow_path.name)
        return flow_path

    # ── log ────────────────────────────────────────────────────────────────

    def _write_log(self, log_dir: Path, entries: list[str]):
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "run.log").write_text("\n".join(entries))

    # ── ADR approval + gate creation ───────────────────────────────────────

    @staticmethod
    def _processed_marker(adr_path: Path) -> Path:
        return Path(str(adr_path) + ".processed")

    def _read_approved_adrs(self) -> list[tuple[Path, str]]:
        """Return (path, content) for ADRs whose Decision field is filled AND
        that haven't already been processed in a previous run (no .processed
        marker sibling file). Without this, every run re-calls the gate-
        generation LLM for every already-handled ADR just to find out its
        gate already exists — wasted calls on every single rerun."""
        adr_dir = self._adr_dir()
        if not adr_dir.exists():
            return []
        approved = []
        for path in sorted(adr_dir.glob("*.md")):
            if self._processed_marker(path).exists():
                continue
            content = path.read_text()
            # Decision section is filled if there's non-comment, non-whitespace text after "## Decision"
            decision_match = re.search(r"## Decision\s*\n(.*)", content, re.DOTALL)
            if not decision_match:
                continue
            decision_body = decision_match.group(1).strip()
            # Remove comment lines
            lines = [l for l in decision_body.splitlines()
                     if l.strip() and not l.strip().startswith("<!--")]
            if lines:
                approved.append((path, content))
        return approved

    def _generate_gate_file(self, adr_content: str) -> str:
        """Call LLM to produce a gate .md file from an approved ADR."""
        slot_types = (AGENT_DIR / "slot_types" / "index.md").read_text()
        response = self.client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=GATE_GENERATION_PROMPT,
            messages=[{"role": "user", "content":
                f"## Slot Types\n{slot_types}\n\n## Approved ADR\n{adr_content}"}],
        )
        return response.content[0].text.strip()

    def _generate_amended_gate_file(self, existing_md: str, adr_content: str) -> str:
        """Call LLM to apply an approved ADR's decision to an EXISTING gate file."""
        slot_types = (AGENT_DIR / "slot_types" / "index.md").read_text()
        response = self.client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=GATE_AMENDMENT_PROMPT,
            messages=[{"role": "user", "content":
                f"## Slot Types\n{slot_types}\n\n## Current Gate File\n{existing_md}"
                f"\n\n## Approved ADR (apply its Decision)\n{adr_content}"}],
        )
        return response.content[0].text.strip()

    def _replace_index_row(self, index_path: Path, name: str, new_row: str) -> None:
        """Replace the index table row for `name` in place (append if absent)."""
        lines = index_path.read_text().splitlines()
        replaced = False
        for i, line in enumerate(lines):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if cells and cells[0] == name:
                lines[i] = f"| {new_row} |"
                replaced = True
                break
        if not replaced:
            lines.append(f"| {new_row} |")
        index_path.write_text("\n".join(lines) + "\n")

    def _extract_gate_name(self, gate_md: str) -> str | None:
        """Extract name from YAML frontmatter."""
        match = re.search(r"^name:\s*(\S+)", gate_md, re.MULTILINE)
        return match.group(1) if match else None

    def _generate_index_row(self, gate_md: str) -> str:
        """Derive the gates/index.md table row deterministically from the gate
        file's own frontmatter — no LLM call. The frontmatter already IS the
        source of truth; asking a model to re-summarise it only adds a
        nondeterministic drift surface between the index and the file on disk.
        Uses the same derivation proof.py's index-consistency checker applies,
        so writer and checker can never disagree."""
        pm = self._proof_module()
        return pm.derive_index_row(pm.parse_gate_frontmatter(gate_md))

    def _process_approved_adrs(self) -> int:
        """Create gate files from approved ADRs. Returns count of gates created."""
        approved = self._read_approved_adrs()
        if not approved:
            return 0

        gates_dir = AGENT_DIR / "gates"
        index_path = gates_dir / "index.md"
        created = 0

        for adr_path, adr_content in approved:
            print(f"  Processing approved ADR: {adr_path.name}")
            marker = self._processed_marker(adr_path)

            # A decision can REJECT the proposal outright ("Rejected" leads the
            # Decision body). No gate is generated; the decision's guidance
            # still reaches FA because processed ADRs remain in its context.
            decision = re.search(r"## Decision\s*\n(.*)", adr_content, re.DOTALL)
            decision_head = decision.group(1).strip()[:120].lower() if decision else ""
            if decision_head.lstrip("*# ").startswith("rejected"):
                print(f"    Decision: rejected — no gate will be created")
                marker.write_text("status: rejected\n")
                continue

            gate_md = self._generate_gate_file(adr_content)
            name = self._extract_gate_name(gate_md)
            if not name:
                print(f"    Could not extract gate name — skipping (not marked processed, will retry next run)")
                continue

            gate_file = gates_dir / f"{name}.md"
            if gate_file.exists():
                # Approved decision targets an EXISTING gate: this is a contract
                # amendment, not a creation. Silently skipping here once dropped
                # an approved decision on the floor (ADR-010, delivery_router).
                print(f"    Gate {name} exists — applying contract amendment")
                amended = self._generate_amended_gate_file(
                    gate_file.read_text(), adr_content)
                if self._extract_gate_name(amended) != name:
                    print(f"    Amendment renamed the gate — rejected "
                          f"(not marked processed, will retry next run)")
                    continue
                gate_file.write_text(amended)
                self._replace_index_row(
                    index_path, name, self._generate_index_row(amended))
                print(f"    Gate amended: {gate_file.name}; index row refreshed.")
                marker.write_text(f"gate: {name}\nstatus: amended\n")
                created += 1
                continue

            gate_file.write_text(gate_md)
            print(f"    Gate written: {gate_file.name}")

            # append row to index
            row = self._generate_index_row(gate_md)
            with open(index_path, "a") as f:
                f.write(f"| {row} |\n")
            print(f"    Index updated.")
            marker.write_text(f"gate: {name}\nstatus: created\n")
            created += 1

        return created

    # ── cumulative error tracking (prevents iteration regression) ───────────

    @staticmethod
    def _defect_key(line: str) -> str:
        """Fingerprint an error/issue line by (gate-or-req, category) so the
        same underlying defect is recognised as 'the same one' even if FA
        renames the domain term/flow between iterations (e.g. 'rejected_order'
        -> 'sandwich_order_rejected'). Used to dedupe a growing error history
        without losing track of issues that were already reported."""
        m = re.search(r"gate '([^']+)'", line) or re.search(r"^(REQ-[^:]+):", line)
        anchor = m.group(1) if m else line[:40]
        if "no consuming synapse" in line:
            cat = "dead-end-output"
        elif "no upstream path produces" in line or "not reachable" in line:
            cat = "unreachable-input"
        elif "phantom gate" in line:
            cat = "phantom-template"
        elif "outcome" in line and "not found" in line:
            cat = "bad-outcome"
        elif "does not exist in this flow" in line:
            cat = "missing-target-gate"
        elif "claims gate_template" in line:
            cat = "template-mismatch"
        else:
            cat = "other"
        return f"{anchor}::{cat}"

    @staticmethod
    def _format_error_history(error_history: dict[str, str]) -> str:
        return (
            "Cumulative list of every distinct structural issue observed across "
            "ALL iterations so far in this run, not just the most recent pass. "
            "Your new flow must satisfy every item below simultaneously. A defect "
            "absent from the most recent eval/proof output may have been silently "
            "reintroduced while you were fixing something else — it is not "
            "actually resolved unless every item here is true at once:\n"
            + "\n".join(f"- {line}" for line in error_history.values())
        )

    @staticmethod
    def _format_recurrence_nudges(defect_history: dict[str, dict]) -> str:
        """When a defect fingerprint keeps recurring — either many times within
        this run or reopened after a prior 'fix' — more rewiring is unlikely to
        resolve it: the need probably doesn't fit any existing gate's contract.
        Emit a strong nudge telling FA to propose a NEW gate via an `adrs` array
        this turn (and emit NO flow spec), rather than exhausting the remaining
        iterations. Fires at ADR_NUDGE_THRESHOLD occurrences, or on any reopen.
        Returns '' when nothing is chronic yet."""
        chronic = [
            v for v in defect_history.values()
            if v.get("status") == "outstanding"
            and (v.get("times_seen", 0) >= ADR_NUDGE_THRESHOLD or v.get("reopened_count", 0) >= 1)
        ]
        if not chronic:
            return ""
        lines = [
            "STOP REWIRING — the defect(s) below have recurred repeatedly without "
            "being resolved by rewiring existing gates. That is a strong signal the "
            "need does not fit any existing gate's contract, so another wiring attempt "
            "will likely fail the same way. Instead, THIS TURN output an `adrs` array "
            "proposing a NEW gate (described in kata-agnostic computing terms only) that "
            "covers this need, and emit NO flow spec. Only the User approving that ADR "
            "will create the gate you're missing:",
        ]
        for v in sorted(chronic, key=lambda e: -e.get("times_seen", 0)):
            lines.append(
                f"- (seen {v.get('times_seen', 0)}×, reopened {v.get('reopened_count', 0)}×) {v['line']}"
            )
        return "\n".join(lines)

    # ── defect history (persisted ACROSS separate runs, not just within one) ─
    #
    # error_history above only lives in memory for one `run()` call — if FA
    # escalates after 5 iterations and you invoke the runner again later, that
    # context is gone. This persists fixed/outstanding defects to a file in
    # the kata's output dir so a fresh invocation still remembers what was
    # wrong (and what was already resolved) from every prior run.

    def _defect_history_path(self) -> Path:
        return self.output_dir / "fa_defect_history.json"

    def _load_defect_history(self) -> dict[str, dict]:
        path = self._defect_history_path()
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return {}

    def _save_defect_history(self, history: dict[str, dict]) -> None:
        self._defect_history_path().write_text(json.dumps(history, indent=2, sort_keys=True))

    @staticmethod
    def _touch_defect(history: dict[str, dict], key: str, line: str, run_id: str) -> None:
        """Record that `key` was observed (again) in this run. Reopens a
        previously-fixed entry if it has recurred — that recurrence itself is
        useful signal (a chronically unstable defect, not a one-off)."""
        now = datetime.now(timezone.utc).isoformat()
        entry = history.get(key)
        if entry is None:
            history[key] = {
                "line": line, "status": "outstanding",
                "times_seen": 1, "times_fixed": 0, "reopened_count": 0,
                "first_seen": now, "last_seen": now,
                "runs_seen": [run_id],
            }
            return
        entry["line"] = line  # keep the latest wording
        entry["last_seen"] = now
        entry["times_seen"] = entry.get("times_seen", 0) + 1
        if run_id not in entry.get("runs_seen", []):
            entry.setdefault("runs_seen", []).append(run_id)
        if entry["status"] == "fixed":
            entry["reopened_count"] = entry.get("reopened_count", 0) + 1
        entry["status"] = "outstanding"

    @staticmethod
    def _mark_all_fixed(history: dict[str, dict], run_id: str) -> int:
        """At full success every still-outstanding entry is, by definition,
        resolved (opis-eval clean + every requirement proved). Returns count
        of entries newly closed."""
        now = datetime.now(timezone.utc).isoformat()
        n = 0
        for entry in history.values():
            if entry["status"] == "outstanding":
                entry["status"] = "fixed"
                entry["times_fixed"] = entry.get("times_fixed", 0) + 1
                entry["last_fixed"] = now
                entry.setdefault("runs_fixed", []).append(run_id)
                n += 1
        return n

    # ── main ───────────────────────────────────────────────────────────────

    def run(self):
        print(f"FA starting — kata: {self.kata_name}, target version: v{self.version}")

        # Phase 0: process any approved ADRs → create gate files
        approved_count = self._process_approved_adrs()
        if approved_count:
            print(f"  {approved_count} gate(s) created from approved ADRs.")

        kata, slot_types, gates_index = self._load_context()

        log_dir = self._log_dir()
        run_id = log_dir.name
        log = [f"FA run — {datetime.now(timezone.utc).isoformat()}",
               f"kata: {self.kata_path}",
               f"target version: v{self.version}"]

        # Seed from defects outstanding at the end of any PREVIOUS invocation
        # (e.g. a prior escalation) — without this, a fresh run forgets
        # everything the moment the process exits.
        defect_history = self._load_defect_history()
        error_history: dict[str, str] = {
            k: v["line"] for k, v in defect_history.items() if v.get("status") == "outstanding"
        }
        if error_history:
            print(f"  resuming with {len(error_history)} outstanding defect(s) from a previous run")
        errors = self._format_error_history(error_history) if error_history else ""
        adr_index = self._next_adr_index()

        for iteration in range(1, MAX_ITERATIONS + 1):
            print(f"  iteration {iteration}/{MAX_ITERATIONS}...")
            log.append(f"\n--- iteration {iteration} ---")

            # A defect that keeps recurring won't be fixed by more rewiring —
            # nudge FA to propose a new gate via ADR before it burns the rest
            # of the iterations. Prepended so it leads the error feedback.
            nudges = self._format_recurrence_nudges(defect_history)
            call_errors = f"{nudges}\n\n{errors}" if nudges else errors
            if nudges:
                print("  recurrence nudge active — steering FA toward an ADR for chronic defect(s)")
                log.append("recurrence nudge injected (chronic defect past threshold)")

            raw = self._call_llm(kata, slot_types, gates_index, call_errors)
            log.append(f"LLM response ({len(raw)} chars)")

            try:
                parsed = self._extract_json(raw)
            except json.JSONDecodeError as e:
                log.append(f"JSON parse error: {e}\nRaw:\n{raw[:500]}")
                print(f"  JSON parse error: {e} — treating as a retryable failure, not aborting the run.")
                key = "json-parse-error"
                line = (
                    "Your previous response could not be parsed as a single JSON object. "
                    "Respond with ONLY the JSON object — no prose before or after it, "
                    "and no markdown fence unless the fence wraps the entire JSON and "
                    "nothing else."
                )
                error_history[key] = line
                self._touch_defect(defect_history, key, line, run_id)
                self._save_defect_history(defect_history)
                errors = self._format_error_history(error_history)
                if iteration < MAX_ITERATIONS:
                    print(f"  retrying — attempt {iteration + 1}/{MAX_ITERATIONS}")
                continue

            # handle ADRs (batch — all missing gates proposed at once)
            if "adrs" in parsed:
                written = []
                for adr in parsed["adrs"]:
                    adr_path = self._write_adr(adr, adr_index)
                    adr_index += 1
                    written.append(adr_path.name)
                msg = f"  {len(written)} ADR(s) written: {', '.join(written)}"
                print(msg)
                print("  → Review and fill in Decision fields, then re-run FA.")
                log.append(msg + " — waiting for User approval")
                if "name" not in parsed:
                    self._write_log(log_dir, log)
                    return

            if "name" not in parsed:
                log.append("No flow spec in response.")
                break

            flow_path = self._write_scratch(parsed)
            log.append(f"scratch flow written: {flow_path}")
            print(f"  flow written (scratch, attempt {iteration}): {flow_path.name}")

            passed, eval_output = self._run_eval(flow_path)
            log.append(f"opis-eval: {'PASS' if passed else 'FAIL'}\n{eval_output}")
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / f"eval_iter{iteration}.txt").write_text(eval_output)

            if passed:
                print(f"  opis-eval PASS — attempt {iteration} structurally clean.")
                proofs_ok, proof_results, proof_report = self._verify_requirements(parsed)
                conform_ok, conform_issues, conform_report = self._verify_gate_conformance(parsed)

                if proofs_ok and conform_ok:
                    n = len(proof_results)
                    print(f"  requirement coverage PASS — {n}/{n} requirement(s) proved.")
                    print(f"  gate conformance PASS — every instance honors its claimed template.")
                    log.append("FA complete — structurally clean, all requirements proved, "
                                "all gates conform to their claimed templates.")
                    self._commit_flow(parsed)
                    print(f"  flow committed: flow_v{self.version}.json")
                    n_fixed = self._mark_all_fixed(defect_history, run_id)
                    self._save_defect_history(defect_history)
                    if n_fixed:
                        print(f"  defect history: {n_fixed} defect(s) closed out, 0 outstanding.")
                    self._write_log(log_dir, log)
                    self._write_proofs(proof_results)
                    self._write_tests(parsed, proof_results)
                    self._workspace_commit(
                        f"FA: {self.kata_name} flow_v{self.version} — "
                        f"{len(proof_results)} requirement(s) proved, conformant")
                    return

                fail_parts = []

                if not proofs_ok:
                    n_bad = sum(1 for r in proof_results if r["status"] != "proved")
                    print(f"  requirement coverage FAILED — {n_bad} unproved requirement(s).")
                    print("  reason:")
                    for line in proof_report.splitlines():
                        print(f"    {line}")
                    log.append(f"opis-eval PASS but requirement coverage FAILED:\n{proof_report}")
                    if proof_results:
                        self._write_proofs(proof_results)  # keep evidence even on failure, for debugging
                    new_lines = [l.strip() for l in proof_report.splitlines() if l.strip().startswith(("- REQ", "    ·"))]
                    for line in new_lines:
                        key = self._defect_key(line)
                        error_history[key] = line
                        self._touch_defect(defect_history, key, line, run_id)
                    fail_parts.append(
                        "Requirement coverage verification failed. Every requirement's target "
                        "gate must have a genuine path for ALL its required inputs (not just "
                        "one), and gate_template/outcome must be real. Fix the wiring or the "
                        "requirement's target — don't just reword the requirement text."
                    )

                if not conform_ok:
                    print(f"  gate conformance FAILED — {len(conform_issues)} gate(s) don't honor their claimed template.")
                    print("  reason:")
                    for line in conform_report.splitlines():
                        print(f"    {line}")
                    log.append(f"gate conformance FAILED:\n{conform_report}")
                    for line in conform_report.splitlines():
                        key = self._defect_key(line)
                        error_history[key] = line
                        self._touch_defect(defect_history, key, line, run_id)
                    fail_parts.append(
                        "Gate conformance verification failed. A gate claiming a gate_template "
                        "must actually wire ALL of that template's required input slot types — "
                        "if a need doesn't truly fit an existing template's full contract, either "
                        "wire the missing input properly or propose a NEW gate via ADR instead of "
                        "reusing a template that doesn't really cover this case. Don't drop a "
                        "required input just to make an unrelated gate fit."
                    )

                self._save_defect_history(defect_history)
                errors = "\n\n".join(fail_parts) + "\n\n" + self._format_error_history(error_history)
            else:
                error_lines = [
                    l.strip() for l in eval_output.splitlines()
                    if "✗" in l and not re.match(r"^\s*✗\s*\d+\s+error", l)
                ]
                error_lines = self._enrich_eval_errors(parsed, error_lines)
                print(f"  opis-eval FAILED — {len(error_lines)} error(s).")
                print("  reason:")
                for line in (error_lines or [eval_output.strip()[:500]]):
                    print(f"    {line}")
                log.append(f"opis-eval FAILED:\n{eval_output}")
                for line in error_lines:
                    key = self._defect_key(line)
                    error_history[key] = line
                    self._touch_defect(defect_history, key, line, run_id)
                self._save_defect_history(defect_history)
                errors = self._format_error_history(error_history)

            if iteration < MAX_ITERATIONS:
                print(f"  retrying — attempt {iteration + 1}/{MAX_ITERATIONS}")

        n_outstanding = sum(1 for v in defect_history.values() if v.get("status") == "outstanding")
        print(f"  FA could not produce a clean, fully-proved flow in {MAX_ITERATIONS} iterations.")
        print(f"  No flow_v{self.version}.json was written — only clean, proved flows get committed.")
        print(f"  {n_outstanding} defect(s) carried forward to defect history — the next run will resume with this context.")
        print(f"  Last attempt left at: {self._scratch_flow_path()}")
        print(f"  Check logs: {log_dir}")
        log.append(f"ESCALATE: could not resolve in {MAX_ITERATIONS} iterations. No version committed. "
                    f"{n_outstanding} defect(s) carried to {self._defect_history_path().name}.")
        self._write_log(log_dir, log)

    def _next_adr_index(self) -> int:
        adr_dir = self._adr_dir()
        if not adr_dir.exists():
            return 1
        existing = sorted(adr_dir.glob("*.md"))
        return len(existing) + 1

    def _write_tests(self, spec: dict, proof_results: list[dict] | None = None):
        tests_dir = self.output_dir / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        gates = list(spec.get("gates", {}).keys())

        flow_level = [
            "- [x] opis-eval passes with zero errors",
            "- [x] every external locus (source: true) has sentinel_auth upstream",
            "",
            "**Requirement coverage** (each one structurally proved, not just described):",
            "",
        ]
        if proof_results:
            for r in proof_results:
                mark = "x" if r["status"] == "proved" else " "
                flow_level.append(f"- [{mark}] {r['id']}: {r['text']}")
                for t, path in r.get("proofs", {}).items():
                    flow_level.append(f"    - `{t}`: {self._format_proof_path(path)}")
                for issue in r.get("issues", []):
                    flow_level.append(f"    - ISSUE: {issue}")
                for note in r.get("notes", []):
                    flow_level.append(f"    - note: {note}")
        else:
            flow_level.append(
                "- [ ] (no requirements array — FA did not comply with the requirements rule)"
            )

        lines = [
            "# FA Tests\n",
            "## Flow-level (FA verifies)\n",
        ] + flow_level + [
            "\n## Gate-level (GA verifies)\n",
        ] + [f"- [ ] {g}: PDs within flow timing bounds" for g in gates] + [
            "\n## Code-level (CA verifies)\n",
        ] + [f"- [ ] {g}: implementation accepts correct input types and emits correct output types" for g in gates]
        (tests_dir / "fa_tests.md").write_text("\n".join(lines))
        print(f"  tests written: {tests_dir / 'fa_tests.md'}")
