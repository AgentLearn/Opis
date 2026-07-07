# Silicon Sandwiches — Order Flow

A typed, dependency-free TypeScript implementation of the Silicon Sandwiches
order flow. Runs directly on Node ≥ 23.6 (native type stripping) — no build
step, no `npm install` needed to run the demo or tests.

```
npm run demo        # end-to-end walkthrough (pickup, declined card, tracked delivery)
npm test            # node --test src/
npm run typecheck   # requires `npm install` once (typescript devDependency)
```

## Architecture

```
                 CheckoutOrchestrator (src/checkout.ts)
                          │
   1. route to shop ──────┼────────────► ShopRouter ──► RoutePlanner
   2. price cart          │              (pickup: chosen shop;      │
   3. apply loyalty       │               delivery: fastest ETA)    ▼
   4. charge payment ─────┼──► PaymentGateway            MappingProvider ×2
   5. create + validate   │    (hard gate)               (GoogleMapsAdapter,
   6. submit to kitchen ──┼──► KitchenService             OsrmAdapter —
   7. earn points ────────┼──► LoyaltyService             traffic-aware)
   8. dispatch driver ────┴──► DriverDispatcher ──► DeliveryTracking
      (delivery only)                               (live subscribe/tick)
```

## Requirement → code map

| Requirement | Where |
|---|---|
| Payment confirmed before kitchen | `CheckoutOrchestrator.placeOrder` charges first and throws `PaymentDeclinedError`; `KitchenService.submit` independently rejects unpaid orders |
| Post-payment coordination (create → validate → submit) | `src/checkout.ts` |
| Pickup ETA from queue length | `KitchenService.estimatePickupMinutes` (base prep + per-queued-order) |
| ≥ 2 traffic-aware mapping services | `src/services/mapping.ts` — two adapters behind `MappingProvider`, injected `TrafficFeed`; `RoutePlanner` races them and tolerates provider failures |
| Orders routed to the correct shop | `ShopRouter` — customer's shop for pickup; fastest traffic-aware ETA among shops that stock every item for delivery |
| Driver dispatch + real-time tracking (delivery only) | `DriverDispatcher` picks nearest free driver; `DeliveryTracking.subscribe`/`tick` streams position, progress, ETA |
| Franchise owners edit own menu/pricing | `MenuService` — per-shop menu copies; every mutation authorized against `shop.ownerId` |
| Loyalty points + rewards at checkout | `LoyaltyService` — 1 pt/$ earned on payment; 100 pts = $5 off, refunded if payment declines |

## Layout

```
src/
  domain/        types, per-shop menus, loyalty
  services/      payment, mapping adapters, shop routing, kitchen, dispatch
  checkout.ts    the orchestrator
  fixtures.ts    wired-up sample system (shared by demo and tests)
  demo.ts        runnable scenario
  *.test.ts      node:test suites next to what they test
```

External integrations (payments, mapping) are simulated behind interfaces
(`PaymentGateway`, `MappingProvider`) — swapping in real HTTP adapters
doesn't touch the orchestrator.
