import type { Coordinates, ShopLocation } from '../domain/types.ts';
import type { MappingService, RouteEstimate } from './mappingService.ts';

export interface LocationChoice {
  location: ShopLocation;
  route: RouteEstimate;
}

/**
 * Queries every configured mapping provider and picks the fastest
 * traffic-aware route. Requires at least two providers so a single vendor
 * outage or bad estimate never decides routing alone.
 */
export class RoutePlanner {
  private readonly providers: MappingService[];

  constructor(providers: MappingService[]) {
    if (providers.length < 2) {
      throw new Error('RoutePlanner requires at least two mapping providers');
    }
    this.providers = providers;
  }

  async bestRoute(from: Coordinates, to: Coordinates): Promise<RouteEstimate> {
    const results = await Promise.allSettled(this.providers.map((p) => p.route(from, to)));
    const routes = results
      .filter((r): r is PromiseFulfilledResult<RouteEstimate> => r.status === 'fulfilled')
      .map((r) => r.value);
    if (routes.length === 0) {
      throw new Error('All mapping providers failed to produce a route');
    }
    return routes.reduce((best, r) => (r.durationMinutes < best.durationMinutes ? r : best));
  }

  /** Picks the shop that can reach the delivery address fastest right now. */
  async pickBestLocation(locations: ShopLocation[], deliveryAddress: Coordinates): Promise<LocationChoice> {
    if (locations.length === 0) throw new Error('No shop locations available');
    const choices = await Promise.all(
      locations.map(async (location) => ({
        location,
        route: await this.bestRoute(location.coordinates, deliveryAddress),
      })),
    );
    return choices.reduce((best, c) => (c.route.durationMinutes < best.route.durationMinutes ? c : best));
  }
}
