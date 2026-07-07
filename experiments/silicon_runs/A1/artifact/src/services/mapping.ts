import { haversineKm, type GeoPoint } from '../domain/types.ts';

export interface RouteResult {
  provider: string;
  distanceKm: number;
  durationMinutes: number;
  /** Simplified turn-by-turn path from origin to destination. */
  path: GeoPoint[];
}

/** External mapping service (Google Maps, OSRM, ...) behind one interface. */
export interface MappingProvider {
  readonly name: string;
  getRoute(from: GeoPoint, to: GeoPoint): Promise<RouteResult>;
}

/** Current congestion multiplier for a leg; 1 = free flow, 2 = twice as slow. */
export type TrafficFeed = (from: GeoPoint, to: GeoPoint) => number;

export const freeFlow: TrafficFeed = () => 1;

function interpolatePath(from: GeoPoint, to: GeoPoint, segments: number): GeoPoint[] {
  const path: GeoPoint[] = [];
  for (let i = 0; i <= segments; i += 1) {
    const t = i / segments;
    path.push({ lat: from.lat + (to.lat - from.lat) * t, lng: from.lng + (to.lng - from.lng) * t });
  }
  return path;
}

/**
 * Simulated adapter over the Google Maps Directions API.
 * Slightly longer routes (road factor) but a faster average speed.
 */
export class GoogleMapsAdapter implements MappingProvider {
  readonly name = 'google-maps';
  private readonly traffic: TrafficFeed;

  constructor(traffic: TrafficFeed = freeFlow) {
    this.traffic = traffic;
  }

  async getRoute(from: GeoPoint, to: GeoPoint): Promise<RouteResult> {
    const distanceKm = haversineKm(from, to) * 1.25;
    const speedKmh = 38 / this.traffic(from, to);
    return {
      provider: this.name,
      distanceKm,
      durationMinutes: (distanceKm / speedKmh) * 60,
      path: interpolatePath(from, to, 10),
    };
  }
}

/**
 * Simulated adapter over an OSRM-style open routing service.
 * More direct routes but a more conservative speed model.
 */
export class OsrmAdapter implements MappingProvider {
  readonly name = 'osrm';
  private readonly traffic: TrafficFeed;

  constructor(traffic: TrafficFeed = freeFlow) {
    this.traffic = traffic;
  }

  async getRoute(from: GeoPoint, to: GeoPoint): Promise<RouteResult> {
    const distanceKm = haversineKm(from, to) * 1.18;
    const speedKmh = 32 / this.traffic(from, to);
    return {
      provider: this.name,
      distanceKm,
      durationMinutes: (distanceKm / speedKmh) * 60,
      path: interpolatePath(from, to, 8),
    };
  }
}

/**
 * Queries every configured provider in parallel and returns the fastest
 * route. Provider failures are tolerated as long as at least one answers.
 */
export class RoutePlanner {
  private readonly providers: MappingProvider[];

  constructor(providers: MappingProvider[]) {
    if (providers.length < 2) {
      throw new Error('RoutePlanner requires at least two mapping providers');
    }
    this.providers = providers;
  }

  async bestRoute(from: GeoPoint, to: GeoPoint): Promise<RouteResult> {
    const results = await Promise.allSettled(this.providers.map((p) => p.getRoute(from, to)));
    const routes = results
      .filter((r): r is PromiseFulfilledResult<RouteResult> => r.status === 'fulfilled')
      .map((r) => r.value);
    if (routes.length === 0) {
      throw new Error('All mapping providers failed');
    }
    return routes.reduce((best, r) => (r.durationMinutes < best.durationMinutes ? r : best));
  }
}
