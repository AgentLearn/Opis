import type { Coordinates } from "../domain/types.ts";

export type RouteEstimate = {
  provider: string;
  minutes: number;
  distanceKm: number;
  steps: string[];
};

/** Adapter interface — one implementation per external mapping provider. */
export interface MappingService {
  readonly name: string;
  route(from: Coordinates, to: Coordinates): Promise<RouteEstimate>;
}

export function haversineKm(a: Coordinates, b: Coordinates): number {
  const R = 6371;
  const dLat = ((b.lat - a.lat) * Math.PI) / 180;
  const dLng = ((b.lng - a.lng) * Math.PI) / 180;
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((a.lat * Math.PI) / 180) * Math.cos((b.lat * Math.PI) / 180) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

/** Deterministic pseudo-traffic so two providers disagree in a stable way. */
function trafficFactor(seed: number, from: Coordinates, to: Coordinates): number {
  const n = Math.abs(Math.sin(seed + from.lat * 7 + from.lng * 13 + to.lat * 17 + to.lng * 19));
  return 1 + 0.5 * n; // 1.0x – 1.5x of free-flow time
}

class SimulatedMappingService implements MappingService {
  readonly name: string;
  private readonly seed: number;
  private readonly avgSpeedKmh: number;

  constructor(name: string, seed: number, avgSpeedKmh: number) {
    this.name = name;
    this.seed = seed;
    this.avgSpeedKmh = avgSpeedKmh;
  }

  async route(from: Coordinates, to: Coordinates): Promise<RouteEstimate> {
    const distanceKm = haversineKm(from, to);
    const freeFlowMinutes = (distanceKm / this.avgSpeedKmh) * 60;
    const minutes = freeFlowMinutes * trafficFactor(this.seed, from, to);
    return {
      provider: this.name,
      minutes: Math.round(minutes * 10) / 10,
      distanceKm: Math.round(distanceKm * 100) / 100,
      steps: [
        `Depart (${from.lat.toFixed(3)}, ${from.lng.toFixed(3)})`,
        `Follow ${this.name} traffic-optimized route`,
        `Arrive (${to.lat.toFixed(3)}, ${to.lng.toFixed(3)})`,
      ],
    };
  }
}

// The two external integrations required by the spec. Swapping in real HTTP
// adapters (Google Maps, TomTom, ...) means implementing MappingService.
export const goodMaps: MappingService = new SimulatedMappingService("GoodMaps", 1, 38);
export const openTraffic: MappingService = new SimulatedMappingService("OpenTraffic", 2, 42);

/**
 * Queries every configured provider in parallel and picks the fastest
 * traffic-aware route. Tolerates individual provider outages.
 */
export class RoutePlanner {
  private readonly services: MappingService[];

  constructor(services: MappingService[]) {
    if (services.length < 2) {
      throw new Error("RoutePlanner requires at least 2 mapping services");
    }
    this.services = services;
  }

  async bestRoute(from: Coordinates, to: Coordinates): Promise<RouteEstimate> {
    const results = await Promise.allSettled(this.services.map((s) => s.route(from, to)));
    const ok = results
      .filter((r): r is PromiseFulfilledResult<RouteEstimate> => r.status === "fulfilled")
      .map((r) => r.value);
    if (ok.length === 0) throw new Error("All mapping services failed");
    return ok.reduce((best, r) => (r.minutes < best.minutes ? r : best));
  }
}
