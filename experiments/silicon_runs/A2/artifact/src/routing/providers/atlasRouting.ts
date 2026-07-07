import type { Coordinates } from '../../domain/types.ts';
import { haversineKm, interpolate } from '../geo.ts';
import { rushHourTraffic, type MappingService, type RouteEstimate, type TrafficSource } from '../mappingService.ts';

/**
 * Adapter for the fictional "AtlasRouting" API: prefers direct surface
 * streets — shorter routes at lower average speed.
 */
export class AtlasRoutingClient implements MappingService {
  readonly name = 'AtlasRouting';
  private readonly roadFactor = 1.15;
  private readonly avgSpeedKmh = 29;
  private readonly traffic: TrafficSource;

  constructor(traffic: TrafficSource = rushHourTraffic) {
    this.traffic = traffic;
  }

  async route(from: Coordinates, to: Coordinates): Promise<RouteEstimate> {
    const distanceKm = haversineKm(from, to) * this.roadFactor;
    const baseMinutes = (distanceKm / this.avgSpeedKmh) * 60;
    const durationMinutes = baseMinutes * this.traffic();
    return {
      provider: this.name,
      distanceKm,
      durationMinutes,
      trafficDelayMinutes: durationMinutes - baseMinutes,
      waypoints: interpolate(from, to, 12),
    };
  }
}
