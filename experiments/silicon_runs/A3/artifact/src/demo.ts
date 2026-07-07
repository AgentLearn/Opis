import type { Customer } from "./domain/types.ts";
import { CorporateMenu, FranchiseMenu } from "./menu/menu.ts";
import { SimulatedPaymentGateway } from "./payments/payments.ts";
import { goodMaps, openTraffic, RoutePlanner } from "./routing/mapping.ts";
import { LocationRouter } from "./routing/locationRouter.ts";
import { Shop } from "./shops/shop.ts";
import { LoyaltyProgram } from "./loyalty/loyalty.ts";
import { DriverDispatcher } from "./delivery/dispatch.ts";
import { OrderService } from "./orders/orderService.ts";

const dollars = (cents: number) => `$${(cents / 100).toFixed(2)}`;

// --- Wiring -----------------------------------------------------------------
const corporate = new CorporateMenu([
  { id: "blt", name: "Classic BLT", priceCents: 899 },
  { id: "veggie", name: "Garden Veggie", priceCents: 799 },
  { id: "italian", name: "Spicy Italian", priceCents: 999 },
]);

const downtownMenu = new FranchiseMenu(corporate);
const airportMenu = new FranchiseMenu(corporate);
// The airport franchisee charges more and runs a local special — downtown is unaffected.
airportMenu.setPrice("blt", 1099);
airportMenu.addLocalItem({ id: "redeye", name: "Red-Eye Breakfast Sub", priceCents: 1199 });

const downtown = new Shop("shop-downtown", "Downtown", { lat: 37.7749, lng: -122.4194 }, downtownMenu);
const airport = new Shop("shop-airport", "Airport", { lat: 37.6213, lng: -122.379 }, airportMenu);
const shops = [downtown, airport];

const planner = new RoutePlanner([goodMaps, openTraffic]);
const gateway = new SimulatedPaymentGateway();
const loyalty = new LoyaltyProgram();
const dispatcher = new DriverDispatcher([
  { id: "drv-1", name: "Sam" },
  { id: "drv-2", name: "Riley" },
]);
const orders = new OrderService(shops, gateway, loyalty, new LocationRouter(planner), planner, dispatcher);

const ada: Customer = { id: "cust-ada", name: "Ada", location: { lat: 37.79, lng: -122.41 } };
const grace: Customer = { id: "cust-grace", name: "Grace", location: { lat: 37.64, lng: -122.4 } };

// --- Scenarios ----------------------------------------------------------------
console.log("=== Franchise menus (independent overrides) ===");
console.log(`Downtown BLT: ${dollars(downtownMenu.get("blt")!.priceCents)}   Airport BLT: ${dollars(airportMenu.get("blt")!.priceCents)}`);
console.log(`Airport local special: ${airportMenu.get("redeye")!.name} ${dollars(airportMenu.get("redeye")!.priceCents)}\n`);

console.log("=== 1. Declined payment never reaches the kitchen ===");
gateway.declineNextChargeFor(ada.id);
const declined = await orders.checkout({
  customer: ada,
  lines: [{ itemId: "blt", quantity: 1 }],
  fulfilment: "pickup",
  pickupShopId: downtown.id,
});
console.log(`Result: ${declined.accepted ? "accepted" : `rejected — ${declined.reason}`}`);
console.log(`Downtown kitchen queue: ${downtown.kitchen.length}\n`);

console.log("=== 2. Pickup order with queue-based estimate ===");
// Two orders already cooking ahead of Ada.
for (let i = 0; i < 2; i++) {
  await orders.checkout({
    customer: grace,
    lines: [{ itemId: "veggie", quantity: 1 }],
    fulfilment: "pickup",
    pickupShopId: downtown.id,
  });
}
const pickup = await orders.checkout({
  customer: ada,
  lines: [{ itemId: "blt", quantity: 2 }],
  fulfilment: "pickup",
  pickupShopId: downtown.id,
});
if (pickup.accepted) {
  console.log(`Order ${pickup.order.id} @ ${pickup.shop.name}: ${dollars(pickup.order.totalCents)} paid (${pickup.order.paymentTransactionId})`);
  console.log(`Queue ahead: 2 → pickup ready in ~${pickup.pickupEstimateMinutes} min`);
  console.log(`Loyalty: earned ${pickup.loyalty.pointsEarned} pts (balance ${pickup.loyalty.balance})\n`);
}

console.log("=== 3. Delivery: routed to nearest shop, driver tracked live ===");
const delivery = await orders.checkout({
  customer: grace, // Grace lives near the airport
  lines: [{ itemId: "italian", quantity: 1 }, { itemId: "redeye", quantity: 1 }],
  fulfilment: "delivery",
});
if (delivery.accepted && delivery.delivery) {
  const { route, tracking } = delivery.delivery;
  console.log(`Routed to: ${delivery.shop.name} (fastest of 2 mapping providers: ${route.provider}, ${route.minutes} min, ${route.distanceKm} km)`);
  tracking.onUpdate((e) => {
    if (e.type === "dispatched") console.log(`Driver ${e.driver.name} dispatched, ETA ${e.etaMinutes} min`);
    if (e.type === "position") console.log(`  [track] ${e.step} — ${e.remainingMinutes} min remaining`);
    if (e.type === "delivered") console.log(`Delivered! Order ${e.orderId} complete.`);
  });
  tracking.start();
  while (!tracking.delivered) tracking.advance();
  console.log();
}

console.log("=== 4. Loyalty redemption at checkout ===");
loyalty.earn(grace.id, 25000); // long-time customer: points from past orders
console.log(`Grace's balance: ${loyalty.pointsOf(grace.id)} pts`);
const redeemed = await orders.checkout({
  customer: grace,
  lines: [{ itemId: "italian", quantity: 3 }],
  fulfilment: "pickup",
  pickupShopId: downtown.id,
  redeemPoints: 200,
});
if (redeemed.accepted) {
  console.log(
    `Subtotal ${dollars(redeemed.order.subtotalCents)} − ${redeemed.loyalty.pointsUsed} pts (${dollars(redeemed.loyalty.discountCents)}) = charged ${dollars(redeemed.order.totalCents)}`,
  );
  console.log(`New balance: ${redeemed.loyalty.balance} pts`);
}
