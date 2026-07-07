import assert from 'node:assert/strict';
import { test } from 'node:test';
import { buildSystem } from './helpers.ts';

test('owners update their own menu and pricing independently', () => {
  const { menus } = buildSystem();

  menus.setPrice('owner-a', 'downtown', 'blt', 1250);

  assert.equal(menus.getItem('downtown', 'blt')?.priceCents, 1250);
  assert.equal(menus.getItem('mission', 'blt')?.priceCents, 1000, 'other franchise unaffected');
});

test('an owner cannot modify another franchise menu', () => {
  const { menus } = buildSystem();

  assert.throws(() => menus.setPrice('owner-b', 'downtown', 'blt', 1), /not authorized/);
  assert.throws(
    () => menus.upsertItem('owner-b', 'downtown', { id: 'new', name: 'New', priceCents: 500, available: true }),
    /not authorized/,
  );
  assert.equal(menus.getItem('downtown', 'blt')?.priceCents, 1000);
});

test('loyalty rejects redeeming more points than the balance', () => {
  const { loyalty } = buildSystem();
  loyalty.refund('cust-1', 10);
  assert.throws(() => loyalty.redeem('cust-1', 11), /Insufficient/);
  assert.equal(loyalty.balance('cust-1'), 10);
});
