#!/usr/bin/env python3
"""contract_lint.py — prose-exceeds-slots static lint for gate contracts.

Motivation (2026-07-05): ALL FOUR falsifications to date are one class —
contract prose (or frontmatter) demands an inbound fact the slot signature
never declares, so the static prover proves flows in which that fact never
travels. CA's translation catches it, but only after a full FA round. This
lint shifts the class left: it runs on the contract text alone, before any
flow exists.

The four instances, as calibration corpus:
  - queue_based_estimator v1  — "pulling the current queue depth from the
    stateful locus"; interaction: pull; no response-shaped slot   (ADR-012)
  - routed_command_dispatcher v1 — "expects an acknowledgement in return";
    no ack input slot                                             (ADR-014)
  - assignment_tracker v1     — tracking_update "reflecting the agent's
    real-time position"; only input is command                    (ADR-015)
  - command_completion_recorder v1 — "obtain a completion acknowledgement";
    interaction: pull; only input is command                      (ADR-016)

Three heuristic rules, ADVISORY tier only (exit 0 clean / 2 warnings —
never 1; a heuristic must not be able to fail a build):

  R1 inbound-promise: an inbound verb (expects/awaits/obtains/receives/...)
     followed within a few words by an inbound-fact noun from a curated
     lexicon (ack/acknowledgement/response/reply/position/...), where no
     input slot name/type covers that noun (with synonyms).
  R2 internalized-pull: pull language in prose OR `interaction: pull` in
     frontmatter, with NO response-shaped slot (type/name query_response or
     ack) on EITHER side. A boundary adapter that pulls and emits the
     result as a typed output (provider_query_resolver) is legitimate; a
     gate whose pulled fact never becomes a pulse is not.
  R3 output-content promise: output prose promises content (reflecting/
     carrying/containing X) where X is a lexicon noun no input slot covers
     — the gate would have to fabricate the fact it reports.

Both verb AND noun must look inbound-fact-ish (R1/R3), so abstract objects
("obtain non-loss guarantees") stay quiet. The lexicon is deliberately
small; extend it as new falsification classes name new nouns.

Usage:
  python contract_lint.py <gates_dir | gate.md> [more paths...] [--quiet]
Archive directories are skipped unless a file inside one is named directly.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from proof import parse_gate_frontmatter  # noqa: E402

# Inbound-fact nouns worth promising: each maps to the set of slot-vocab
# stems that COVER it (a slot name or type matching any stem = covered).
INBOUND_NOUNS: dict[str, set[str]] = {
    "ack": {"ack"},
    "acks": {"ack"},
    "acknowledgement": {"ack"},
    "acknowledgements": {"ack"},
    "acknowledgment": {"ack"},
    "acknowledgments": {"ack"},
    "response": {"response", "query_response", "ack"},
    "responses": {"response", "query_response", "ack"},
    "reply": {"response", "query_response", "ack"},
    "replies": {"response", "query_response", "ack"},
    "answer": {"response", "query_response"},
    "answers": {"response", "query_response"},
    "query_response": {"query_response"},
    "position": {"position", "location"},
    "positions": {"position", "location"},
}

INBOUND_VERBS = (
    r"(?:expects?|awaits?|waits?\s+for|obtains?|receives?|listens?\s+for|"
    r"collects?|consumes?|pulls?|polls?|pulling|polling|gathers?)"
)
CONTENT_VERBS = r"(?:reflecting|carrying|containing|reporting|including)"
PULL_WORDS = r"\b(?:pull|pulls|pulling|polls?|polling)\b"
RESPONSE_SHAPED = {"query_response", "ack"}
NOUN_WINDOW = 6  # words scanned after a verb for a lexicon noun


def _slot_vocab(fm: dict) -> set[str]:
    """Stems that count as declared-inbound: input slot names and types."""
    vocab: set[str] = set()
    for slot in fm.get("input_slots", []):
        for v in (slot.get("name"), slot.get("type")):
            if v:
                vocab.add(v.lower())
    return vocab


def _covered(noun: str, vocab: set[str]) -> bool:
    stems = INBOUND_NOUNS[noun]
    return any(stem in vocab for stem in stems)


def _scan_verb_noun(body: str, verb_pattern: str) -> list[tuple[str, str]]:
    """(noun, snippet) for each verb followed closely by a lexicon noun."""
    hits: list[tuple[str, str]] = []
    for m in re.finditer(verb_pattern, body, re.IGNORECASE):
        tail = body[m.end():]
        words = re.findall(r"[A-Za-z_]+", tail)[:NOUN_WINDOW]
        for w in words:
            wl = w.lower()
            if wl in INBOUND_NOUNS:
                snippet = " ".join((body[max(0, m.start() - 20):m.end()]
                                    .split()[-4:]) + words[:NOUN_WINDOW])
                hits.append((wl, snippet.strip()))
                break
    return hits


def lint_contract(path: Path) -> list[str]:
    text = path.read_text()
    fm = parse_gate_frontmatter(text)
    body_match = re.match(r"^---\s*\n.*?\n---\s*\n", text, re.DOTALL)
    body = text[body_match.end():] if body_match else text
    vocab = _slot_vocab(fm)
    warnings: list[str] = []

    # R1 — inbound promise without a slot (first snippet per noun; the same
    # missing fact repeated across paragraphs is one defect, not four)
    r1_seen: set[str] = set()
    for noun, snippet in _scan_verb_noun(body, INBOUND_VERBS):
        if not _covered(noun, vocab) and noun not in r1_seen:
            r1_seen.add(noun)
            warnings.append(
                f"R1 inbound-promise: prose promises inbound '{noun}' "
                f"(“...{snippet}...”) but no input slot covers it "
                f"(inputs: {sorted(vocab) or 'none'})")

    # R2 — internalized pull
    interaction_pull = bool(re.search(
        r"^interaction:\s*pull\s*$", text.split("---")[1] if "---" in text
        else "", re.MULTILINE)) if text.startswith("---") else False
    pull_prose = bool(re.search(PULL_WORDS, body, re.IGNORECASE))
    if interaction_pull or pull_prose:
        both_sides: set[str] = set(vocab)
        for slot in fm.get("output_slots", []):
            for v in (slot.get("name"), slot.get("type")):
                if v:
                    both_sides.add(v.lower())
        if not (both_sides & RESPONSE_SHAPED):
            source = ("frontmatter interaction: pull" if interaction_pull
                      else "pull language in prose")
        # a gate that pulls but types the result on NEITHER side keeps the
        # pulled fact invisible to the prover — the ADR-010/012 rejected shape
            warnings.append(
                f"R2 internalized-pull: {source}, but no response-shaped "
                f"slot (query_response/ack) on either side — the pulled "
                f"fact never becomes a pulse")

    # R3 — output-content promise without an input source
    r3_seen: set[str] = set()
    for noun, snippet in _scan_verb_noun(body, CONTENT_VERBS):
        if not _covered(noun, vocab) and noun not in r3_seen:
            r3_seen.add(noun)
            warnings.append(
                f"R3 content-promise: output prose promises '{noun}' "
                f"(“...{snippet}...”) but no input slot could "
                f"supply it — the gate would fabricate the fact")

    # de-duplicate identical lines (a noun repeated across paragraphs)
    seen: set[str] = set()
    return [w for w in warnings if not (w in seen or seen.add(w))]


def collect_files(args: list[str]) -> list[Path]:
    files: list[Path] = []
    for a in args:
        p = Path(a)
        if p.is_dir():
            files.extend(sorted(
                f for f in p.glob("*.md")
                if f.stem != "index" and f.parent.name != "archive"))
        elif p.suffix == ".md":
            files.append(p)
    return files


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    quiet = "--quiet" in sys.argv
    if not args:
        args = ["agents/gates"]
    files = collect_files(args)
    if not files:
        print("contract_lint: no gate contracts found", file=sys.stderr)
        return 0

    total = 0
    for f in files:
        warnings = lint_contract(f)
        if warnings:
            total += len(warnings)
            print(f"[contract-lint] {f}")
            for w in warnings:
                print(f"  ⚠ {w}")
        elif not quiet:
            print(f"[contract-lint] {f.name}: clean")
    if total:
        print(f"[contract-lint] {total} warning(s) across "
              f"{len(files)} contract(s) — ADVISORY: prose-exceeds-slots "
              f"suspects; not a failure.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
