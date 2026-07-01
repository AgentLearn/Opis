#!/usr/bin/env python3
"""
FA runner — drop a kata .md into agents/input/ and run this script.

Usage:
  python -m agents.fa.runner                         # processes all katas in agents/input/
  python -m agents.fa.runner agents/katas/my.md      # run a specific kata
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = REPO_ROOT / "agents" / "input"


def main():
    if len(sys.argv) > 1:
        paths = [Path(sys.argv[1])]
    else:
        paths = sorted(INPUT_DIR.glob("*.md"))
        if not paths:
            print(f"No kata files found in {INPUT_DIR}")
            sys.exit(0)

    for path in paths:
        if not path.exists():
            print(f"Kata not found: {path}")
            sys.exit(1)
        print(f"\n{'='*60}")
        print(f"Processing kata: {path.name}")
        print(f"{'='*60}")
        from agents.fa.agent import FAAgent
        agent = FAAgent(path)
        agent.run()


if __name__ == "__main__":
    main()
