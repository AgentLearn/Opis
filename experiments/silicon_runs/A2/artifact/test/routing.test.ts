import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { Coordinates } from '../src/domain/types.ts';
import type { MappingService } from '../src/routing/mappingService.ts';
import { AtlasRoutingClient } from '../src/routing/providers/atlasRouting.ts';
import { SpeedyMapsClient } from '../src/routing/providers/speedyMaps.ts';
import { RoutePlanner } from '../src/routing/routePlanner.ts';
import { buildSystem, NO_TRAFFIC } from './helpers.ts';

const SF: Coordinates = { lat: 37.7749, lng: -122.4194 };
const OAKLAND: Coordinates = { lat: 37.8044, lng: -122.2712 };

test('planner requires at least two mapping providers', () => {
  assert.throws(() => new RoutePlanner([new SpeedyMapsClient(NO_TRAFFIC)]), /at least two/);
});

test('planner picks the fastest route across providers', async () => {
  const planner = new RoutePlanner([new SpeedyMapsClient(NO_TRAFFIC), new AtlasRoutingClient(NO_TRAFFIC)]);
  const speedy = await new SpeedyMapsClient(NO_TRAFFIC).route(SF, OAKLAND);
  const atlas = await new AtlasRoutingClient(NO_TRAFFIC).route(SF, OAKLAND);

  const best = await planner.bestRoute(SF, OAKLAND);
  assert.equal(best.durationMinutes, Math.min(speedy.durationMinutes, atlas.durationMinutes));
});

test('planner survives one provider failing', async () => {
  const broken: MappingService = {
    name: 'Broken',
    route: async () => {
      throw new Error('provider outage');
    },
  };
  const planner = new RoutePlanner([broken, new AtlasRoutingClient(NO_TRAFFIC)]);
  const route = await planner.bestRoute(SF, OAKLAND);
  assert.equal(route.provider, 'AtlasRouting');
});

test('routes are traffic-aware', async () => {
  const heavyTraffic = new SpeedyMapsClient(() => 2);
  const freeFlow = new SpeedyMapsClient(NO_TRAFFIC);

  const congested = await heavyTraffic.route(SF, OAKLAND);
  const clear = await freeFlow.route(SF, OAKLAND);

  assert.ok(congested.durationMinutes > clear.durationMinutes);
  assert.ok(congested.trafficDelayMinutes > 0);
  assert.equal(clear.trafficDelayMinutes, 0);
});

test('delivery order is routed to the nearest shop', async () => {
  const { orchestrator } = buildSystem();
  const nearMission: Coordinates = { lat: 37.7549, lng: -122.4194 };

  const result = await orchestrator.checkout({
    customerId: 'cust-1',
    fulfillment: 'delivery',
    deliveryAddress: nearMission,
    items: [{ menuItemId: 'blt', quantity: 1 }],
  });

  assert.equal(result.location.id, 'mission');
  assert.ok(result.deliveryRoute);
});

test('driver is dispatched when a delivery order is ready and tracking emits updates', async () => {
  const { orchestrator } = buildSystem();
  const result = await orchestrator.checkout({
    customerId: 'cust-1',
    fulfillment: 'delivery',
    deliveryAddress: { lat: 37.7549, lng: -122.4194 },
    items: [{ menuItemId: 'blt', quantity: 1 }],
  });

  const tracking = await orchestrator.markReady(result.order.id);
  assert.ok(tracking, 'delivery order should get a driver');

  let updates = 0;
  tracking.on('position', () => updates++);
  await tracking.delivered();

  assert.ok(updates > 0, 'tracking should emit position updates');
  assert.equal(orchestrator.getOrder(result.order.id).status, 'completed');
});

test('pickup orders do not dispatch a driver', async () => {
  const { orchestrator } = buildSystem();
  const result = await orchestrator.checkout({
    customerId: 'cust-1',
    fulfillment: 'pickup',
    locationId: 'downtown',
    items: [{ menuItemId: 'blt', quantity: 1 }],
  });

  const tracking = await orchestrator.markReady(result.order.id);
  assert.equal(tracking, undefined);
  orchestrator.completePickup(result.order.id);
  assert.equal(orchestrator.getOrder(result.order.id).status, 'completed');
});
