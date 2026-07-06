"""FA — Flow Architect agent."""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from .prompts import (SYSTEM_PROMPT, GATE_GENERATION_PROMPT, GATE_AMENDMENT_PROMPT,
                      TAXONOMY_PROMPT, build_user_prompt)

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "agents"
AGENT_DIR = AGENTS_DIR
TOOLS_DIR = REPO_ROOT / "tools"

MAX_ITERATIONS = 5
MODEL = "claude-fable-5"        # flow design: the hard reasoning
GATE_MODEL = "claude-sonnet-5"  # ADR → gate .md: mechanical transcription, cheaper

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
        self.output_dir = REPO_ROOT / "workspace" / self.kata_name
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
        (workspace/ at the repo root is its own git repo, never pushed — the
        product repo on GitHub ignores it entirely). Agents manage this repo
        themselves; a missing repo or git failure never fails the run."""
        import subprocess
        root = self.output_dir.parent  # workspace/
        if not (root / ".git").exists():
            print("  (workspace repo not initialised — skipping local commit; "
                  "run `git init` in workspace/ to enable)")
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

    def _decided_adr_context(self, max_chars: int = 12000,
                             decisions_only: bool = False) -> str:
        """Concatenate the decided (processed) ADRs for this kata, injected
        into every flow iteration so decisions bind future drafts too — a
        rejected proposal must never be re-proposed.

        DECISIONS ARE NEVER DROPPED (2026-07-05 fix). The old version built
        oldest-first and cut with text[:6000]; once the ADR log outgrew the
        cap, the NEWEST decisions silently vanished from FA's context — the
        run right after ADR-017 was decided re-litigated the same problem
        and proposed ADR-018, loyal to old 008 and blind to 017. Now:
        every Decision block is always included (a binding decision that
        exceeds a token budget is still binding); Context blocks are
        attached newest-first only while budget remains, since old contexts
        are mostly embodied in the gate library already. Ordered newest
        first so the freshest bindings lead."""
        adr_dir = self._adr_dir()
        if not adr_dir.exists():
            return ""
        entries = []  # newest first: (stem, context, decision)
        for path in sorted(adr_dir.glob("*.md"), reverse=True):
            if not self._processed_marker(path).exists():
                continue
            content = path.read_text()
            ctx = re.search(r"## Context\s*\n(.*?)(?=\n## )", content, re.DOTALL)
            dec = re.search(r"## Decision\s*\n(.*)", content, re.DOTALL)
            if dec:
                entries.append((path.stem,
                                ctx.group(1).strip() if ctx else "",
                                dec.group(1).strip()))
        if not entries:
            return ""
        # pass 1 — every decision, unconditionally
        decision_blocks = {stem: f"### {stem}\nDecision: {dec}"
                           for stem, _, dec in entries}
        if decisions_only:
            # lean mode (taxonomy stage): the binding calls, none of the
            # option-tradeoff prose — keeps small-model prompts small.
            return ("(newest first; all decisions included)\n\n"
                    + "\n\n".join(decision_blocks[s] for s, _, _ in entries))
        budget = max_chars - sum(len(b) + 2 for b in decision_blocks.values())
        # pass 2 — contexts newest-first while budget allows
        with_ctx: set[str] = set()
        for stem, ctx, _ in entries:
            if ctx and len(ctx) + 10 <= budget:
                with_ctx.add(stem)
                budget -= len(ctx) + 10
        chunks = []
        for stem, ctx, dec in entries:
            if stem in with_ctx:
                chunks.append(f"### {stem}\nContext: {ctx}\nDecision: {dec}")
            else:
                chunks.append(decision_blocks[stem])
        omitted = len(entries) - len(with_ctx)
        header = ("(newest first; all decisions included"
                  + (f"; context omitted for {omitted} older ADR(s) — "
                     f"decisions still bind" if omitted else "") + ")\n\n")
        return header + "\n\n".join(chunks)

    @staticmethod
    def _response_text(response) -> str:
        """Concatenate the TEXT blocks of a response. Fable-class models
        prepend ThinkingBlocks; content[0].text blows up on those."""
        return "".join(
            b.text for b in response.content if getattr(b, "type", "") == "text")

    _model_verified = False

    def _verify_served_model(self, response) -> None:
        """The API once silently served a fallback for an invalid model string.
        Never again: verify the served model matches the pin, loudly, once."""
        if FAAgent._model_verified:
            return
        served = getattr(response, "model", "")
        if not served.startswith(MODEL):
            print(f"  !! MODEL MISMATCH: pinned '{MODEL}' but API served '{served}' — "
                  f"check the model string / account access")
        else:
            print(f"  model verified: {served}")
        FAAgent._model_verified = True

    # ── Stage 1: domain taxonomy (kata terms → slot types → gates) ──────────

    def _taxonomy_path(self) -> Path:
        return self.output_dir / f"taxonomy_v{self.version}.json"

    @staticmethod
    def _parse_index_gates(gates_index: str) -> list[tuple[str, str, list[str], list[str]]]:
        """(name, kind, in_types, out_types) rows from the gates index table."""
        rows = []
        for line in gates_index.splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == 5 and cells[0] not in ("gate", "") and not set(cells[0]) <= set("-"):
                rows.append((cells[0], cells[1],
                             [t.strip() for t in cells[2].split(",") if t.strip()],
                             [t.strip() for t in cells[3].split(",") if t.strip()]))
        return rows

    @staticmethod
    def _slot_type_parents(slot_types: str) -> dict[str, str | None]:
        """{slot_type: parent_or_None} from the slot_types index table."""
        out: dict[str, str | None] = {}
        for line in slot_types.splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 2 and cells[0] not in ("type", "") and not set(cells[0]) <= set("-"):
                parent = cells[1] if cells[1] not in ("—", "-", "") else None
                out[cells[0]] = parent
        return out

    def _load_or_create_taxonomy(self, kata: str, slot_types: str, gates_index: str) -> dict | None:
        """Stage 1 of a run: the domain glossary. Generated once per version,
        persisted, mechanically validated and enriched with gate linkage —
        then BINDING for every flow iteration. Returns None if unmappable
        concepts need a slot-type decision first."""
        path = self._taxonomy_path()
        if path.exists():
            # STALENESS (2026-07-05): an ADR decided AFTER this taxonomy was
            # written may add binding vocabulary — reusing the old file would
            # make the decided terms illegal in flow conformance. Regenerate
            # whenever any processed-ADR marker is newer than the file.
            newest_marker = max(
                (m.stat().st_mtime for m in self._adr_dir().glob("*.processed")),
                default=0.0)
            if path.stat().st_mtime >= newest_marker:
                tax = json.loads(path.read_text())
                print(f"  taxonomy: reusing {path.name} ({len(tax.get('terms', {}))} term(s))")
                return tax
            print(f"  taxonomy: {path.name} is older than the newest decided "
                  f"ADR — regenerating with decisions in context")

        print("  taxonomy: deriving domain glossary (stage 1)...")
        # Shape-guarded with one retry: a response without a non-empty 'terms'
        # dict used to KeyError deep in enrichment (2026-07-05, silicon v2 run)
        # — malformed LLM output must be a clean, loud failure, never a crash.
        tax = None
        # Decided ADRs bind the taxonomy too (2026-07-05): a term-addition
        # decided via ADR must appear with EXACTLY the decided name — stage 1
        # deriving from the kata alone would invent its own synonyms and the
        # flow could never legally use the decided vocabulary.
        # Decisions only — the taxonomy stage needs "term X extends Y", not
        # the full option-tradeoff contexts (which bloated the prompt enough
        # to truncate the 8k-token response on first deployment, 2026-07-05).
        adr_ctx = self._decided_adr_context(decisions_only=True)
        tax_user = f"## Kata\n{kata}\n\n## Available Slot Types\n{slot_types}"
        if adr_ctx:
            tax_user += (
                "\n\n## Decided ADRs (BINDING)\n"
                "Any domain term a Decision below adds MUST appear in your "
                "taxonomy under exactly that name with the decided extends; "
                "rejected proposals must not reappear under any name.\n\n"
                + adr_ctx)
        for attempt in (1, 2):
            response = self.client.messages.create(
                model=GATE_MODEL,  # small structured task; flow design stays on MODEL
                max_tokens=16000,
                system=TAXONOMY_PROMPT,
                messages=[{"role": "user", "content": tax_user}],
            )
            raw = self._response_text(response)
            try:
                cand = self._extract_json(raw)
            except json.JSONDecodeError as e:
                stop = getattr(response, "stop_reason", "?")
                print(f"  taxonomy: unparseable response (attempt {attempt}/2): {e}")
                print(f"    stop_reason={stop}, text len={len(raw)}, "
                      f"head={raw[:200]!r}")
                fail_path = self.output_dir / f"taxonomy_failure_attempt{attempt}.txt"
                fail_path.parent.mkdir(parents=True, exist_ok=True)
                fail_path.write_text(f"stop_reason: {stop}\n\n{raw}")
                print(f"    raw response saved: {fail_path.name}")
                continue
            if isinstance(cand.get("terms"), dict) and cand["terms"]:
                tax = cand
                break
            print(f"  taxonomy: response has no non-empty 'terms' dict "
                  f"(attempt {attempt}/2) — keys: {sorted(cand)[:8]}")
        if tax is None:
            raise RuntimeError(
                "taxonomy generation failed twice — no usable 'terms' in the "
                "model's response; re-run FA (nothing was written)")

        # mechanical validation: every extends resolves into the slot-type index
        parents = self._slot_type_parents(slot_types)
        bad = {t: spec.get("extends") for t, spec in tax.get("terms", {}).items()
               if spec.get("extends") not in parents}
        if bad:
            raise RuntimeError(f"taxonomy invalid — terms extending unknown slot types: {bad}")

        # unmappable concepts block the run: they need a slot-type decision
        if tax.get("unmappable"):
            print("  taxonomy: UNMAPPABLE concepts — a slot-type decision is needed first:")
            for u in tax["unmappable"]:
                print(f"    - {u.get('kata_phrase')!r}: {u.get('why_no_slot_type_fits')}")
            path.write_text(json.dumps(tax, indent=2))
            self._workspace_commit(f"FA: {self.kata_name} taxonomy blocked — unmappable concepts")
            return None

        # enrich: which index gates consume/produce each term's slot type
        # (subtype-aware upward: a gate accepting `order` consumes a term
        # extending order). Derived, not LLM-claimed.
        def ancestors_of(st: str) -> set[str]:
            seen: set[str] = set()
            cur: str | None = st
            while cur is not None and cur not in seen:
                seen.add(cur)
                cur = parents.get(cur)
            return seen

        gates = self._parse_index_gates(gates_index)
        for term, spec in tax["terms"].items():
            anc = ancestors_of(spec["extends"])
            spec["consumed_by"] = sorted(g for g, _, ins, _ in gates if anc & set(ins))
            spec["produced_by"] = sorted(g for g, _, _, outs in gates if anc & set(outs))

        path.write_text(json.dumps(tax, indent=2))
        uncovered = [t for t, s in tax["terms"].items()
                     if not s["consumed_by"] and not s["produced_by"]]
        print(f"  taxonomy: {len(tax['terms'])} term(s) written to {path.name}"
              + (f"; {len(uncovered)} with NO gate coverage yet: {', '.join(uncovered[:6])}"
                 if uncovered else ""))
        self._workspace_commit(f"FA: {self.kata_name} taxonomy_v{self.version} — "
                               f"{len(tax['terms'])} term(s)")
        return tax

    @staticmethod
    def _format_taxonomy(tax: dict) -> str:
        lines = ["| term | extends | consumed_by | produced_by |",
                 "|------|---------|-------------|-------------|"]
        for term, s in tax.get("terms", {}).items():
            lines.append(f"| {term} | {s.get('extends')} | "
                         f"{', '.join(s.get('consumed_by', [])) or '—'} | "
                         f"{', '.join(s.get('produced_by', [])) or '—'} |")
        if tax.get("loci"):
            lines += ["", "| locus | kind | source |", "|-------|------|--------|"]
            for name, s in tax["loci"].items():
                lines.append(f"| {name} | {s.get('kind')} | {s.get('source', False)} |")
        return "\n".join(lines)

    def _taxonomy_conformance_errors(self, parsed: dict, tax: dict) -> list[str]:
        """The flow's archetypes and loci must come from the binding taxonomy."""
        if not tax:
            return []
        terms = tax.get("terms", {})
        errs = []
        for name, aspec in parsed.get("archetypes", {}).items():
            if name not in terms:
                errs.append(f"archetype '{name}' is not in the binding taxonomy — "
                            f"use the taxonomy's term for this concept, do not invent types")
            elif isinstance(aspec, dict) and aspec.get("extends") != terms[name]["extends"]:
                errs.append(f"archetype '{name}' extends '{aspec.get('extends')}' but the "
                            f"taxonomy says '{terms[name]['extends']}' — the taxonomy is binding")
        known_loci = set(tax.get("loci", {}))
        if known_loci:
            for name in parsed.get("loci", {}):
                if name not in known_loci:
                    errs.append(f"locus '{name}' is not in the binding taxonomy — "
                                f"use the taxonomy's locus for this actor/store, do not invent loci")
        return errs

    def _call_llm(self, kata: str, slot_types: str, gates_index: str, errors: str = "") -> str:
        user_prompt = build_user_prompt(kata, slot_types, gates_index, self.version,
                                        errors, self._decided_adr_context(),
                                        getattr(self, "_taxonomy_table", ""))
        # Streaming is mandatory at this budget (SDK refuses non-streaming
        # calls that could exceed 10 minutes). Fable-class models think by
        # default; the budget must fit thinking + a full flow spec — 8192
        # starved the text entirely (thinking ate it all → empty response).
        with self.client.messages.stream(
            model=MODEL,
            max_tokens=32000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        ) as stream:
            response = stream.get_final_message()
        self._verify_served_model(response)
        text = self._response_text(response)
        if not text.strip():
            kinds = [getattr(b, "type", "?") for b in response.content]
            print(f"  !! empty text from model — stop_reason={response.stop_reason}, "
                  f"blocks={kinds} (thinking likely consumed max_tokens)")
        return text

    # ── parse response ─────────────────────────────────────────────────────

    def _extract_json(self, text: str) -> dict:
        """Extract JSON from LLM response, tolerating markdown fences AND
        leading prose before the JSON object (the model sometimes "thinks
        out loud" — e.g. "Let me map the kata requirements..." — before
        emitting the actual JSON, with no code fence around it).

        SHAPE-AWARE (2026-07-05 fix): the response may contain several JSON
        objects — small illustrative snippets in prose plus the actual flow
        spec. The old code returned the FIRST parseable object, so a tiny
        snippet could shadow the flow spec ("No flow spec in response" run
        kill). Now: collect every candidate (all fenced blocks, whole text,
        inline scan), return the first one that looks like a flow spec or an
        ADR batch; if none qualifies, return the LARGEST candidate so the
        caller's diagnostics see the most substantial object."""
        candidates: list[dict] = []

        def _try(s: str) -> None:
            try:
                obj = json.loads(s)
                if isinstance(obj, dict):
                    candidates.append(obj)
            except json.JSONDecodeError:
                pass

        # 1) every fenced ```json ... ``` block (not just the first)
        for match in re.finditer(r"```(?:json)?\s*([\s\S]+?)\s*```", text):
            _try(match.group(1))
        # 2) the whole trimmed text
        stripped = text.strip()
        _try(stripped)
        # 3) scan for top-level JSON objects anywhere in the text
        decoder = json.JSONDecoder()
        i = 0
        while i < len(stripped):
            if stripped[i] != "{":
                i += 1
                continue
            try:
                obj, end = decoder.raw_decode(stripped, i)
                if isinstance(obj, dict):
                    candidates.append(obj)
                i = end
            except json.JSONDecodeError:
                i += 1

        # prefer a flow spec or ADR batch over incidental snippets
        for obj in candidates:
            if "name" in obj or "adrs" in obj:
                return obj
        if candidates:
            return max(candidates, key=lambda o: len(json.dumps(o)))
        # nothing parsed — raise against the full text so the caller's
        # error message still shows something useful.
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
        lines.append("### Architect's option (optional)\n\n"
                      "<!-- Add your own alternative here and name it in Decision -->\n")
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

    @staticmethod
    def _pins_module():
        """Load tools/opis-eval/pins.py by file path (same hyphen-dir dance
        as _proof_module)."""
        import importlib.util
        pins_path = TOOLS_DIR / "opis-eval" / "pins.py"
        spec = importlib.util.spec_from_file_location("opis_pins", pins_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules.setdefault("opis_pins", mod)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod

    def _commit_flow(self, spec: dict) -> Path:
        """Promote a structurally-clean, fully-proved spec to a real
        flow_vN.json. Called exactly once per successful run — failed
        iterations never produce a permanent version.

        The committed flow carries a `pins` block freezing the exact gate
        contracts + slot-type taxonomy the proofs ran against (version +
        content hash). A later contract/taxonomy change never moves this
        flow — upgrade is an explicit re-prove producing a new version."""
        flow_path = self._flow_path(self.version)
        flow_path.parent.mkdir(parents=True, exist_ok=True)
        spec["version"] = self.version
        pins_mod = self._pins_module()
        pins, pin_errors = pins_mod.compute_pins(spec, AGENT_DIR / "gates")
        if pin_errors:
            # a used template with no contract file should have been caught by
            # conformance long before commit — treat as a hard bug, not a skip
            raise RuntimeError("pin compute failed at commit: "
                               + "; ".join(pin_errors))
        spec["pins"] = pins
        flow_path.write_text(json.dumps(spec, indent=2))
        # update symlink to point to current version
        symlink = self.output_dir / "flow" / "flow_current.json"
        if symlink.exists() or symlink.is_symlink():
            symlink.unlink()
        symlink.symlink_to(flow_path.name)
        return flow_path

    def _write_evidence(self, flow_path) -> None:
        """Generate the evidence report (evidence_vN.json + .md) beside the
        committed flow — static layers now; twin/co-sim evidence attaches in
        later runs that produce those reports. Best-effort: an evidence
        failure never un-commits a proved flow, but it is loud."""
        try:
            import subprocess
            r = subprocess.run(
                [sys.executable, str(TOOLS_DIR / "opis-eval" / "evidence.py"),
                 str(flow_path), "--kata", self.kata_name],
                capture_output=True, text=True, timeout=120,
            )
            for line in (r.stdout or "").strip().splitlines():
                print(f"  {line.strip()}")
            if r.returncode != 0:
                print(f"  WARNING: evidence report failed (exit {r.returncode}): "
                      f"{(r.stderr or '').strip()[:300]}")
        except Exception as e:  # noqa: BLE001
            print(f"  WARNING: evidence report failed: {e}")

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
            model=GATE_MODEL,
            max_tokens=2048,
            system=GATE_GENERATION_PROMPT,
            messages=[{"role": "user", "content":
                f"## Slot Types\n{slot_types}\n\n## Approved ADR\n{adr_content}"}],
        )
        return self._response_text(response).strip()

    def _generate_amended_gate_file(self, existing_md: str, adr_content: str) -> str:
        """Call LLM to apply an approved ADR's decision to an EXISTING gate file."""
        slot_types = (AGENT_DIR / "slot_types" / "index.md").read_text()
        response = self.client.messages.create(
            model=GATE_MODEL,
            max_tokens=2048,
            system=GATE_AMENDMENT_PROMPT,
            messages=[{"role": "user", "content":
                f"## Slot Types\n{slot_types}\n\n## Current Gate File\n{existing_md}"
                f"\n\n## Approved ADR (apply its Decision)\n{adr_content}"}],
        )
        return self._response_text(response).strip()

    def _lint_contract(self, gate_file: Path) -> None:
        """ADVISORY prose-exceeds-slots lint on a just-written contract.
        4/4 CA falsifications to date were this class — surface suspects at
        write time, before any flow is proved against them. Warnings only:
        printed, never blocking (the lint is a heuristic; falsification
        stays CA's job, and amendment stays the User's decision via ADR)."""
        lint = Path(__file__).parent.parent.parent / "tools" / "opis-eval" / "contract_lint.py"
        try:
            result = subprocess.run(
                [sys.executable, str(lint), str(gate_file), "--quiet"],
                capture_output=True, text=True, timeout=30)
        except Exception as e:  # advisory — never fail the run
            print(f"    contract-lint skipped ({e})")
            return
        out = result.stdout.strip()
        if result.returncode == 2 and out:
            print(f"    ⚠ contract-lint: prose-exceeds-slots suspect(s) in {gate_file.name}:")
            for line in out.splitlines():
                print(f"      {line}")

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

    @staticmethod
    def _set_frontmatter_version(gate_md: str, version: int) -> str:
        """Set (or insert, after `name:`) the frontmatter `version:` field."""
        if re.search(r"^version:\s*\d+\s*$", gate_md, re.MULTILINE):
            return re.sub(r"^version:\s*\d+\s*$", f"version: {version}",
                          gate_md, count=1, flags=re.MULTILINE)
        return re.sub(r"^(name:.*)$", rf"\1\nversion: {version}",
                      gate_md, count=1, flags=re.MULTILINE)

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

            # TAXONOMY ADRs (2026-07-05): a decided term-addition ADR creates
            # no gate — it binds through (a) the decided-ADR context injected
            # into flow iterations and (b) the taxonomy stage, which also
            # receives decided ADRs and regenerates when a marker is newer
            # than the taxonomy file. Without this check the generic path
            # below would fabricate a gate .md out of a vocabulary decision.
            title_line = adr_content.splitlines()[0] if adr_content else ""
            if ("taxonomy_gap" in adr_path.stem
                    or re.search(r"taxonomy\W{0,3}gap", title_line, re.I)):
                print(f"    Decision: taxonomy term addition — no gate; "
                      f"binds via taxonomy stage + decision context")
                marker.write_text("status: taxonomy\n")
                continue

            # Amendment detection BEFORE any generation call (token saver: the
            # old flow burned a full gate-generation just to learn the name).
            # If the Decision section names exactly one existing gate, this is
            # an amendment of that gate.
            existing = {p.stem for p in gates_dir.glob("*.md")} - {"index"}
            decision_body = decision.group(1) if decision else ""
            mentioned = sorted({g for g in existing
                                if re.search(rf"\b{re.escape(g)}\b", decision_body)})
            amend_target = mentioned[0] if len(mentioned) == 1 else None

            if amend_target is None:
                # Generated contracts are VERIFIED before they touch disk
                # (2026-07-05): a response missing the closing frontmatter
                # `---` once wrote a parser-invisible gate file whose index
                # row derived as '?' — FA then couldn't see its own gate and
                # re-proposed it as a fresh ADR. One repair retry, then skip
                # loudly (unprocessed → retried next run).
                gate_md = None
                pm = self._proof_module()
                for gen_attempt in (1, 2):
                    cand_md = self._generate_gate_file(adr_content)
                    fm = pm.parse_gate_frontmatter(cand_md)
                    if fm.get("name") and fm.get("input_slots"):
                        gate_md = cand_md
                        break
                    print(f"    generated contract failed frontmatter "
                          f"verification (attempt {gen_attempt}/2): "
                          f"name={fm.get('name')!r}, "
                          f"input_slots={len(fm.get('input_slots', []))}")
                if gate_md is None:
                    print(f"    Could not generate a verifiable gate file — "
                          f"skipping (not marked processed, will retry next run)")
                    continue
                name = fm["name"]
            else:
                name = amend_target
                gate_md = ""  # amendment path never uses a fresh generation

            gate_file = gates_dir / f"{name}.md"
            if gate_file.exists():
                # Approved decision targets an EXISTING gate: this is a contract
                # amendment, not a creation. Silently skipping here once dropped
                # an approved decision on the floor (ADR-010, delivery_router).
                print(f"    Gate {name} exists — applying contract amendment")
                amended = self._generate_amended_gate_file(
                    gate_file.read_text(), adr_content)
                got = self._extract_gate_name(amended)
                if got != name:
                    # A gate's identity is fixed: amendments change contracts,
                    # never names. Clamp the frontmatter back instead of
                    # rejecting — rejection burned the generation AND retried
                    # forever on every subsequent run (bitten: ADR-012).
                    print(f"    Amendment renamed the gate to '{got}' — "
                          f"clamping name back to '{name}'")
                    amended = re.sub(r"^name:\s*\S+", f"name: {name}",
                                     amended, count=1, flags=re.MULTILINE)
                    if self._extract_gate_name(amended) != name:
                        print("    no clampable frontmatter name line — "
                              "rejected (not marked processed, will retry next run)")
                        continue
                # Same frontmatter verification as the creation path
                # (2026-07-05): _extract_gate_name greps a name line, which
                # survives a broken frontmatter block (e.g. missing closing
                # `---`) that parse_gate_frontmatter — and therefore the
                # index row, pins, and conformance — cannot see.
                amended_fm = self._proof_module().parse_gate_frontmatter(amended)
                if not (amended_fm.get("name") and amended_fm.get("input_slots")):
                    print(f"    amended contract failed frontmatter verification "
                          f"(name={amended_fm.get('name')!r}, input_slots="
                          f"{len(amended_fm.get('input_slots', []))}) — "
                          f"rejected (not marked processed, will retry next run)")
                    continue
                # Append-only contract versioning: the outgoing contract may
                # be pinned by committed flows — archive it verbatim, then
                # bump the amended file's version. Pinned flows keep proving
                # against the archive; new flows pin the new version.
                pins_mod = self._pins_module()
                old_version = pins_mod.frontmatter_version(gate_file)
                archive = gates_dir / "archive" / f"{name}_v{old_version}.md"
                archive.parent.mkdir(exist_ok=True)
                if archive.exists() and archive.read_bytes() != gate_file.read_bytes():
                    print(f"    !! archive {archive.name} already exists with "
                          f"DIFFERENT content — refusing to overwrite an "
                          f"immutable version; resolve manually")
                    continue
                archive.write_bytes(gate_file.read_bytes())
                amended = self._set_frontmatter_version(amended, old_version + 1)
                gate_file.write_text(amended)
                print(f"    archived {archive.name}; contract now v{old_version + 1}")
                self._replace_index_row(
                    index_path, name, self._generate_index_row(amended))
                print(f"    Gate amended: {gate_file.name}; index row refreshed.")
                self._lint_contract(gate_file)
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
            self._lint_contract(gate_file)
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

        # Stage 1: binding domain taxonomy (kata terms → slot types → gates)
        self._taxonomy = self._load_or_create_taxonomy(kata, slot_types, gates_index)
        if self._taxonomy is None:
            print("  → Resolve the unmappable concepts (slot-type decision), then re-run FA.")
            return
        self._taxonomy_table = self._format_taxonomy(self._taxonomy)

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
            # Always persist the raw response — when extraction goes wrong
            # (wrong-shaped JSON, truncation) this is the ONLY diagnostic.
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / f"response_iter{iteration}.txt").write_text(raw)

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

            # Binding-taxonomy conformance: cheaper than eval, checked first.
            # A flow using invented vocabulary is wrong before it's wired.
            tax_errs = self._taxonomy_conformance_errors(
                parsed, getattr(self, "_taxonomy", {}) or {})
            if tax_errs and "adrs" not in parsed:
                print(f"  taxonomy conformance FAILED — {len(tax_errs)} violation(s).")
                for t in tax_errs:
                    print(f"    ✗ {t}")
                for t in tax_errs:
                    key = self._defect_key(t)
                    error_history[key] = t
                    self._touch_defect(defect_history, key, t, run_id)
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
                self._workspace_commit(
                    f"FA: {self.kata_name} — {len(written)} ADR(s) proposed, awaiting decisions")
                if "name" not in parsed:
                    self._write_log(log_dir, log)
                    return

            if "name" not in parsed:
                # RETRYABLE (2026-07-05 fix): this used to `break`, killing
                # the whole run on iteration 1 while the console claimed all
                # 5 iterations were spent — sibling of the json-parse-error
                # bug fixed 2026-07-04. A wrong-shaped response is a defect
                # the model can correct, not a run-ending condition.
                keys_seen = ", ".join(sorted(parsed.keys())[:12]) or "(empty object)"
                log.append(f"No flow spec in response — parsed JSON keys: {keys_seen}")
                print(f"  no flow spec in response (keys: {keys_seen}) — retryable defect.")
                key = "no-flow-spec"
                line = (
                    "Your previous response contained JSON, but it was not a flow "
                    f"spec (keys seen: {keys_seen}). Respond with ONE JSON object: "
                    "either the complete flow spec (with name, version, archetypes, "
                    "loci, gates, synapses, requirements) or an ADR batch "
                    "(with adrs). No illustrative JSON snippets in prose."
                )
                error_history[key] = line
                self._touch_defect(defect_history, key, line, run_id)
                self._save_defect_history(defect_history)
                errors = self._format_error_history(error_history)
                if iteration < MAX_ITERATIONS:
                    print(f"  retrying — attempt {iteration + 1}/{MAX_ITERATIONS}")
                continue

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
                    flow_path = self._commit_flow(parsed)
                    print(f"  flow committed: flow_v{self.version}.json")
                    self._write_evidence(flow_path)
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
