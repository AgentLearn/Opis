# Silicon Sandwiches — Order Flow

A self-contained TypeScript model of the Silicon Sandwiches franchise order flow: payment-gated kitchen submission, queue-based pickup estimates, multi-provider traffic-aware delivery routing, live driver tracking, per-franchise menu management, and loyalty rewards.

Zero runtime dependencies — Node ≥ 23.6 runs the TypeScript sources directly (type stripping).

## Run it

```sh
npm run demo      # end-to-end scenario: menus, pickup, declined payment, tracked delivery
npm test          # 16 tests via node:test
npm run typecheck # tsc --noEmit (needs `npm install` first for typescript + @types/node)
```

## Requirements → implementation

| Requirement | Where | How |
|---|---|---|
| Payment confirmed before kitchen | `src/orders/orderOrchestrator.ts`, `src/kitchen/kitchenService.ts` | `checkout()` charges the `PaymentGateway` before an `Order` exists; `KitchenService.submitOrder` independently rejects any order without a confirmed `paymentId` (defense in depth). |
| Coordinate creation → validation → submission | `src/orders/orderOrchestrator.ts` | `OrderOrchestrator` is a facade sequencing routing, basket validation, loyalty, payment, order creation, and kitchen submission. |
| Pickup estimate from queue length | `src/kitchen/kitchenService.ts` | `estimateReadyAt` = current queue length × avg minutes per order + prep time per item. |
| ≥ 2 traffic-aware mapping services | `src/routing/providers/` | `SpeedyMapsClient` and `AtlasRoutingClient` both implement the `MappingService` adapter interface; each applies an injectable `TrafficSource` congestion multiplier. |
| Route order to the correct shop | `src/routing/routePlanner.ts` | `RoutePlanner` (requires ≥ 2 providers, tolerates provider outages) picks the shop with the fastest current route to the delivery address; pickup orders go to the customer-chosen shop. |
| Driver dispatched & tracked live (delivery only) | `src/dispatch/driverService.ts` | `DriverService.dispatch` assigns a driver when the kitchen marks a delivery order ready; `DeliveryTracking` (EventEmitter) streams `position` updates along the route and `delivered` on arrival. Pickup orders never dispatch. |
| Owners manage their own menus | `src/franchise/menuService.ts` | Menus are stored per location; every mutation checks the caller's `ownerId` against the location's owner. |
| Loyalty points & rewards at checkout | `src/loyalty/loyaltyService.ts` | 1 point per $1 paid; points redeem at 5¢ each as a checkout discount, refunded automatically if the payment is declined. |

## Layout

```
src/
  domain/types.ts             shared domain model (Order, MenuItem, ShopLocation, ...)
  payments/paymentGateway.ts  PaymentGateway interface + mock card processor
  franchise/                  location directory + owner-scoped menu service
  loyalty/loyaltyService.ts   point balances, earn/redeem/refund
  routing/                    MappingService adapters, geo math, RoutePlanner
  kitchen/kitchenService.ts   per-location prep queues + pickup estimates
  dispatch/driverService.ts   driver assignment + real-time tracking simulation
  orders/orderOrchestrator.ts checkout facade tying it all together
  demo.ts                     runnable end-to-end scenario
test/                         node:test suites (order flow, routing, franchise)
```

## Notes on the model

- All state is in-memory; payment and mapping providers are mocks behind the same interfaces a real integration would use (swap in a Stripe or Google Maps adapter without touching the orchestrator).
- Money is integer cents throughout.
- Checkout order matters: loyalty points are redeemed before the charge and refunded on decline, so a failed payment leaves no side effects — no order, no kitchen ticket, no lost points.
