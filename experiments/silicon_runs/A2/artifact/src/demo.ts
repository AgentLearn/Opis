import { DriverService, type PositionUpdate } from './dispatch/driverService.ts';
import { FranchiseDirectory } from './franchise/franchiseDirectory.ts';
import { MenuService } from './franchise/menuService.ts';
import { KitchenService } from './kitchen/kitchenService.ts';
import { LoyaltyService } from './loyalty/loyaltyService.ts';
import { OrderOrchestrator, PaymentDeclinedError } from './orders/orderOrchestrator.ts';
import { MockCardGateway } from './payments/paymentGateway.ts';
import { AtlasRoutingClient } from './routing/providers/atlasRouting.ts';
import { SpeedyMapsClient } from './routing/providers/speedyMaps.ts';
import { RoutePlanner } from './routing/routePlanner.ts';

const usd = (cents: number) => `$${(cents / 100).toFixed(2)}`;
const mins = (n: number) => `${n.toFixed(1)} min`;

// --- Wire up the system -----------------------------------------------------

const directory = new FranchiseDirectory();
const menus = new MenuService(directory);
const payments = new MockCardGateway();
const loyalty = new LoyaltyService();
const kitchen = new KitchenService();
const planner = new RoutePlanner([new SpeedyMapsClient(), new AtlasRoutingClient()]);
const drivers = new DriverService([{ id: 'drv-1', name: 'Riya' }], 150);
const orchestrator = new OrderOrchestrator(directory, menus, payments, loyalty, kitchen, planner, drivers);

// Two franchises, two owners.
directory.register({ id: 'downtown', name: 'Downtown SF', ownerId: 'owner-ana', coordinates: { lat: 37.7897, lng: -122.4011 } });
directory.register({ id: 'mission', name: 'Mission District', ownerId: 'owner-bo', coordinates: { lat: 37.7599, lng: -122.4148 } });

for (const locationId of ['downtown', 'mission'] as const) {
  const ownerId = directory.get(locationId).ownerId;
  menus.upsertItem(ownerId, locationId, { id: 'blt', name: 'Bacon-Lettuce-Transistor', priceCents: 1195, available: true });
  menus.upsertItem(ownerId, locationId, { id: 'cap', name: 'Capacitor Club', priceCents: 1350, available: true });
  menus.upsertItem(ownerId, locationId, { id: 'soda', name: 'Fizzy Logic Soda', priceCents: 295, available: true });
}

// --- 1. Franchise owners manage their own menus -----------------------------

console.log('=== Franchise menu management ===');
menus.setPrice('owner-bo', 'mission', 'blt', 1095);
console.log(`owner-bo set Mission BLT price to ${usd(menus.getItem('mission', 'blt')!.priceCents)} (Downtown still ${usd(menus.getItem('downtown', 'blt')!.priceCents)})`);
try {
  menus.setPrice('owner-bo', 'downtown', 'blt', 100);
} catch (err) {
  console.log(`owner-bo touching Downtown menu -> rejected: ${(err as Error).message}`);
}

// --- 2. Pickup order with loyalty redemption --------------------------------

console.log('\n=== Pickup order (with loyalty) ===');
const carol = { id: 'cust-carol', name: 'Carol' };
loyalty.refund(carol.id, 120); // pretend Carol earned 120 points historically

const pickup = await orchestrator.checkout({
  customerId: carol.id,
  fulfillment: 'pickup',
  locationId: 'downtown',
  items: [
    { menuItemId: 'cap', quantity: 1 },
    { menuItemId: 'soda', quantity: 2 },
  ],
  redeemPoints: 100,
});
console.log(`Order ${pickup.order.id.slice(0, 12)}… at ${pickup.location.name}`);
console.log(`Subtotal ${usd(pickup.order.subtotalCents)} - loyalty ${usd(pickup.order.loyaltyDiscountCents)} = ${usd(pickup.order.totalCents)} (earned ${pickup.pointsEarned} pts, balance now ${loyalty.balance(carol.id)})`);
console.log(`Kitchen queue at pickup time: ${kitchen.queueLength('downtown') - 1} ahead -> estimated ready ${pickup.estimatedReadyAt.toLocaleTimeString()}`);

// --- 3. Declined payment never reaches the kitchen --------------------------

console.log('\n=== Declined payment ===');
payments.declineNextChargeFor('cust-mallory');
const queueBefore = kitchen.queueLength('downtown');
try {
  await orchestrator.checkout({
    customerId: 'cust-mallory',
    fulfillment: 'pickup',
    locationId: 'downtown',
    items: [{ menuItemId: 'blt', quantity: 1 }],
  });
} catch (err) {
  if (!(err instanceof PaymentDeclinedError)) throw err;
  console.log(`${err.message} -> kitchen queue unchanged (${queueBefore} before, ${kitchen.queueLength('downtown')} after)`);
}

// --- 4. Delivery: routed to the best shop, driver tracked live --------------

console.log('\n=== Delivery order ===');
const customerHome = { lat: 37.7549, lng: -122.4194 }; // near Mission
const delivery = await orchestrator.checkout({
  customerId: 'cust-dave',
  fulfillment: 'delivery',
  deliveryAddress: customerHome,
  items: [{ menuItemId: 'blt', quantity: 2 }],
});
const route = delivery.deliveryRoute!;
console.log(`Routed to ${delivery.location.name} — fastest of ${2} providers: ${route.provider}, ${route.distanceKm.toFixed(1)} km, ${mins(route.durationMinutes)} (incl. ${mins(route.trafficDelayMinutes)} traffic)`);
console.log(`Estimated ready at ${delivery.estimatedReadyAt.toLocaleTimeString()}`);

const tracking = (await orchestrator.markReady(delivery.order.id))!;
console.log(`Kitchen done -> driver ${tracking.driver.name} dispatched`);
tracking.on('position', ({ position, waypointIndex, totalWaypoints }: PositionUpdate) => {
  console.log(`  [track] ${tracking.driver.name} at (${position.lat.toFixed(4)}, ${position.lng.toFixed(4)}) — waypoint ${waypointIndex + 1}/${totalWaypoints}`);
});
await tracking.delivered();
console.log(`Delivered! Order status: ${orchestrator.getOrder(delivery.order.id).status}`);
