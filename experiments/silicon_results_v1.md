# Results — "hey, I need something like this" vs Opis
# Specimen: silicon_sandwiches · Checklist: silicon_baseline_checks_v1.md (pre-registered)

Scored 2026-07-07. Scorer: Claude (Fable), the same model family that ran the
condition-A baselines and played roles in condition B's agents — disclosed as
a scoring-bias caveat; every verdict below carries an evidence pointer so a
skeptic can re-score without trusting the scorer.

## Conditions

- **A1–A3:** Claude Code 2.1.202 (model Fable), fresh folders, prompt = "I
  need something like this — build it." + kata verbatim. All three produced
  runnable TypeScript with passing test suites (A1: 14/14, A2: 16/16,
  A3: 11/11 — re-verified in sandbox, Node 22).
- **B:** flow_v4 + evidence_v4 (real FA/CA runs, full gauntlet incl.
  forge-on-the-wire tamper).
- **Question logs:** A1, A2, A3 asked the human **zero questions** (verified
  against all three transcripts: no AskUserQuestion calls, no interrogative
  assistant text). Condition B's question log = the ADR register (22 ADRs).
- Adversarial probes (fake payment, provider-down, accrual trigger,
  cross-tenant write) were executed live in the sandbox against each A
  artifact; transcripts reproduced below.

## Scoring sheet (MET / PARTIAL / ABSENT)

| Check | A1 | A2 | A3 | B |
|-------|----|----|----|---|
| R-1 payment gates kitchen | PARTIAL | PARTIAL | PARTIAL | **MET** |
| R-2 create→validate→submit | MET | MET | MET | **MET** |
| R-3 estimate from live queue | MET | MET | MET | **MET** |
| R-4 ≥2 mapping services aggregated | MET | MET | MET | **MET** |
| R-5 correct shop | MET | MET | MET | **MET** |
| R-6 dispatch+tracking, pickup-optional | MET | MET | MET | **MET** |
| R-7 owners edit only own menu | MET | MET | **ABSENT** | **MET** |
| R-8 loyalty accrues from completed orders | PARTIAL | PARTIAL | PARTIAL | **MET** |
| S-1 tenant isolation server-side | ABSENT | ABSENT | ABSENT | **MET** |
| S-2 no self-attestation | ABSENT | ABSENT | ABSENT | **MET** |
| S-3 forged/expired creds rejected | ABSENT | ABSENT | ABSENT | PARTIAL |
| S-4 rejection visible | MET | MET | ABSENT | **MET** |
| S-5 payment race | PARTIAL | PARTIAL | ABSENT | **MET** |
| F-1 mapping service down → loud | ABSENT | ABSENT | ABSENT | PARTIAL |
| F-2 payment failure → loud | MET | MET | MET | **MET** |
| DRIFT tally (D-1..D-4) | 0 | 0 | 1 | 0 |
| **Q-3 silent decisions (headline)** | **10** | **10** | **10** | **2** |
| Q-1 / Q-2 / Q-4 | 0/0/0 | 0/0/0 | 0/0/0 | 20/0/2 |
| Silent-failure tally | 1 | 1 | 2 | 0 |

**Best-of-3 (condition A) = A2** (tie with A1 on verdicts; A2 has the larger
test suite, dispatch-at-ready semantics, and explicit redemption + refund).

**Headline row, best-A vs B:** requirements 6 MET / 2 PARTIAL vs 8 MET;
safety 1 MET / 1 PARTIAL / 3 ABSENT vs 4 MET / 1 PARTIAL; silent decisions
10 vs 2; silent failures 1 vs 0.

## Verdict evidence, check by check

### R-1 — Payment gates the kitchen
- **A1/A2 PARTIAL.** Happy path enforced (declined payment throws, queue
  untouched — covered by their own tests). But the probe includes *fake the
  payment step*, and pass requires *structurally impossible*. Sandbox probe:
  `kitchen.submit(order, {status:'confirmed'})` (A1) and a fabricated order
  with `status:'paid', paymentId:'pay_fabricated'` (A2) were **accepted** —
  the kitchen trusts caller-supplied payment state; nothing binds the claim
  to an actual charge.
