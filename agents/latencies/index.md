# Latency library

Real-life latency expectations feeding the opis-twin Monte Carlo simulator
(GA_PLAN Phases 3–4). Machine-readable source of truth: `latencies.json`.

Three sections:

- **media** — per-synapse traversal latency by `medium` (local / lan / internet).
  Sampled once per pulse crossing a synapse.
- **operations** — per-gate service latency keyed by `gate_template`. Sampled
  once per gate firing. Gates whose template has no entry fall back to a
  window-derived distribution (p50 = 20% of window_ms, p95 = 60%), tagged as
  fallback in the twin report.
- **norms** — advisory end-to-end expectations keyed by *base slot type* of a
  requirement target's outcome (subtype-aware: `ride_payment_confirmed` is-a
  `payment_confirmed` matches the `payment_confirmed` norm). `twin_check.py`
  flags requirement paths whose simulated p95 exceeds the norm — a flag for the
  architect, never a hard failure. Per Zarko's decision (2026-07-01): timing
  targets do NOT live in katas; norms are rough real-life expectations, and
  their value is surfacing outliers, not enforcing SLAs.

All distributions are lognormal, parameterized by `p50_ms`/`p95_ms`
(μ = ln p50, σ = (ln p95 − ln p50)/1.645).

## Confidence tiers

- `sourced` — cites a published benchmark (URL in the entry). Currently:
  `media.internet` (Ookla H2 2025 mobile RTT; LTE/5G field measurements) and
  `operations.payment_processor` (Adyen's published <500 ms p95 authorization).
- `llm-estimate` — model-proposed, explicitly unverified. Replace with
  measured values when CA instruments real gate implementations (the twin then
  switches from simulation to instrumentation, per OpisDescription).

Never mix the tiers silently: anything derived from an `llm-estimate` entry
inherits that caveat.
