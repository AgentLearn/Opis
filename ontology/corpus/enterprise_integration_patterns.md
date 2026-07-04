# Seed corpus: Enterprise Integration Patterns (gate TEMPLATE axis)

Source (authoritative): Gregor Hohpe & Bobby Woolf, "Enterprise Integration Patterns:
Designing, Building, and Deploying Messaging Solutions", Addison-Wesley, 2003. ISBN 0321200683.
Catalog (65 patterns): https://www.enterpriseintegrationpatterns.com/patterns/messaging/
Pattern names, icons, problem/solution statements are CC-BY licensed.

Role in the SA taxonomy: the **template axis**. Opis gate templates (order_validator,
delivery_router, payment_processor, ...) are messaging patterns with a contract attached.
EIP gives the established vocabulary of *what a gate does to messages* — route, filter,
aggregate, split, enrich, translate — independent of domain.

Scope: the 65 EIP patterns span 6 groups. For gate templates the relevant groups are
**Routing** and **Transformation** (the gate's processing behaviour) and parts of
**Endpoint** and **Channel** (delivery/consumption semantics). Message-construction
patterns (Command/Event/Document Message) map to the Opis SLOT-TYPE / term axis, not the
template axis — noted where they cross over.

Each entry: name | EIP group | template semantics | Opis gate-template relevance.

---

## Routing Patterns (specializations of Message Router)
The core of the template axis: how a gate directs messages to receivers.

- **Message Router** — consumes a message and republishes it to a different channel based
  on conditions; the base routing pattern. Opis: any gate whose outcome selects a
  downstream synapse. The genus of `delivery_router`, `driver_dispatcher`.

- **Content-Based Router** — routes based on the *content* of the message (field values,
  presence). Opis: a routing gate whose outcome depends on payload/type — the canonical
  `delivery_router` / `routed_command_dispatcher` template.

- **Message Filter** — passes a message through only if it meets criteria; otherwise
  discards it. A router with one output and a drop. Opis: a validation/guard gate that
  emits accepted vs. drops (relates to `order_validator`'s reject path; note Opis
  discourages silent drops — terminal flows end at loci, ADR-011 rejected a sink gate).

- **Dynamic Router** — a router whose routing rules can change at runtime via a control
  channel. Opis: no direct template; routing is static in a flow. Candidate gap.

- **Recipient List** — routes one message to a computed *set* of destinations (static or
  dynamic list). Opis: fan-out to multiple synapses; `delivery_router` broadcasting.

- **Splitter** — breaks one composite message into multiple messages, each processed
  separately. Opis: a gate emitting multiple pulses from one input (relates to
  workflow Thread Split / fan-out).

- **Aggregator** — collects and combines related messages into one, using a completeness
  condition and a correlation. Opis: a **join gate** — this is the template realization of
  `logic: AND` / `logic: THRESHOLD` (the aggregator's completeness condition IS the join
  logic). `routing_decision_aggregator` is exactly this.

- **Resequencer** — reorders out-of-order messages into a specified sequence using a
  buffer. Opis: no template today; relates to ordering guarantees (candidate gap,
  probably CA/body layer).

- **Composed Message Processor** — splits, routes to processors, then re-aggregates.
  Opis: a sub-flow / gate internals (GA composition) — Splitter+Router+Aggregator.

- **Scatter-Gather** — broadcasts a request to multiple recipients and aggregates their
  replies. Opis: fan-out + join; `routing_decision_multi_provider_aggregator` is this
  pattern (query to N providers, THRESHOLD/AND join on responses).

- **Routing Slip** — attaches a sequence of processing steps to a message, each station
  routing to the next. Opis: an itinerary encoded in the pulse (candidate — closest to a
  flow path made data).

- **Process Manager** — a central component maintains state and determines the next step
  (stateful orchestration). Opis: relates to a stateful regulator / the flow itself as
  orchestrator; not a single gate template.

- **Message Broker** — a central hub decoupling senders from receivers, routing to the
  correct destination. Opis: the flow substrate (loci + synapses), not a gate template.

## Transformation Patterns (specializations of Message Translator)
Gates that change message content.

- **Message Translator** — converts a message from one format to another. Opis: the CA
  schema-translation layer (per-archetype message schemas) more than a gate template;
  crosses into CA's job.

- **Content Enricher** — augments a message with data from an external source it queries.
  Opis: `provider_query_resolver` / any gate that pulls query_response to enrich — a
  genuine template (enrich-from-source). Matches the pull-idiom providers.

- **Content Filter** — removes/simplifies fields from a message, keeping a subset. Opis:
  a projection gate; `order_validator` when it strips to accepted_order.

- **Claim Check** — stores message content externally and passes a reference (token),
  re-retrieving later. Opis: relates to the CA body-provider (bodies travel by reference;
  HMAC tokens). Template-relevant to sentinel/token handling.

- **Normalizer** — translates messages arriving in different formats into a common one.
  Opis: CA canonical schema layer.

- **Envelope Wrapper / Canonical Data Model** — wrap payloads for transport / define a
  shared format. Opis: the pulse envelope + slot-type taxonomy (term axis), not template.

## Endpoint Patterns (delivery/consumption semantics — partial template relevance)

- **Content Enricher's source**, **Polling Consumer** vs **Event-driven Consumer** —
  pull vs push consumption. Opis: distinguishes provider (pull, query/query_response) from
  event-driven gates. Maps to the pull-idiom vs event handling distinction FA already hit.

- **Competing Consumers / Message Dispatcher** — multiple consumers share a channel to
  scale throughput. Opis: relates to fan-out to worker loci / driver pool; twin
  concurrency, not a gate template per se.

- **Selective Consumer** — consumer filters which messages it accepts by criteria. Opis:
  a gate's input type-matching / archetype resolution (already core to gate selection).

- **Idempotent Receiver** — handles duplicate messages safely. Opis: relates to
  `repeat_event_throttle` / dedup; crosses into the kind axis (throttle).

- **Durable Subscriber** — retains messages for a subscriber that is temporarily offline.
  Opis: the Persistent Trigger analog (buffered input) — same gap flagged in the
  control-flow corpus (WCP24).

- **Service Activator** — connects a service to the messaging system so it can be invoked
  by messages. Opis: the CA gate-implementation adapter (subprocess over stdio).

## Channel & System-Management Patterns (mostly substrate / kind-axis crossover)

- **Dead Letter Channel** — where the messaging system routes messages it cannot deliver.
  Opis: relates to breaker/failure outcomes and rejected paths.
- **Invalid Message Channel** — for messages a receiver cannot process. Opis: reject
  outcome routing.
- **Guaranteed Delivery** — persist messages so they survive failure. Opis: reliability
  property, twin/CA concern.
- **Wire Tap** — inspect messages on a channel without disturbing flow. Opis: the
  `event_recorder` / observability template.
- **Control Bus** — separate channel for management/monitoring. Opis: relates to sentinel
  control signals.
- **Detour** — route through intermediate steps for validation/testing under control.
  Opis: relates to regulator-inserted checks.

---

## Cross-reference: EIP -> Opis gate template (curator's mapping, to be tested by induction)

| EIP pattern | Opis gate template / construct |
|-------------|-------------------------------|
| Content-Based Router | delivery_router / routed_command_dispatcher (routing template) |
| Recipient List | fan-out router |
| Aggregator | join gate = realization of AND/THRESHOLD logic |
| Scatter-Gather | multi-provider aggregator (fan-out + join) |
| Content Enricher | provider_query_resolver (enrich-from-source) |
| Content Filter | order_validator projection / accepted_order |
| Message Filter | guard/validation gate |
| Splitter | fan-out emitter |
| Wire Tap | event_recorder (observability) |
| Claim Check | CA body-provider / token reference |
| Selective Consumer | gate input archetype resolution |
| Polling vs Event-driven Consumer | provider (pull) vs event-driven gate |

## Template-axis observations (candidate findings, to confirm by induction)
- The **Aggregator** is the missing link: Opis gate `logic` (AND/THRESHOLD) is the
  *abstract* join; the Aggregator is its *template* form (completeness condition +
  correlation). This unifies the logic axis and the template axis at one point.
- **Dynamic Router, Resequencer, Durable Subscriber** are EIP templates with no Opis
  counterpart — same family of "runtime-dynamic / ordering / buffering" gaps the
  control-flow corpus surfaced. Consistent signal across both axes.
- Several EIP patterns (Translator, Normalizer, Canonical Data Model, Envelope Wrapper)
  belong to the **CA schema layer**, not the gate-template axis — a clean boundary
  confirmation, matching the standing "payload content = CA layer" rule.
