import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildSystem, customers } from './fixtures.ts';
import { PaymentDeclinedError } from './checkout.ts';

test('successful pickup order is paid, validated, and queued at the chosen shop', async () => {
  const sys = buildSystem();
  const receipt = await sys.checkout.placeOrder({
    customer: customers.nia,
    items: [{ itemId: 'blt', quantity: 2 }, { itemId: 'soda', quantity: 1 }],
    fulfillment: 'pickup',
    pickupShopId: 'shop_soma',
  });

  assert.equal(receipt.payment.status, 'confirmed');
  assert.equal(receipt.order.status, 'in-kitchen');
  assert.equal(receipt.order.shopId, 'shop_soma');
  assert.equal(receipt.order.total, 1150 * 2 + 295);
  assert.equal(sys.kitchen.queueLength('shop_soma'), 1);
  assert.equal(receipt.tracking, undefined, 'pickup orders get no driver');
});

test('declined payment never reaches the kitchen', async () => {
  const sys = buildSystem();
  sys.payments.declineCustomer(customers.nia.id);

  await assert.rejects(
    sys.checkout.placeOrder({
      customer: customers.nia,
      items: [{ itemId: 'blt', quantity: 1 }],
      fulfillment: 'pickup',
      pickupShopId: 'shop_soma',
    }),
    PaymentDeclinedError,
  );
  assert.equal(sys.kitchen.queueLength('shop_soma'), 0);
  assert.equal(sys.kitchen.queueLength('shop_mission'), 0);
});

test('pickup ETA grows with the kitchen queue', async () => {
  const sys = buildSystem();
  const order = () =>
    sys.checkout.placeOrder({
      customer: customers.nia,
      items: [{ itemId: 'veggie', quantity: 1 }],
      fulfillment: 'pickup',
      pickupShopId: 'shop_soma',
    });

  const first = await order();
  const second = await order();
  const third = await order();
  assert.ok(second.pickupEtaMinutes > first.pickupEtaMinutes);
  assert.ok(third.pickupEtaMinutes > second.pickupEtaMinutes);
});

test('loyalty points are earned on payment and redeemable at checkout', async () => {
  const sys = buildSystem();
  // Build up a balance: $25.95 order → 25 points, repeated.
  for (let i = 0; i < 5; i += 1) {
    await sys.checkout.placeOrder({
      customer: customers.nia,
      items: [{ itemId: 'blt', quantity: 2 }, { itemId: 'soda', quantity: 1 }],
      fulfillment: 'pickup',
      pickupShopId: 'shop_soma',
    });
  }
  assert.equal(sys.loyalty.balance(customers.nia.id), 125);

  const receipt = await sys.checkout.placeOrder({
    customer: customers.nia,
    items: [{ itemId: 'turkey', quantity: 1 }],
    fulfillment: 'pickup',
    pickupShopId: 'shop_soma',
    redeemLoyaltyPoints: true,
  });
  assert.equal(receipt.loyalty.discountApplied, 500, '100 points = $5 off');
  assert.equal(receipt.loyalty.pointsSpent, 100);
  assert.equal(receipt.order.total, 1250 - 500);
});

test('redeemed points are refunded when payment is declined', async () => {
  const sys = buildSystem();
  for (let i = 0; i < 5; i += 1) {
    await sys.checkout.placeOrder({
      customer: customers.nia,
      items: [{ itemId: 'blt', quantity: 2 }, { itemId: 'soda', quantity: 1 }],
      fulfillment: 'pickup',
      pickupShopId: 'shop_soma',
    });
  }
  const before = sys.loyalty.balance(customers.nia.id);
  sys.payments.declineCustomer(customers.nia.id);

  await assert.rejects(
    sys.checkout.placeOrder({
      customer: customers.nia,
      items: [{ itemId: 'turkey', quantity: 1 }],
      fulfillment: 'pickup',
      pickupShopId: 'shop_soma',
      redeemLoyaltyPoints: true,
    }),
  );
  assert.equal(sys.loyalty.balance(customers.nia.id), before);
});

test('delivery routes to the closest shop and dispatches a tracked driver', async () => {
  const sys = buildSystem();
  // Raj lives in the Mission — the Mission shop should win the ETA race.
  const receipt = await sys.checkout.placeOrder({
    customer: customers.raj,
    items: [{ itemId: 'turkey', quantity: 1 }],
    fulfillment: 'delivery',
  });

  assert.equal(receipt.order.shopId, 'shop_mission');
  assert.equal(receipt.order.status, 'out-for-delivery');
  assert.ok(receipt.tracking, 'delivery orders are tracked');

  const updates: number[] = [];
  receipt.tracking!.subscribe((u) => updates.push(u.progress));
  let last = receipt.tracking!.current();
  while (last.status !== 'delivered') {
    last = receipt.tracking!.tick(1);
  }
  assert.equal(last.status, 'delivered');
  assert.equal(last.progress, 1);
  assert.ok(updates.length > 1, 'subscriber saw live position updates');
  assert.deepEqual(last.position, customers.raj.address);
  assert.ok(sys.drivers.find((d) => d.id === last.driverId)!.available, 'driver freed after delivery');
});

test('delivery skips shops that cannot make every item', async () => {
  const sys = buildSystem();
  // Mission runs out of turkey — Raj's order must fall through to SoMa.
  sys.menus.setAvailability('own_bob', 'shop_mission', 'turkey', false);

  const receipt = await sys.checkout.placeOrder({
    customer: customers.raj,
    items: [{ itemId: 'turkey', quantity: 1 }],
    fulfillment: 'delivery',
  });
  assert.equal(receipt.order.shopId, 'shop_soma');
});
