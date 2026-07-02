# Test residue — regenerated, no authority

Everything under this folder is produced by re-running katas from a blank slate.

- `flow/flow_vN.json` — kept in git **only** as regression baselines for
  `tools/opis-eval/regress.py` (the golden corpus).
- `adrs/`, `logs/`, `fa_defect_history.json`, `tests/` — documentation of past
  runs. They are not design artifacts, carry no authority, and are never traced
  as justification for gate contracts (see `agents/gates/index.md` for how
  contracts actually earn their status).

Deleting this folder and re-running the katas is expected to reproduce it.
