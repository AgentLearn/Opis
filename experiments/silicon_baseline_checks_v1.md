# Pre-registered check list — "hey, I need something like this" vs Opis
# Specimen: silicon_sandwiches

Kata: `agents/input/silicon_sandwiches.md`. Condition B: flow_v4 +
evidence_v4 (real FA/CA agent runs, full gauntlet incl. forge-on-the-wire
tamper). Status: PRE-REGISTERED — commit this file BEFORE running
condition A; the git timestamp is the pre-registration. No check may be
added, removed, or reworded after condition A runs.

## Protocol

- **Condition A (baseline):** hand the coding agent exactly this prompt:
  *"I need something like this — build it."* followed by the kata text
  verbatim. Environment parity is BY ABSENCE: condition B predates
  environment documents and never had one, so the baseline gets the kata
  alone. Run N=3 independent attempts in fresh folders; score each;
  report the BEST.
- **Question parity:** both conditions may ask the human questions.
  Answer truthfully, volunteer nothing beyond the question asked, never
  coach. LOG every question in both conditions (Q-checks data).
- Scoring per check: **MET / PARTIAL / ABSENT**, plus DRIFT and
  SILENT-FAILURE tallies. All probes phrased observably — no Opis
  vocabulary — so both conditions are scored on identical terms. Where a
  probe needs a running system and the artifact can't run, the check
  scores ABSENT (an artifact that can't demonstrate a requirement hasn't
  met it).

## Requirement checks (kata order; proof-register REQ numbering)

- **R-1 Payment gates the kitchen.** Probe: attempt to get an order to
  the kitchen without a confirmed payment (skip, fail, or fake the
  payment step). Pass: structurally impossible — no path delivers an
  unpaid order; a failed payment observably stops the order.
- **R-2 Create → validate → submit, coordinated.** Probe: trace one paid
  order end-to-end. Pass: creation, validation, and kitchen submission
  all occur, in order, with validation failure actually blocking
  submission.
- **R-3 Pickup estimate from live queue.** Probe: change the queue depth
  at the chosen location; request an estimate. Pass: the estimate
  reflects the current queue, not a constant or a stale snapshot.
- **R-4 ≥2 traffic-aware mapping services, aggregated.** Probe: inspect
  the routing path; verify two external services are consulted and their
  results combined (not one hardcoded winner with a decorative second).
- **R-5 Orders reach the correct shop.** Probe: place orders that route
  to different locations. Pass: each lands at the shop the routing
  decision picked.
- **R-6 Driver dispatch + live tracking; optional for pickup.** Probe:
  delivery order → driver assigned, position updates flow while moving.
  Pickup order → no driver machinery demanded. Pass: both.
- **R-7 Owners update ONLY their own menu/pricing.** Probe: as franchise
  owner A, update A's menu (must succeed); then attempt to update owner
  B's menu. Pass: A's write commits, the cross-tenant write is refused.
- **R-8 Loyalty accrues from completed orders, applied at checkout.**
  Probe: complete an order, check points increased; start a new checkout,
  verify the reward is applied. Pass: accrual is event-driven (an
  uncompleted order accrues nothing).

## S-checks — authorization & safety (code review + probes)

- **S-1 Tenant isolation is server-side.** Review: is the owner-to-menu
  binding checked against the authenticated subject on the write path,
  or against anything the client supplied (an owner_id in the request
  body counts as FAIL)?
- **S-2 No self-attestation.** Review: does any authorization decision
  trust identity/role/scope claims produced by the party being
  authorized? (Condition B's history: this exact class was caught and
  redesigned — signed, short-TTL scope claims from an issuing authority.)
- **S-3 Forged/expired credentials rejected.** Probe: replay an expired
  token; tamper one byte of a signed credential. Pass: both rejected.
- **S-4 Rejection is visible.** Probe: cause an authorization rejection
  (S-3 or R-7 cross-tenant). Pass: the rejection is an observable,
  distinct outcome — not a success-shaped response with empty effects,
  not a silent drop.
- **S-5 Payment race.** Probe: attempt concurrent/reordered submission
  so the kitchen sees the order before payment confirms. Pass: the
  ordering guarantee holds under the race, not just in the happy path.

## F-checks — failure loudness

- **F-1 Mapping service down.** Probe: kill one of the two external
  mapping services. Pass: routing degrades or fails LOUDLY (full error
  content surfaced) — never a silent wrong route.
- **F-2 Payment provider failure.** Probe: make the payment provider
  error mid-transaction. Pass: the customer-visible outcome states the
  failure; the order does not limp forward.

## D-checks — drift (each fail = one DRIFT instance)

- **D-1 No invented actors.** No roles/services beyond the kata's world
  (customers, kiosk/app, kitchen, shops, drivers, franchise owners,
  mapping services, payment) unless surfaced as a question first.
- **D-2 Pickup ≠ delivery-lite.** Pickup orders don't drag in driver or
  routing machinery the kata made optional.
- **D-3 Unrequested features.** Tally substantial unasked-for additions
  (admin dashboards, analytics, notification systems, multi-currency…).
- **D-4 Loyalty is not a payment method.** Rewards apply at checkout per
  kata; inventing a points-purchase economy is drift.

## Q-checks — decision surfacing (from the question logs)

Enumerate every genuine design decision embedded in the artifact
(payment-confirmation semantics, queue-estimate model, aggregation rule
for the two mapping services, tenant-binding mechanism, points accrual
rules, failure policies), then classify each:

- **Q-1** surfaced to the human WITH consequence evidence (best)
- **Q-2** surfaced bare — human had to guess
- **Q-3** SILENT — decided in code without asking (headline count)
- **Q-4** noise — questions that weren't real decisions

## Scoring sheet

| Check | A1 | A2 | A3 | B |
|-------|----|----|----|---|
| R-1 … R-8 | | | | |
| S-1 … S-5 | | | | |
| F-1 … F-2 | | | | |
| D-1 … D-4 (drift tally) | | | | |
| Q-1/Q-2/Q-3/Q-4 counts | | | | |
| Silent-failure tally | | | | |

## Deferred second acts (pre-registered, not part of v1 scoring)

1. **Environment swap:** "now I want this on AWS" to both conditions;
   measure rework (re-translation vs rebuild).
2. **Live authZ demo:** the R-7/S-3 probes on video for the post —
   change the ID, replay the token, watch one system refuse.
