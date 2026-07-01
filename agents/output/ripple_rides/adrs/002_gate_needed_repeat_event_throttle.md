# ADR-002: gate needed: repeat_event_throttle

## Context
The flow requires a gate that accumulates repeated events from a given actor within a rolling window and, when a threshold is exceeded, emits a suspension or cooldown command. This covers both repeated driver non-acceptance (driver suspension) and repeated rider late cancellations (rider cooldown). No existing gate tracks event frequency per actor and conditionally emits a command — driver_dispatcher emits events but does not count or threshold them.

## Options

### Option A
Add repeat_event_throttle gate: inputs event (repeated), outputs command (suspend/cooldown) when threshold exceeded within window_ms, otherwise emits ack. Stateful counter per actor identity in the gate.

**Tradeoffs:** Directly models the requirement; reusable for both driver and rider penalty patterns. Requires stateful gate implementation with actor-keyed counters.

### Option B
Model suspension as a side-effect of driver_dispatcher by adding a 'threshold_exceeded' outcome that emits a command. Rider cooldown handled by a separate dedicated gate.

**Tradeoffs:** Avoids a new gate for driver suspension but mixes dispatch and penalty logic. Rider cooldown still requires a new gate anyway.

## Decision

A
