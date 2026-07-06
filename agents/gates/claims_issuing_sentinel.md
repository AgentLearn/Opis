---
name: claims_issuing_sentinel
kind: sentinel
input_slots:
  - name: auth_request
    type: auth_request
    required: true
output_slots:
  - name: auth_token
    type: auth_token
  - name: denial_event
    type: event
window_ms: 200
refractory_ms: 0
auth_required: false
medium: local
---

## Claims Issuing Sentinel

Validates an incoming credential against locally-held, periodically-synchronized credential and revocation state in a single round-trip, with no external query/response pair. On success it issues a short-TTL token carrying signed, scoped claims for downstream protected gates. On failure it emits an audit event and issues no token.

## Parameters
- `window_ms`: Time budget for completing local validation against the synced credential/revocation store before treating the request as expired.
- `refractory_ms`: Set to 0 — each auth_request is evaluated independently with no forced cooldown between issuances.
- `auth_required`: False. This gate is itself the sentinel that establishes authorization for downstream gates; it does not sit behind another auth check.
- `medium`: Local, since validation is performed against locally cached state rather than by querying a remote verifier.
- Revocation guarantee: bounded by the staleness of the local sync period plus the token's TTL, not by a per-issuance external check.