/**
 * End-to-end walkthrough of the Silicon Sandwiches order flow.
 * Run with: npm run demo   (or: node src/demo.ts)
 */
import { buildSystem, customers } from './fixtures.ts';
import { PaymentDeclinedError } from './checkout.ts';
import type { Money } from './domain/types.ts';

const usd = (cents: Money) => `$${(cents / 100).toFixed(2)}`;
const log = (msg: string) => console.log(msg);

// Lunch rush: everything moves at ~60% of free-flow speed.
const sys = buildSystem(() => 1.6);

log('=== Silicon Sandwiches ===\n');

// --- Franchise owners tune their own menus -------------------------------
sys.menus.setPrice('own_ada', 'shop_soma', 'blt', 1295);
sys.menus.upsertItem('own_bob', 'shop_mission', {
  id: 'torta', name: 'Mission Torta', price: 1195, available: true,
});
log('Ada (SoMa) repriced the BLT to $12.95; Bob (Mission) added a Torta.');
try {
  sys.menus.setPrice('own_bob', 'shop_soma', 'blt', 1);
} catch (e) {
  log(`Bob tried to edit SoMa's menu → "${(e as Error).message}"\n`);
}

// --- Pickup order ---------------------------------------------------------
log('--- Nia orders pickup at SoMa ---');
const pickup = await sys.checkout.placeOrder({
  customer: customers.nia,
  items: [{ itemId: 'blt', quantity: 1 }, { itemId: 'soda', quantity: 1 }],
  fulfillment: 'pickup',
  pickupShopId: 'shop_soma',
});
for (const l of pickup.order.lines) log(`  ${l.quantity}× ${l.name} @ ${usd(l.unitPrice)}`);
log(`  Payment ${pickup.payment.id}: ${pickup.payment.status} for ${usd(pickup.order.total)}`);
log(`  Order ${pickup.order.id} → ${pickup.order.shopId} kitchen (queue was empty)`);
log(`  Ready for pickup in ~${pickup.pickupEtaMinutes} min`);
log(`  Loyalty: earned ${pickup.loyalty.pointsEarned} pts (balance ${pickup.loyalty.balance})\n`);

// --- Declined payment never reaches the kitchen ---------------------------
log('--- A declined card ---');
sys.payments.declineCustomer('cus_mallory');
try {
  await sys.checkout.placeOrder({
    customer: { id: 'cus_mallory', name: 'Mallory' },
    items: [{ itemId: 'turkey', quantity: 10 }],
    fulfillment: 'pickup',
    pickupShopId: 'shop_soma',
  });
} catch (e) {
  if (e instanceof PaymentDeclinedError) {
    log(`  ${e.message} — kitchen queue untouched (still ${sys.kitchen.queueLength('shop_soma')} order)\n`);
  }
}

// --- Delivery order with routing + live tracking --------------------------
log('--- Raj orders delivery (lunch-rush traffic) ---');
const delivery = await sys.checkout.placeOrder({
  customer: customers.raj,
  items: [{ itemId: 'torta', quantity: 2 }],
  fulfillment: 'delivery',
});
log(`  Routed to ${delivery.order.shopId} — fastest traffic-aware ETA to Raj`);
log(`  Payment ${delivery.payment.status} for ${usd(delivery.order.total)}`);
const t = delivery.tracking!;
log(`  Driver ${t.driver.name} dispatched, ETA ${t.current().etaMinutes.toFixed(1)} min`);
while (t.current().status !== 'delivered') {
  const u = t.tick(1);
  const pos = `(${u.position.lat.toFixed(4)}, ${u.position.lng.toFixed(4)})`;
  log(`    [live] ${u.status} ${Math.round(u.progress * 100)}% at ${pos}, eta ${u.etaMinutes.toFixed(1)} min`);
}
log(`  Delivered. Driver ${t.driver.name} is available again.\n`);

log(`Loyalty balances: Nia ${sys.loyalty.balance('cus_nia')} pts, Raj ${sys.loyalty.balance('cus_raj')} pts`);
