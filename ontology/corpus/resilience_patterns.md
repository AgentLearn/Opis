# Seed corpus: Resilience / Stability Patterns (gate KIND axis)

Sources (authoritative):
- Michael T. Nygard, "Release It! Design and Deploy Production-Ready Software",
  2nd ed., Pragmatic Bookshelf, 2018 — stability patterns & antipatterns.
- Microsoft Azure Architecture Center, "Cloud Design Patterns" (Reliability category):
  https://learn.microsoft.com/en-us/azure/architecture/patterns/
  incl. Circuit Breaker, Bulkhead, Throttling, Retry, Gatekeeper.

Role in the SA taxonomy: the **kind axis**. Opis gate `kind` (plain / regulator /
breaker / sentinel) declares a gate's *stability role* — how it protects the flow, not
what message transformation it performs (that's the template axis) or how it joins inputs
(logic axis). Resilience patterns are the established vocabulary for exactly these roles.

Each entry: name | source | stability semantics | Opis gate-kind relevance.

---

## Failure-isolation patterns

- **Circuit Breaker** (Nygard; Azure) — wraps a protected call; after failures reach a
  threshold it "trips" and fails fast without attempting the call, then after a timeout
  moves to half-open to test recovery, closing again on success. Opis: **`kind: breaker`
  directly** — `trips_on` (threshold) + `recovery_ms` (timeout to half-open). Exact match;
  this is the source-of-truth definition for the breaker kind.

- **Bulkhead** (Nygard; Azure) — partitions resources (connection pools, threads) so a
  failure in one partition cannot exhaust resources needed by others; isolation by
  compartment. Opis: a **`kind: regulator`** variant that isolates a downstream resource
  pool. No dedicated Opis primitive for compartment isolation — candidate refinement of
  regulator.

- **Steady State** (Nygard) — every mechanism that accumulates a resource must have a
  mechanism that recycles it; avoid unbounded growth (logs, caches, data). Opis: relates
  to regulator / throttle keeping downstream load bounded; systemic, not a single kind.

## Load / rate-control patterns

- **Throttling** (Azure) — controls the consumption of resources by limiting the rate of
  requests, shedding or queuing excess to protect a service. Opis: **`kind: regulator`**
  with rate logic — `zone_regulator`, `repeat_event_throttle` are this pattern.

- **Rate Limiting / Governor** (Nygard "Governor") — deliberately slows the rate of a
  dangerous action to keep the system in a safe envelope (a governor resists runaway).
  Opis: **`kind: regulator`** — the rate-limiting core of the regulator kind. Also relates
  to the refractory period (`recovery_ms`) as a per-actor rate limit (rider cooldown).

- **Load Shedding** (Nygard) — under overload, reject low-priority work early rather than
  degrade everything. Opis: regulator + reject outcome; relates to breaker fail-fast.

- **Backpressure / Queue-Based Load Leveling** (Azure) — a buffer/queue between producer
  and consumer smooths bursts so the consumer is never overwhelmed. Opis:
  `queue_based_estimator` / buffered inputs; ties to the Persistent Trigger gap (buffering
  has no gate-logic primitive, lives in gate internals).

## Fail-fast / gatekeeping patterns

- **Fail Fast** (Nygard) — if a request is bound to fail, detect it and fail immediately
  (validate resources/preconditions up front) rather than after expensive work. Opis: a
  guard/validation gate; relates to `order_validator` checking preconditions before money
  moves (the ADR-003 Option-B rationale exactly).

- **Gatekeeper** (Azure) — a dedicated brokering/validation instance sits in front of a
  protected resource, validating and sanitizing requests, never exposing the resource
  directly. Opis: **`kind: sentinel` directly** — the auth/validation guard in front of a
  protected gate (`auth_token` sentinel issuing/verifying tokens). Source definition for
  the sentinel kind.

- **Handshaking** (Nygard) — a server signals a client whether it can accept work, so
  callers back off when it is busy (cooperative admission control). Opis: relates to
  sentinel + regulator admission; no dedicated primitive.

## Recovery patterns

- **Retry** (Azure) — transparently retry a transient failure, typically with backoff.
  Opis: no gate kind — retry is a per-synapse / gate-internals concern (relates to CA
  implementation and twin timing), deliberately below the flow layer. Boundary note.

- **Timeout** (Nygard) — never wait forever for a response; bound every external wait.
  Opis: **`input_timeout_ms`** — the window/timeout budget on gate inputs. The timing
  layer that the control-flow and EIP corpora both lack; here it is a first-class
  resilience pattern, confirming Opis's timing fields are grounded in this literature.

## Antipatterns (Nygard) — what gates defend against (context, not kinds)
Cascading Failures, Slow Responses, Unbounded Result Sets, Integration Points,
Blocked Threads, Self-Denial Attacks. Opis: these are the failure modes breaker/regulator/
sentinel exist to contain — useful as the "why" in gate descriptions, not taxonomy nodes.

---

## Cross-reference: resilience pattern -> Opis gate kind (curator's mapping, to test)

| resilience pattern | Opis gate kind |
|--------------------|----------------|
| Circuit Breaker | `kind: breaker` (trips_on + recovery_ms) — EXACT source definition |
| Gatekeeper | `kind: sentinel` — EXACT source definition |
| Throttling / Governor / Rate Limiting | `kind: regulator` |
| Bulkhead | `kind: regulator` (isolation variant) |
| Timeout | `input_timeout_ms` (timing field, not a kind) |
| Backpressure / Queue-Based Leveling | queue_based_estimator / buffered input (gap) |
| Retry | below flow layer (synapse / gate internals / CA) |
| Fail Fast | guard/validation gate (plain kind + reject outcome) |

## Kind-axis observations (candidate findings, to confirm by induction)
- **All three non-plain Opis kinds have exact source definitions in this literature:**
  breaker = Circuit Breaker, sentinel = Gatekeeper, regulator = Throttling/Governor.
  The kind axis is the best-grounded of the three axes — Opis did not invent these.
- **Timeout confirms the timing layer is grounded**, not an Opis invention: `input_timeout_ms`
  is the Timeout stability pattern. (Note this nuances the control-flow diff, which called
  windows Opis-original because the *workflow-patterns* literature is untimed — the
  *resilience* literature is not. Windows are original to workflow modeling, standard in
  resilience engineering. Worth stating precisely.)
- **Retry and Backpressure/buffering are deliberately below the flow layer** (synapse /
  gate internals / CA) — a boundary confirmation, not a gap.
- **Bulkhead isolation** (per-compartment resource partitioning) is the one kind-axis
  concept without a clean Opis primitive — a candidate refinement of `regulator`.
