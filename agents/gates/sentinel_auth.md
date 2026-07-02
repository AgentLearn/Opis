---
name: sentinel_auth
kind: sentinel
input_slots:
  - name: auth_request
    type: auth_request
    required: true
output_slots:
  - name: auth_token
    type: auth_token
window_ms: 5000
refractory_ms: 0
auth_required: false
medium: internet
status: draft
confidence: llm-estimate
---

## Sentinel Auth

Receives an authentication or authorisation request from an external actor and verifies it against an auth service. On success it emits an `auth_token` that satisfies the `auth_token` requirement of any downstream protected gate. On failure it drops the request and emits nothing — the actor must retry with valid credentials. This is the canonical zero-trust boundary gate: any flow where a `source: true` locus reaches a protected gate must route through a `sentinel_auth` instance first.

## Parameters
- `window_ms`: Maximum time allowed for the auth check to complete (including any round trip to an external auth service) before the request is dropped; set to 5 000 ms to accommodate slower identity providers.
- `auth_required`: `false` — this gate produces auth tokens, it does not consume one. It is the upstream boundary, not a protected gate itself.
- `refractory_ms`: Set to 0 because rapid sequential auth attempts (retry after typo, token refresh) are permitted; brute-force rate-limiting, if needed, is the responsibility of an upstream regulator, not this gate.
