#!/usr/bin/env python3
import sys, json
for line in sys.stdin:
    req = json.loads(line)
    gate, run = req["gate"], req["run"]
    if gate == "EmitterA":
        body = {"order_id": "X"}
        out = [{"pulse_type": "t_a", "body": body}]
    else:  # EmitterB: run 0 mismatched key, run 1 matching key
        body = {"order_id": "Y" if run == 0 else "X"}
        out = [{"pulse_type": "t_b", "body": body}]
    print(json.dumps({"outcome": "ok", "service_ms": 1.0, "outputs": out}), flush=True)
