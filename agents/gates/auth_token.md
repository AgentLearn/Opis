---
name: auth_token
kind: sentinel
input_slots:
  - name: auth_request
    type: auth_request
    required: true
  - name: entitlement_response
    type: query_response
    required: true
output_slots:
  - name: entitlement_query
    type: query
  - name: auth_token
    type: auth_token
  - name: rejection
    type: event
window_ms: 3000
refractory_ms: 500
auth_required: false
medium: lan
---

## Auth Token

This sentinel consumes an incoming auth_request and issues an entitlement_query to an upstream identity locus rather than deciding locally, ensuring revocation and scope changes are reflected immediately. On receiving the entitlement_response it emits an auth_token when the actor is currently entitled, or a rejection event when the credential has been revoked, expired, or fails scope checks. It is designed to sit upstream of every gate marked auth_required, gating access on a fresh, per-request authority decision.

## Parameters
- `window_ms`: maximum time allowed to wait for the entitlement_response before the request is treated as failed and a rejection event is emitted.
- `refractory_ms`: minimum interval between successive auth_request evaluations for the same actor, preventing rapid re-query flooding of the identity locus.
- `auth_required`: false — this gate itself is the source of authorisation for other gates and does not require a token to be invoked.
- `medium`: lan — reflects the network round-trip to the identity locus required for every evaluation, distinguishing this from a stateless, locally-verified alternative.