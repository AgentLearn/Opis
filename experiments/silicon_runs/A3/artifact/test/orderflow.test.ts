import { test } from "node:test";
import assert from "node:assert/strict";

import type { Customer } from "../src/domain/types.ts";
import { CorporateMenu, FranchiseMenu } from "../src/menu/menu.ts";
import { SimulatedPaymentGateway } from "../src/payments/payments.ts";
import { goodMaps, openTraffic, RoutePlanner } from "../src/routing/mapping.ts";
import type { MappingService } from "../src/routing/mapping.ts";
import { LocationRouter } from "../src/routing/locationRouter.ts";
import { Shop, estimatePickupMinutes } from "../src/shops/shop.ts";
import { LoyaltyProgram } from "../src/loyalty/loyalty.ts";
import { DriverDispatcher } from "../src/delivery/dispatch.ts";
import type { TrackingEvent } from "../src/delivery/dispatch.ts";
import { OrderService } from "../src/orders/orderService.ts";
import type { CheckoutResult } from "../src/orders/orderService.ts";

type AcceptedCheckout = Extract<CheckoutResult, { accepted: true }>;

function expectAccepted(result: CheckoutResult): AcceptedCheckout {
  if (!result.accepted) assert.fail(`checkout rejected: ${result.reason}`);
  return result;
}

function makeSystem() {
  const corporate = new CorporateMenu([
    { id: "blt", name: "Classic BLT", priceCents: 899 },
    { id: "veggie", name: "Garden Veggie", priceCents: 799 },
  ]);
  const downtownMenu = new FranchiseMenu(corporate);
  const airportMenu = new FranchiseMenu(corporate);
  const downtown = new Shop("shop-downtown", "Downtown", { lat: 37.7749, lng: -122.4194 }, downtownMenu);
  const airport = new Shop("shop-airport", "Airport", { lat: 37.6213, lng: -122.379 }, airportMenu);
  const planner = new RoutePlanner([goodMaps, openTraffic]);
  const gateway = new SimulatedPaymentGateway();
  const loyalty = new LoyaltyProgram();
  const dispatcher = new DriverDispatcher([{ id: "drv-1", name: "Sam" }]);
  const orders = new OrderService(
    [downtown, airport],
    gateway,
    loyalty,
    new LocationRouter(planner),
    planner,
    dispatcher,
  );
  const customer: Customer = { id: "cust-1", name: "Ada", location: { lat: 37.79, lng: -122.41 } };
  return { corporate, downtownMenu, airportMenu, downtown, airport, gateway, loyalty, dispatcher, orders, customer };
}

test("declined payment: order is rejected and never reaches the kitchen", async () => {
  const { orders, gateway, downtown, customer } = makeSystem();
  gateway.declineNextChargeFor(customer.id);
  const result = await orders.checkout({
    customer,
    lines: [{ itemId: "blt", quantity: 1 }],
    fulfilment: "pickup",
    pickupShopId: downtown.id,
  });
  assert.equal(result.accepted, false);
  assert.equal(downtown.kitchen.length, 0);
});

test("confirmed payment: order is created, validated, and submitted to the kitchen", async () => {
  const { orders, downtown, customer } = makeSystem();
  const result = expectAccepted(
    await orders.checkout({
      customer,
      lines: [{ itemId: "blt", quantity: 2 }],
      fulfilment: "pickup",
      pickupShopId: downtown.id,
    }),
  );
  assert.equal(result.order.status, "submitted");
  assert.match(result.order.paymentTransactionId, /^tx-/);
  assert.equal(result.order.totalCents, 1798);
  assert.equal(downtown.kitchen.length, 1);
  assert.ok(downtown.kitchen.has(result.order.id));
});

test("pickup estimate grows with the queue at the chosen location", async () => {
  const { orders, downtown, customer } = makeSystem();
  const estimates: number[] = [];
  for (let i = 0; i < 3; i++) {
    const r = expectAccepted(
      await orders.checkout({
        customer,
        lines: [{ itemId: "veggie", quantity: 1 }],
        fulfilment: "pickup",
        pickupShopId: downtown.id,
      }),
    );
    estimates.push(r.pickupEstimateMinutes!);
  }
  assert.deepEqual(estimates, [estimatePickupMinutes(0), estimatePickupMinutes(1), estimatePickupMinutes(2)]);
  assert.ok(estimates[1] > estimates[0] && estimates[2] > estimates[1]);
});

test("route planner requires >= 2 mapping services and picks the fastest", async () => {
  assert.throws(() => new RoutePlanner([goodMaps]));
  const planner = new RoutePlanner([goodMaps, openTraffic]);
  const from = { lat: 37.7749, lng: -122.4194 };
  const to = { lat: 37.79, lng: -122.41 };
  const [a, b, best] = await Promise.all([
    goodMaps.route(from, to),
    openTraffic.route(from, to),
    planner.bestRoute(from, to),
  ]);
  assert.equal(best.minutes, Math.min(a.minutes, b.minutes));
});

