---
id: coincidence-drop
name: Coincidence Drop
threshold_fire_pct: 80.0
---

## Detection
A gate requires pulses from 2 or more independent upstream producers. Because each producer
fires at a random time within its own window_ms, the probability that all required pulses
arrive within the downstream gate's coincidence window drops multiplicatively with each
additional independent path. At 2 independent paths with uniform[0, 5000ms] service times,
expected coincidence is already well below 50%.

## Signal
Twin fire% < 80% on a gate that has multiple requires entries sourced from different
upstream gates (not the same producer chain).

## Remedy
Insert a sync gate upstream of the affected gate. The sync gate:
- Archetype: TransactionCoordination
- Collects all the scattered upstream pulses as inputs
- Emits a single coordinated pulse once all have arrived (commit semantics)
- The downstream gate replaces its multiple requires with that single pulse

The sync gate serialises the fan-in and guarantees the downstream gate sees 100%
coincidence on its single required input.

## FA instruction
When this pattern fires on gate G with requires [A, B, ...] from producers [X, Y, ...]:
1. Create a new gate named `<G>-sync` with archetype TransactionCoordination
2. Its inputs: [A, B, ...] (the scattered pulses)
3. Its output: `<g>_coordinated` (snake_case of G name + _coordinated)
4. Replace G's requires with [`<g>_coordinated`]
5. Update graph.json connections accordingly
6. Delete G's cached spec so GA regenerates with the new single input
