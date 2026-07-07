import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildSystem } from '../fixtures.ts';

test('an owner can reprice items on their own menu without affecting other shops', () => {
  const sys = buildSystem();
  sys.menus.setPrice('own_ada', 'shop_soma', 'blt', 1395);

  assert.equal(sys.menus.getItem('shop_soma', 'blt')!.price, 1395);
  assert.equal(sys.menus.getItem('shop_mission', 'blt')!.price, 1150, 'other shop unchanged');
});

test('an owner can add a location-specific item', () => {
  const sys = buildSystem();
  sys.menus.upsertItem('own_bob', 'shop_mission', {
    id: 'torta',
    name: 'Mission Torta',
    price: 1195,
    available: true,
  });

  assert.ok(sys.menus.getItem('shop_mission', 'torta'));
  assert.equal(sys.menus.getItem('shop_soma', 'torta'), undefined);
});

test('an owner cannot edit another franchise’s menu', () => {
  const sys = buildSystem();
  assert.throws(
    () => sys.menus.setPrice('own_bob', 'shop_soma', 'blt', 1),
    /not authorized/,
  );
});
