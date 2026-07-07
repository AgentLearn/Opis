import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  GoogleMapsAdapter,
  OsrmAdapter,
  RoutePlanner,
  type MappingProvider,
} from './mapping.ts';
import type { GeoPoint } from '../domain/types.ts';

const A: GeoPoint = { lat: 37.778, lng: -122.405 };
const B: GeoPoint = { lat: 37.76, lng: -122.419 };

test('routes are traffic-aware: heavier traffic means a longer ETA', async () => {
  const calm = await new GoogleMapsAdapter(() => 1).getRoute(A, B);
  const jammed = await new GoogleMapsAdapter(() => 2.5).getRoute(A, B);
  assert.ok(jammed.durationMinutes > calm.durationMinutes * 2);
  assert.equal(jammed.distanceKm, calm.distanceKm, 'traffic changes time, not distance');
});

test('planner picks the fastest of the providers', async () => {
  const planner = new RoutePlanner([new GoogleMapsAdapter(), new OsrmAdapter()]);
  const best = await planner.bestRoute(A, B);
  const google = await new GoogleMapsAdapter().getRoute(A, B);
  const osrm = await new OsrmAdapter().getRoute(A, B);
  assert.equal(best.durationMinutes, Math.min(google.durationMinutes, osrm.durationMinutes));
});

test('planner falls back when a provider fails', async () => {
  const broken: MappingProvider = {
    name: 'broken',
    getRoute: async () => {
      throw new Error('503 from provider');
    },
  };
  const planner = new RoutePlanner([broken, new OsrmAdapter()]);
  const best = await planner.bestRoute(A, B);
  assert.equal(best.provider, 'osrm');
});

test('planner refuses to run with fewer than two providers', () => {
  assert.throws(() => new RoutePlanner([new OsrmAdapter()]));
});
