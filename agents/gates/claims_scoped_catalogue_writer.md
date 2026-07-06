---
name: claims_scoped_catalogue_writer
kind: gate
input_slots:
  - name: menu_update
    type: menu_update
    required: true
  - name: auth_token
    type: auth_token
    required: true
output_slots:
  - name: event
    type: event
  - name: notification
    type: notification
window_ms: 3000
refractory_ms: 250
auth_required: true
medium: local
---

## Claims Scoped Catalogue Writer

This gate commits a catalogue write in a single round by deriving write authorization directly from the presented token rather than performing a runtime verification round-trip. It validates the token's signature and TTL locally, then checks the incoming update's target partition against scope claims embedded in the token at issuance. On success it emits `event` for the committed write; on scope violation, signature failure, or stale TTL it emits `notification` instead.

## Parameters
- `window_ms`: the maximum age, from token issuance to write attempt, within which the embedded scope claims are still considered fresh enough to honor; requests arriving outside this window are treated as stale and rejected via `notification`.
- `refractory_ms`: minimum spacing enforced between successive writes accepted from the same token, preventing rapid repeated commits from a single credential.
- `auth_required`: true — the token consumed here must originate from a sentinel_auth instance upstream, which is responsible for embedding the signed, short-TTL partition-scope claims and performing revocation checks at issuance time. This gate performs no external verification of its own; the entire authorization guarantee is bounded by the token's TTL and the issuing sentinel's revocation check.