- **A3 PARTIAL.** Facade sequencing enforces order, but `KitchenQueue.submit`
  has **no payment check at all**; direct submission of an unpaid order was
  accepted silently (probe transcript below).
- **B MET.** Static proof REQ-1 at `PaymentAuthorizer:confirmed`: no synapse
  path reaches KitchenDispatcher without the authorizer's confirmed outcome —
  structurally impossible by topology, not by caller discipline. Exercised
  dynamically in 1000-run co-sim with 14 real gate implementations
  (evidence_v4.json, static + cosim layers).

### R-2 — Create → validate → submit
All four MET. A1: `validate()` before `kitchen.submit`, invalid orders throw.
A2: basket validation blocks before payment; kitchen re-checks status. A3:
explicit create→validate→submit with defensive re-checks. B: OrderValidator
gate, REQ-2 proved; `rejected → invalid_order → Customer` path exists.

### R-3 — Estimate from live queue
All four MET. A1/A2/A3 compute from current queue length (each has a passing
"estimate grows with queue" test). B: REQ-3 proved; QueueEstimator consumes
`queue_length_response` pulled live by KitchenQueueResolver (the ADR-012
redesign — the original pull-in-estimator contract was CA falsification #1).

### R-4 — ≥2 mapping services, aggregated
All four MET. A1/A2/A3: two provider adapters queried in parallel,
fastest-duration wins — both consulted, neither decorative. B: REQ-4 proved;
MapResolverA+B AND-joined by RoutingAggregator (both responses required).

### R-5 — Correct shop
All four MET. A-runs: per-shop queues keyed by routing choice, each with a
passing routing test. B: REQ-5 proved at `KitchenDispatcher:kitchen_submission`.

### R-6 — Dispatch + live tracking, pickup-optional
All four MET. A1: dispatch at checkout, deterministic tick-based positions.
A2: dispatch when kitchen marks ready, re-routed for current traffic,
position events. A3: event-stream tracking. Pickup demands no driver
machinery in any of them. B: REQ-6 proved; `driver_position` push
(ADR-015/021); pickup degradation honest by design.

### R-7 — Owners edit only their own menu
- **A1/A2 MET** at the probe's level: cross-tenant write refused with a loud
  error (both demo'd and tested). The *binding* is client-supplied — that
  failure is S-1's, not R-7's.
- **A3 ABSENT.** No owner identity exists anywhere in the artifact. Sandbox
  probe: arbitrary caller set shop B's BLT price to 1 cent. No refusal
  mechanism to probe.
- **B MET.** REQ-7 proved at `MenuWriter:committed`, partition-scoped writes;
  plus the tamper co-sim below.

### R-8 — Loyalty accrues from completed orders
- **A1/A2/A3 PARTIAL.** Rewards apply at checkout correctly (capped, refunded
  on decline — good). But all three accrue points **at payment time**.
  Probe: an order that never completed had already earned 11 points (A1
  transcript below; A2 `earnFromPurchase` at checkout step 6; A3 `earn` at
  step 5). The pre-registered pass condition — *an uncompleted order accrues
  nothing* — fails in all three.
- **B MET.** `event_reward_accumulator` (ADR-013): accrual fires only on
  completion events from the recorders; reward applied at checkout via the
  payment path. REQ-8 proved; LoyaltyAccumulator exercised in co-sim.

### S-1 — Tenant isolation server-side
- **A1/A2 ABSENT.** The owner-to-menu binding is checked against a plain
  `ownerId` parameter the caller supplies — exactly the checklist's
  "owner_id in the request body counts as FAIL". No authenticated subject
  exists. **A3 ABSENT** (no binding at all).
- **B MET.** MenuAuthSentinel (its own locus) issues signed short-TTL scope
  claims; MenuWriter validates the HMAC locally. The subject never supplies
  its own scope.

### S-2 — No self-attestation
- **A1/A2/A3 ABSENT.** Callers self-declare identity; the party being
  authorized supplies the claim that authorizes it.
- **B MET — and this class was caught, not assumed.** flow_v1 bound both
  resolvers to FranchiseOwner, the very subject being authorized
  (falsification #5); ADR-017/019 redesigned to an issuing sentinel. The
  register shows the catch and the fix.

### S-3 — Forged/expired credentials rejected
- **A1/A2/A3 ABSENT.** No credentials exist to forge or expire.
- **B PARTIAL.** Forge-on-the-wire tamper co-sim: signature corrupted at
  synapse delivery → MenuAuthSentinel **denied 1000/1000** (normal run:
  issued 1000/1000, MenuWriter committed 1000; tampered: MenuWriter never
  fires — twin_cosim.json vs twin_tampered.json). The **expired-token
  replay** half of the probe is contractual (short-TTL claims, expiry in the
  HMAC canonical string) and present in generated code, but was not
  dynamically exercised in evidence_v4 — scored PARTIAL under the
  pre-registered "can't demonstrate = hasn't met" rule.

### S-4 — Rejection is visible
- **A1/A2 MET:** cross-tenant and payment rejections throw distinct, loud
  errors. **A3 ABSENT:** no authorization rejection can be caused (no
  mechanism), so none can be visible.
- **B MET.** `denied` is a distinct sentinel outcome; MenuWriter has an
  explicit `rejected → notification` path. (v3's MenuWriter lacked it —
  the silent-rejection class was caught by a tamper alarm and fixed in v4.)

### S-5 — Payment race
- **A1/A2 PARTIAL.** Single-process sequential await — the ordering holds by
  construction in the happy path, but the kitchen boundary accepts
  caller-asserted payment state (see R-1), so the guarantee doesn't survive
  reordered/forged submission. **A3 ABSENT:** kitchen has no guard at all.
- **B MET.** The ordering is a join, not a convention: kitchen submission
  cannot fire without the validated-order pulse, which cannot fire without
  payment confirmation. 1000-run co-sim under randomized latencies, no
  ordering violation path exists in the topology.

### F-1 — Mapping service down → loud
- **A1/A2/A3 ABSENT (+1 silent-failure each).** All three use
  `Promise.allSettled` and silently continue with whichever provider
  answered. Sandbox probe (A1, A2): one provider dead → route returned, no
  warning surfaced anywhere. A2 even has a test enshrining the silent
  tolerance ("planner survives one provider failing"). The kata demands two
  traffic-aware services; silent degradation to one is the exact failure
  mode the check targets.
- **B PARTIAL.** The AND-join makes a silent wrong route structurally
  impossible — one provider down means the routing decision never fires
  (fail-stop, not fail-wrong). But the stall itself has no explicit loud
  notification path in flow_v4, and the provider-down scenario was not
  dynamically exercised in evidence_v4. Fail-stop ≠ loud; PARTIAL.

### F-2 — Payment provider failure → loud
All four MET. A1: PaymentDeclinedError with reason, points refunded, kitchen
untouched. A2: same plus refund test. A3: `accepted:false` with reason. B:
`failed → payment_failure → Customer` synapse, direct.

### D-checks — drift
- **A1: 0. A2: 0.** Both stayed inside the kata's world; provider names are
  stand-ins for the two required mapping services, not invented actors.
- **A3: 1.** A corporate/franchise two-layer menu system (CorporateMenu
  baseline + per-shop overrides/removals) — substantial unrequested
  structure, never surfaced as a question (D-3).
- **B: 0.** Loci = exactly the kata's actors (Customer, PaymentProcessor,
  Kitchen, MappingProvider, Driver, FranchiseOwner). ADR-018's attempt to
  invent an IdP locus was **rejected** on doctrine — the register records
  drift being refused.

### Q-checks — decision surfacing (headline)
Genuine design decisions embedded in every condition-A artifact, none ever
surfaced (all three transcripts contain zero questions): payment-confirmation
semantics; queue-estimate model (base + per-order constants); aggregation
rule (min duration); tenant-binding mechanism (or its omission, A3); accrual
trigger (payment vs completion); redemption economics (100 pts = $5 blocks /
5¢ per point); provider-failure policy (silent tolerance); driver-assignment
policy (nearest / FIFO); dispatch timing (checkout vs ready); points-refund
policy. **Q-3 = 10 each, Q-1 = Q-2 = 0.**

Condition B: 22 ADRs. 20 decided with options and consequence evidence
(several carrying falsification/lint evidence for why the default was wrong)
→ **Q-1 = 20**. Two were rejected bug artifacts (018, 022) → Q-4 = 2.
Honest remainder: gate `window_ms` policies and the reward→discount
conversion rate are decided-in-artifact or deferred to instance config
without a surfaced question → **Q-3 = 2**.

### Silent-failure tally
- A1: 1 (silent provider degradation). A2: 1 (same, test-enshrined).
- A3: 2 (silent provider degradation; kitchen silently accepts unpaid
  orders — no check, no error, no log).
- B: 0 in the artifact. Tool-level caveat, disclosed: da-twin's
  declared-flows fallback on empty outputs is a known reporting distortion
  (strategy.md), unrelated to any scored check.

## Probe transcripts (sandbox, Node 22, 2026-07-07)

```
A1  R1-FAKE: kitchen ACCEPTED order with fabricated payment. queue= 1
A1  F1: provider dead -> google-maps route returned; silent
A1  R8: order status = in-kitchen (not completed); points earned = 11
A2  R1-FAKE: ACCEPTED, queue= 1
A2  F1: one provider dead -> route from atlas - silent
A3  R1-FAKE: kitchen queue accepted unpaid order, length = 1
A3  R7: arbitrary caller set shop B BLT price to 1 cents — no owner check exists
B   tamper co-sim: MenuAuthSentinel issued 1000/1000 (normal) -> denied 1000/1000 (tampered);
    MenuWriter committed 1000 -> never fires. harness: 14 gates, 0 failures.
```

## What the baselines got right (owed in fairness)

All three A-runs are competent code: clean module boundaries, real test
suites, correct happy-path behavior on 6 of 8 requirements, loud payment
declines with points refunds, and honest pickup/delivery separation. The
gap is not competence — it is that every architectural decision was made
silently, the two requirements whose semantics needed a human (R-8 accrual
trigger) or an adversary (R-1 fake payment) were quietly resolved the
convenient way, and the entire S-column (the authorization surface) does
not exist. Nothing in the baseline process would ever tell its operator
that. Condition B's register shows the same classes of mistake being made —
then caught, argued, and fixed, with the evidence retained.

## Objection: "the A-runs just built a demo — a demo is happy-path by nature"

Fair, and worth answering directly rather than in a footnote.

1. **Demo scope was never requested; it was silently assumed.** The prompt
   is a client saying "I need something like this — build it," and the kata
   speaks in "must" language. "Throwaway demo or the real thing?" is a
   genuine fork with consequences — exactly the kind a competent engineer
   surfaces in the first meeting. Zero questions were asked in all three
   runs. Had the question been asked and answered "demo," the S-column
   would honestly read *out of scope by agreement*. There was no agreement.
   The scope choice is Q-3 silent decision number one.
2. **The artifacts don't claim demo scope — they claim the invariant.**
   In their own prose: A1, "Submission is the hard gate for the core
   business rule"; A2, "Hard-gates on payment: an order without a confirmed
   payment never reaches a kitchen ticket"; A3, "The invariant lives here:
   nothing reaches a kitchen until the payment gateway has confirmed the
   charge." The sandbox probe broke all three. A demo that says "demo" is
   honest; a demo that documents guarantees held only by caller politeness
   is the silent-failure class with documentation.
3. **The S-checks are not gold-plating on a demo.** They test whether
   stated kata requirements are real. "Franchise owners update their own
   menu" with no identity binding is not a smaller version of the feature —
   it is the feature's name attached to its absence (A3 has no owner
   concept anywhere in the artifact).
4. **The comparison is symmetric.** Condition B is also a non-deployable
   simulation, its dynamic evidence is labeled bounded, and it took two
   PARTIALs under the same pre-registered rule. The experiment was never
   demo-vs-product; it measures which process forces the demo-or-real
   conversation to happen at all.

## Scoring caveats (pre-empting "show me")

1. Scorer = Claude; conditions A were also Claude. Bias risk runs *toward*
   condition A if anywhere; every verdict has a pointer for re-scoring.
2. B's dynamic evidence is bounded (sandbox twin/co-sim), and B scored two
   PARTIALs (S-3 expiry replay unexercised; F-1 fail-stop but not loud) —
   scored against B by the same rule that scored the A-runs.
3. Both conditions are simulations; neither shipped to production. The
   comparison is about which process surfaces decisions and failure modes,
   not which artifact is deployable today.