test("route planner survives one provider outage", async () => {
  const broken: MappingService = {
    name: "Broken",
    route: async () => {
      throw new Error("provider down");
    },
  };
  const planner = new RoutePlanner([broken, openTraffic]);
  const route = await planner.bestRoute({ lat: 37.77, lng: -122.42 }, { lat: 37.79, lng: -122.41 });
  assert.equal(route.provider, "OpenTraffic");
});

test("delivery orders are routed to the shop with the shortest drive time", async () => {
  const { orders, airport } = makeSystem();
  const nearAirport: Customer = { id: "cust-2", name: "Grace", location: { lat: 37.63, lng: -122.39 } };
  const result = expectAccepted(
    await orders.checkout({
      customer: nearAirport,
      lines: [{ itemId: "blt", quantity: 1 }],
      fulfilment: "delivery",
    }),
  );
  assert.equal(result.shop.id, airport.id);
  assert.equal(airport.kitchen.length, 1);
});

test("delivery dispatches a driver and streams tracking events; pickup does not", async () => {
  const { orders, downtown, dispatcher, customer } = makeSystem();
  const delivery = expectAccepted(
    await orders.checkout({
      customer,
      lines: [{ itemId: "blt", quantity: 1 }],
      fulfilment: "delivery",
    }),
  );
  assert.ok(delivery.delivery);
  const events: TrackingEvent[] = [];
  const { tracking } = delivery.delivery;
  tracking.onUpdate((e) => events.push(e));
  tracking.start();
  while (!tracking.delivered) tracking.advance();
  assert.equal(events[0].type, "dispatched");
  assert.ok(events.some((e) => e.type === "position"));
  assert.equal(events.at(-1)!.type, "delivered");
  assert.equal(delivery.order.status, "delivered");

  const pickup = expectAccepted(
    await orders.checkout({
      customer,
      lines: [{ itemId: "blt", quantity: 1 }],
      fulfilment: "pickup",
      pickupShopId: downtown.id,
    }),
  );
  assert.equal(pickup.delivery, undefined);
  assert.equal(dispatcher.trackingFor(pickup.order.id), undefined);
});

test("franchise menu overrides are independent per shop", async () => {
  const { downtownMenu, airportMenu } = makeSystem();
  airportMenu.setPrice("blt", 1099);
  airportMenu.addLocalItem({ id: "redeye", name: "Red-Eye Sub", priceCents: 1199 });
  downtownMenu.removeItem("veggie");

  assert.equal(airportMenu.get("blt")!.priceCents, 1099);
  assert.equal(downtownMenu.get("blt")!.priceCents, 899); // untouched by airport's change
  assert.equal(airportMenu.get("redeye")!.name, "Red-Eye Sub");
  assert.equal(downtownMenu.get("redeye"), undefined);
  assert.equal(downtownMenu.get("veggie"), undefined);
  assert.equal(airportMenu.get("veggie")!.priceCents, 799);
});

test("items missing from a franchise menu reject the order before payment", async () => {
  const { orders, downtownMenu, downtown, customer } = makeSystem();
  downtownMenu.removeItem("veggie");
  const result = await orders.checkout({
    customer,
    lines: [{ itemId: "veggie", quantity: 1 }],
    fulfilment: "pickup",
    pickupShopId: downtown.id,
  });
  assert.equal(result.accepted, false);
  assert.equal(downtown.kitchen.length, 0);
});

test("loyalty: points accrue on paid total and redeem as checkout discounts", async () => {
  const { orders, loyalty, downtown, customer } = makeSystem();
  const first = expectAccepted(
    await orders.checkout({
      customer,
      lines: [{ itemId: "blt", quantity: 2 }], // $17.98 → 17 pts
      fulfilment: "pickup",
      pickupShopId: downtown.id,
    }),
  );
  assert.equal(first.loyalty.pointsEarned, 17);
  assert.equal(loyalty.pointsOf(customer.id), 17);

  loyalty.earn(customer.id, 20000); // top up from order history: +200 pts
  const second = expectAccepted(
    await orders.checkout({
      customer,
      lines: [{ itemId: "blt", quantity: 2 }],
      fulfilment: "pickup",
      pickupShopId: downtown.id,
      redeemPoints: 200,
    }),
  );
  assert.equal(second.loyalty.pointsUsed, 200);
  assert.equal(second.loyalty.discountCents, 1000);
  assert.equal(second.order.totalCents, 798); // 1798 − 1000
  assert.equal(second.loyalty.pointsEarned, 7);
});

test("loyalty points are refunded when payment is declined", async () => {
  const { orders, loyalty, gateway, downtown, customer } = makeSystem();
  loyalty.earn(customer.id, 10000); // 100 pts
  gateway.declineNextChargeFor(customer.id);
  const result = await orders.checkout({
    customer,
    lines: [{ itemId: "blt", quantity: 2 }],
    fulfilment: "pickup",
    pickupShopId: downtown.id,
    redeemPoints: 100,
  });
  assert.equal(result.accepted, false);
  assert.equal(loyalty.pointsOf(customer.id), 100);
});
