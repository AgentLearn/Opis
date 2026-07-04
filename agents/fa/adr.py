"""ADR review CLI — the architect's decision loop.

Every ADR lives in the workspace repo with an explicit lifecycle:
  proposed  — FA wrote it (FA commits the proposal automatically)
  decided   — the architect chose an option (one commit per decision)
  rejected  — the architect declined the proposal (also a commit)

Usage:
  python -m agents.fa.adr <kata_name>            # interactive review of pending ADRs
  python -m agents.fa.adr <kata_name> --list     # just show pending ones

Interactive commands per ADR:
  a / b / c ...  choose that option (then optionally type a one-line rationale)
  o              write your own option (ends with a '.' on its own line)
  r              reject (then type the reason)
  s              skip for now
  q              quit
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = REPO_ROOT / "workspace"


def pending_adrs(kata: str) -> list[Path]:
    adr_dir = WORKSPACE / kata / "adrs"
    if not adr_dir.exists():
        return []
    out = []
    for p in sorted(adr_dir.glob("*.md")):
        text = p.read_text()
        m = re.search(r"## Decision\s*\n(.*)", text, re.DOTALL)
        body = m.group(1).strip() if m else ""
        lines = [l for l in body.splitlines() if l.strip() and not l.strip().startswith("<!--")]
        if not lines:
            out.append(p)
    return out


def option_labels(text: str) -> list[str]:
    return re.findall(r"^### Option (\w+)", text, re.MULTILINE)


def show(p: Path) -> None:
    text = p.read_text()
    print("\n" + "=" * 72)
    print(text.split("## Decision")[0].rstrip())
    print("=" * 72)


def write_decision(p: Path, decision: str) -> None:
    text = p.read_text()
    text = re.sub(
        r"## Decision\s*\n.*",
        f"## Decision\n\n{decision}\n",
        text, flags=re.DOTALL)
    p.write_text(text)


def commit(kata: str, message: str) -> None:
    root = WORKSPACE
    if not (root / ".git").exists():
        print("  (workspace repo not initialised — decision saved, not committed)")
        return
    subprocess.run(["git", "-C", str(root), "add", "-A"], capture_output=True)
    r = subprocess.run(["git", "-C", str(root), "commit", "-m", message],
                       capture_output=True, text=True)
    print(f"  committed: {message}" if r.returncode == 0
          else f"  commit failed: {r.stderr.strip()[:150]}")


def read_multiline(prompt: str) -> str:
    print(prompt + " (end with a single '.' line)")
    lines = []
    while True:
        line = input()
        if line.strip() == ".":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def review(kata: str) -> None:
    pend = pending_adrs(kata)
    if not pend:
        print(f"No pending ADRs for {kata}.")
        return
    print(f"{len(pend)} pending ADR(s) for {kata}.")
    for p in pend:
        show(p)
        labels = [l.lower() for l in option_labels(p.read_text())]
        while True:
            choice = input(f"\n[{'/'.join(labels)}] option, (o)wn, (r)eject, (s)kip, (q)uit > ").strip().lower()
            if choice == "q":
                return
            if choice == "s":
                break
            if choice == "r":
                reason = read_multiline("Reason for rejection")
                write_decision(p, f"**Rejected.** (User)\n\n{reason}")
                commit(kata, f"ADR {p.stem}: rejected")
                break
            if choice == "o":
                own = read_multiline("Your option (will be recorded as the Decision)")
                write_decision(p, f"**Architect's option.** (User)\n\n{own}")
                commit(kata, f"ADR {p.stem}: decided — architect's own option")
                break
            if choice in labels:
                rationale = input("One-line rationale (optional) > ").strip()
                d = f"**Option {choice.upper()}** (User)"
                if rationale:
                    d += f"\n\n{rationale}"
                write_decision(p, d)
                commit(kata, f"ADR {p.stem}: decided — Option {choice.upper()}")
                break
            print("  ?")
    print("\nDone. Re-run FA to process the decisions:")
    print(f"  python -m agents.fa.runner agents/katas/{kata}.md")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    kata = sys.argv[1].removesuffix(".md")
    if "--list" in sys.argv:
        pend = pending_adrs(kata)
        print(f"{len(pend)} pending ADR(s) for {kata}:")
        for p in pend:
            print(f"  {p.name}  [{'/'.join(option_labels(p.read_text()))}]")
        return
    review(kata)


if __name__ == "__main__":
    main()
