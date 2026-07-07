import { haversineKm, type GeoPoint, type Order } from '../domain/types.ts';
import type { RouteResult } from './mapping.ts';

export interface Driver {
  id: string;
  name: string;
  location: GeoPoint;
  available: boolean;
}

export interface TrackingUpdate {
  orderId: string;
  driverId: string;
  status: 'en-route' | 'delivered';
  position: GeoPoint;
  /** 0..1 along the shop → dropoff route. */
  progress: number;
  etaMinutes: number;
}

type TrackingListener = (update: TrackingUpdate) => void;

/**
 * Live tracking for one delivery. `tick(minutes)` advances the driver
 * along the route path; callers (demo UI, tests) control the clock, so
 * behavior is deterministic. Subscribers get every position update.
 */
export class DeliveryTracking {
  readonly orderId: string;
  readonly driver: Driver;
  private readonly route: RouteResult;
  private elapsedMinutes = 0;
  private readonly listeners: TrackingListener[] = [];
  private lastUpdate: TrackingUpdate;

  constructor(order: Order, driver: Driver, route: RouteResult) {
    this.orderId = order.id;
    this.driver = driver;
    this.route = route;
    this.lastUpdate = this.snapshot();
  }

  subscribe(listener: TrackingListener): void {
    this.listeners.push(listener);
    listener(this.lastUpdate);
  }

  tick(minutes: number): TrackingUpdate {
    this.elapsedMinutes = Math.min(this.elapsedMinutes + minutes, this.route.durationMinutes);
    this.lastUpdate = this.snapshot();
    if (this.lastUpdate.status === 'delivered') {
      this.driver.available = true;
    }
    for (const l of this.listeners) l(this.lastUpdate);
    return this.lastUpdate;
  }

  current(): TrackingUpdate {
    return this.lastUpdate;
  }

  private snapshot(): TrackingUpdate {
    const progress = this.route.durationMinutes === 0
      ? 1
      : this.elapsedMinutes / this.route.durationMinutes;
    const path = this.route.path;
    const idx = Math.min(Math.floor(progress * (path.length - 1)), path.length - 1);
    return {
      orderId: this.orderId,
      driverId: this.driver.id,
      status: progress >= 1 ? 'delivered' : 'en-route',
      position: path[idx],
      progress,
      etaMinutes: Math.max(this.route.durationMinutes - this.elapsedMinutes, 0),
    };
  }
}

/** Assigns the nearest available driver to a delivery and tracks it. */
export class DriverDispatcher {
  private readonly drivers: Driver[];

  constructor(drivers: Driver[]) {
    this.drivers = drivers;
  }

  dispatch(order: Order, shopLocation: GeoPoint, route: RouteResult): DeliveryTracking {
    const available = this.drivers.filter((d) => d.available);
    if (available.length === 0) throw new Error('No drivers available');
    const driver = available.reduce((best, d) =>
      haversineKm(d.location, shopLocation) < haversineKm(best.location, shopLocation) ? d : best,
    );
    driver.available = false;
    order.status = 'out-for-delivery';
    return new DeliveryTracking(order, driver, route);
  }
}
