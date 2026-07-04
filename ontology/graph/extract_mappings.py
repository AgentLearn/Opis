#!/usr/bin/env python3
"""
Critical-path step 1: turn the 11 hand-written kata mapping tables (markdown) into
structured data (mappings.jsonl) — the precedent corpus for GraphRAG retrieval.

Handles the three table layouts that grew over the session:
  A. silicon:                # | behaviour | term | template(EIP) | logic | kind | gate | resolves?
  B. ripple/encore/sentry:   # | behaviour | term | movement | compute | logic | kind | resolves?
  C. batch2/batch3:          # | behaviour | term | tmpl-M | tmpl-C | logic | kind | note
Batch files hold several katas, each under a `## <Kata>` header.

Output rows: {kata, n, behaviour, term, tmpl_movement, tmpl_computation, logic, kind, gate, tokens}
`tokens` = normalized axis-value tokens (AND/OR/FIRST/THRESHOLD, router/aggregator/...,
sentinel/breaker/regulator, map/reduce/window) for matching to taxonomy nodes.
"""
import json, re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ONT = HERE.parent
OUT = ONT / "mappings.jsonl"

SINGLE = {  # filename stem -> kata id, for single-kata files
    "mapping_silicon_sandwiches_v1": ("silicon_sandwiches", "A"),
    "mapping_ripple_rides_v1": ("ripple_rides", "B"),
    "mapping_encore_tickets_v1": ("encore_tickets", "B"),
    "mapping_sentrygrid_monitoring_v1": ("sentrygrid_monitoring", "B"),
}
BATCH = {"mapping_batch2_v1", "mapping_batch3_v1"}  # multi-kata, layout C

# ## header text -> kata id (batch files)
KATA_OF_HEADER = {
    "dockyard": "dockyard_fulfillment", "triageflow": "triageflow_ed",
    "surveyorswarm": "surveyorswarm_planetary", "aegiswatch": "aegiswatch_threat_detection",
    "titantrain": "titantrain_ml_training", "oracleserve": "oracleserve_ai_inference",
    "agentmesh": "agentmesh_multiagent",
}

def clean(cell):
    c = cell.strip()
    c = re.sub(r"\*\*(.+?)\*\*", r"\1", c)      # **bold**
    c = c.replace("`", "").strip()
    return "" if c in {"—", "-", ""} else c

def tokens(logic, mov, comp, kind):
    t = set()
    blob = " ".join([logic, mov, comp, kind]).lower()
    for k in ("and","or","first","threshold"):
        if re.search(rf"\b{k}\b", blob): t.add("logic:"+k.upper())
    for k,tag in [("router","router"),("aggregat","aggregator"),("join","aggregator"),
                  ("scatter","scatter"),("filter","filter"),("gatekeeper","filter"),
                  ("splitter","splitter"),("split","splitter"),("wire","wiretap"),
                  ("observer","wiretap"),("recorder","wiretap")]:
        if k in blob: t.add("tmpl:"+tag)
    for k,tag in [("pardo","map"),("transform","map"),("domain service","map"),
                  ("compute","map"),("fusion","map"),("combine","reduce"),
                  ("reducer","reduce"),("aggregate","reduce"),("windowed","window"),
                  ("windowing","window"),("entity resolution","reduce")]:
        if k in blob: t.add("comp:"+tag)
    for k in ("sentinel","breaker","regulator"):
        if k in blob: t.add("kind:"+k)
    return sorted(t)

def parse_rows(text, layout, kata_fixed=None):
    rows, kata = [], kata_fixed
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## ") and kata_fixed is None:
            key = s[3:].split("(")[0].strip().lower().replace(" ", "")
            for hk, kid in KATA_OF_HEADER.items():
                if hk in key: kata = kid
            continue
        if not s.startswith("|"): continue
        cells = [clean(c) for c in s.strip("|").split("|")]
        if len(cells) < 7: continue
        if cells[0] in ("#","") or set(cells[1]) <= set("-: "): continue  # header/sep
        if not re.match(r"^\d+$", cells[0]): continue                     # numbered rows only
        n = cells[0]; beh = cells[1]; term = cells[2]
        if layout == "A":   # behaviour|term|template|logic|kind|gate|resolves
            mov, comp, logic, kind, gate = cells[3], "", cells[4], cells[5], cells[6]
        else:               # B and C: behaviour|term|mov|comp|logic|kind|(gate/note)
            mov, comp, logic, kind, gate = cells[3], cells[4], cells[5], cells[6], ""
        rows.append({"kata": kata, "n": int(n), "behaviour": beh, "term": term,
                     "tmpl_movement": mov, "tmpl_computation": comp,
                     "logic": logic, "kind": kind, "gate": gate,
                     "tokens": tokens(logic, mov, comp, kind)})
    return rows

def main():
    all_rows = []
    for stem,(kata,layout) in SINGLE.items():
        all_rows += parse_rows((ONT/f"{stem}.md").read_text(), layout, kata_fixed=kata)
    for stem in BATCH:
        all_rows += parse_rows((ONT/f"{stem}.md").read_text(), "C")
    all_rows = [r for r in all_rows if r["kata"]]
    with OUT.open("w") as f:
        for r in all_rows: f.write(json.dumps(r)+"\n")
    from collections import Counter
    print(f"wrote {len(all_rows)} behaviours -> {OUT.name}")
    print("by kata:", dict(Counter(r['kata'] for r in all_rows)))
    withtok = sum(1 for r in all_rows if r['tokens'])
    print(f"rows with >=1 axis token: {withtok}/{len(all_rows)}")

if __name__ == "__main__":
    main()
