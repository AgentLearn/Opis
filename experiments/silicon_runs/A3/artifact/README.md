# Silicon Sandwiches — Order Flow

A working implementation of the Silicon Sandwiches order flow: a franchise sandwich chain
where customers order via mobile app or kiosk. Zero runtime dependencies — TypeScript
running natively on Node ≥ 24 (type stripping).

## Run it

```sh
npm test        # 11 tests covering every requirement (node:test)
npm run demo    # end-to-end scenario: declined payment, pickup, delivery, loyalty
npm run typecheck
```

## How the requirements map to the code

| Requirement | Where |
|---|---|
| Payment confirmed before kitchen | `OrderService.checkout` charges first; on decline it returns before any kitchen call ([orderService.ts](src/orders/orderService.ts)) |
| Coordinate create → validate → submit after payment | Steps 4 in `OrderService.checkout` (facade over the flow) |
| Pickup time from queue length | `KitchenQueue.length` + `estimatePickupMinutes` ([shop.ts](src/shops/shop.ts)) |
| ≥ 2 traffic-aware mapping services | `MappingService` adapters `GoodMaps` / `OpenTraffic`; `RoutePlanner` queries all in parallel, picks fastest, tolerates one outage, and refuses to be built with < 2 providers ([mapping.ts](src/routing/mapping.ts)) |
| Orders routed to the correct shop | `LocationRouter` picks the shop with the shortest traffic-aware drive time ([locationRouter.ts](src/routing/locationRouter.ts)) |
| Driver dispatched + tracked in real time (delivery only) | `DriverDispatcher` assigns a driver; `DeliveryTracking` streams `dispatched` / `position` / `delivered` events to observers ([dispatch.ts](src/delivery/dispatch.ts)) |
| Franchise owners update menu/pricing independently | `FranchiseMenu` layers per-shop price overrides, local items, and removals over the shared `CorporateMenu` ([menu.ts](src/menu/menu.ts)) |
| Loyalty points + rewards at checkout | `LoyaltyProgram`: 1 pt/$ earned on paid total; 100-pt blocks redeem as $5 discounts; points refunded if payment declines ([loyalty.ts](src/loyalty/loyalty.ts)) |

## Checkout flow

```
checkout(request)
  ├─ pick shop        pickup → customer's chosen shop
  │                   delivery → LocationRouter (fastest drive time across shops)
  ├─ price cart       against that franchise's menu (overrides applied)
  ├─ redeem loyalty   requested points → discount, capped by balance & subtotal
  ├─ charge payment   ── declined? refund points, reject. NOTHING reaches the kitchen
  ├─ coordinate       create order → validate → submit to shop's kitchen queue
  ├─ earn points      on the amount actually paid
  └─ fulfil           pickup → ETA from queue depth ahead of this order
                      delivery → best of 2 mapping providers, dispatch driver,
                                 live tracking events
```

## Design notes

- **`MappingService`** is an adapter interface; the two bundled providers simulate
  traffic-aware ETAs deterministically. A real integration (Google Maps, TomTom, …)
  is one class implementing `route(from, to)`.
- **`SimulatedPaymentGateway`** stands in for a real processor behind the
  `PaymentGateway` interface; declines can be forced per customer for testing.
- **`DeliveryTracking.advance()`** steps the driver along the route so tests and the
  demo are deterministic; in production those events would come from driver-app GPS pings.
- Money is integer cents throughout; ids are human-readable and monotonic.
