#!/usr/bin/env python3
"""
CA runner — implement + co-sim a kata's committed flow.

Usage:
  python -m agents.ca.runner                    # every kata with a committed flow
  python -m agents.ca.runner silicon_sandwiches # one kata
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = REPO_ROOT / "workspace"


def katas_with_flows() -> list[str]:
    out = []
    for d in sorted(WORKSPACE.iterdir()) if WORKSPACE.exists() else []:
        if d.is_dir() and any(re.match(r"flow_v\d+$", p.stem)
                              for p in (d / "flow").glob("flow_v*.json")):
            out.append(d.name)
    return out


def main():
    names = sys.argv[1:] or katas_with_flows()
    if not names:
        print("No katas with a committed flow_vN.json found in workspace/ — "
              "run FA first (CA implements proved flows only).")
        sys.exit(0)
    for name in names:
        print(f"\n{'=' * 60}\nCA — kata: {name}\n{'=' * 60}")
        from agents.ca.agent import CAAgent
        CAAgent(name).run()


if __name__ == "__main__":
    main()
