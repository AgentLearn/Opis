import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { Order } from '../src/domain/types.ts';
import { PaymentDeclinedError, type CheckoutRequest } from '../src/orders/orderOrchestrator.ts';
import { buildSystem } from './helpers.ts';

test('successful pickup checkout: pays, submits to kitchen, earns points', async () => {
  const { orchestrator, kitchen, loyalty } = buildSystem();

  const result = await orchestrator.checkout({
    customerId: 'cust-1',
    fulfillment: 'pickup',
    locationId: 'downtown',
    items: [
      { menuItemId: 'blt', quantity: 1 },
      { menuItemId: 'soda', quantity: 2 },
    ],
  });

  assert.equal(result.order.status, 'submitted_to_kitchen');
  assert.equal(result.order.subtotalCents, 1600);
  assert.equal(result.order.totalCents, 1600);
  assert.ok(result.order.paymentId.startsWith('pay_'));
  assert.equal(kitchen.queueLength('downtown'), 1);
  assert.equal(result.pointsEarned, 16);
  assert.equal(loyalty.balance('cust-1'), 16);
});

test('declined payment: order never reaches the kitchen and points are refunded', async () => {
  const { orchestrator, kitchen, payments, loyalty } = buildSystem();
  loyalty.refund('cust-1', 50);
  payments.declineNextChargeFor('cust-1');

  await assert.rejects(
    orchestrator.checkout({
      customerId: 'cust-1',
      fulfillment: 'pickup',
      locationId: 'downtown',
      items: [{ menuItemId: 'blt', quantity: 1 }],
      redeemPoints: 50,
    }),
    PaymentDeclinedError,
  );

  assert.equal(kitchen.queueLength('downtown'), 0);
  assert.equal(loyalty.balance('cust-1'), 50);
});

test('kitchen rejects an order without confirmed payment', () => {
  const { kitchen } = buildSystem();
  const unpaidOrder: Order = {
    id: 'ord_x',
    customerId: 'cust-1',
    locationId: 'downtown',
    fulfillment: 'pickup',
    lines: [{ menuItemId: 'blt', name: 'BLT', quantity: 1, unitPriceCents: 1000 }],
    subtotalCents: 1000,
    loyaltyDiscountCents: 0,
    totalCents: 1000,
    status: 'cancelled',
    paymentId: '',
    placedAt: new Date(),
  };

  assert.throws(() => kitchen.submitOrder(unpaidOrder), /confirmed payment/);
  assert.equal(kitchen.queueLength('downtown'), 0);
});

test('pickup estimate grows with queue length', async () => {
  const { orchestrator } = buildSystem();
  const request: CheckoutRequest = {
    customerId: 'cust-1',
    fulfillment: 'pickup',
    locationId: 'downtown',
    items: [{ menuItemId: 'blt', quantity: 1 }],
  };

  const first = await orchestrator.checkout(request);
  const second = await orchestrator.checkout(request);

  const gapMinutes = (second.estimatedReadyAt.getTime() - first.estimatedReadyAt.getTime()) / 60_000;
  assert.ok(gapMinutes >= 3.9, `expected the second order to wait behind the first, gap was ${gapMinutes} min`);
});

test('unavailable menu item blocks checkout before payment', async () => {
  const { orchestrator, menus } = buildSystem();
  menus.setAvailability('owner-a', 'downtown', 'blt', false);

  await assert.rejects(
    orchestrator.checkout({
      customerId: 'cust-1',
      fulfillment: 'pickup',
      locationId: 'downtown',
      items: [{ menuItemId: 'blt', quantity: 1 }],
    }),
    /unavailable/,
  );
});

test('loyalty redemption discounts the total', async () => {
  const { orchestrator, loyalty } = buildSystem();
  loyalty.refund('cust-1', 100); // seed 100 points = $5.00

  const result = await orchestrator.checkout({
    customerId: 'cust-1',
    fulfillment: 'pickup',
    locationId: 'downtown',
    items: [{ menuItemId: 'blt', quantity: 1 }],
    redeemPoints: 100,
  });

  assert.equal(result.order.loyaltyDiscountCents, 500);
  assert.equal(result.order.totalCents, 500);
  assert.equal(loyalty.balance('cust-1'), 5); // earned 5 pts on the $5 paid
});
