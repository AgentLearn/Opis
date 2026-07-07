import type { Coordinates } from '../domain/types.ts';

export interface RouteEstimate {
  provider: string;
  distanceKm: number;
  /** Total drive time including traffic. */
  durationMinutes: number;
  trafficDelayMinutes: number;
  waypoints: Coordinates[];
}

/** Adapter interface every external mapping provider is wrapped behind. */
export interface MappingService {
  readonly name: string;
  route(from: Coordinates, to: Coordinates): Promise<RouteEstimate>;
}

/**
 * Returns a congestion multiplier (>= 1) for the current moment.
 * Injectable so tests and demos can pin traffic conditions.
 */
export type TrafficSource = () => number;

export const rushHourTraffic: TrafficSource = () => {
  const hour = new Date().getHours();
  const isRushHour = (hour >= 7 && hour < 10) || (hour >= 16 && hour < 19);
  return isRushHour ? 1.5 : 1.1;
};
