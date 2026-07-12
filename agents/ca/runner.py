#!/usr/bin/env python3
"""
CA runner — implement + co-sim a kata's committed flow.

Usage:
  python -m agents.ca.runner                    # every kata with a committed flow
  python -m agents.ca.runner silicon_sandwiches # one kata
  python -m agents.ca.runner opis_workbench --env opis_repo
                                                # keyed (kata × environment) run

--env <name> (or CA_ENV) resolves agents/environments/<name>.md; a named
environment that doesn't resolve refuses the run. Unkeyed runs are legal
but environment-blind (loud legacy warning).
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
    args = sys.argv[1:]
    env = None
    if "--env" in args:
        i = args.index("--env")
        if i + 1 >= len(args):
            sys.exit("--env requires a name (agents/environments/<name>.md)")
        env = args[i + 1]
        del args[i:i + 2]
    names = args or katas_with_flows()
    if not names:
        print("No katas with a committed flow_vN.json found in workspace/ — "
              "run FA first (CA implements proved flows only).")
        sys.exit(0)
    for name in names:
        print(f"\n{'=' * 60}\nCA — kata: {name}"
              f"{f' × env: {env}' if env else ''}\n{'=' * 60}")
        from agents.ca.agent import CAAgent
        CAAgent(name, environment=env).run()


if __name__ == "__main__":
    main()
