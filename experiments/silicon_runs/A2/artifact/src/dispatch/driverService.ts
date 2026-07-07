import { EventEmitter } from 'node:events';
import type { Coordinates, Order } from '../domain/types.ts';
import type { RouteEstimate } from '../routing/mappingService.ts';

export interface Driver {
  id: string;
  name: string;
}

export interface PositionUpdate {
  orderId: string;
  driver: Driver;
  position: Coordinates;
  waypointIndex: number;
  totalWaypoints: number;
}

/**
 * Live handle for one delivery. Emits:
 *  - 'position' (PositionUpdate) as the driver advances along the route
 *  - 'delivered' (orderId) when the driver reaches the customer
 */
export class DeliveryTracking extends EventEmitter {
  status: 'en_route' | 'delivered' = 'en_route';
  readonly orderId: string;
  readonly driver: Driver;

  constructor(orderId: string, driver: Driver) {
    super();
    this.orderId = orderId;
    this.driver = driver;
  }

  delivered(): Promise<void> {
    if (this.status === 'delivered') return Promise.resolve();
    return new Promise((resolve) => this.once('delivered', resolve));
  }
}

export class DriverService {
  private readonly availableDrivers: Driver[];
  private readonly trackings = new Map<string, DeliveryTracking>();
  private readonly tickMs: number;

  constructor(drivers: Driver[], tickMs = 300) {
    this.availableDrivers = [...drivers];
    this.tickMs = tickMs;
  }

  /** Assigns a driver and starts a simulated drive along the route. */
  dispatch(order: Order, route: RouteEstimate): DeliveryTracking {
    const driver = this.availableDrivers.shift();
    if (!driver) throw new Error('No drivers available');

    order.status = 'out_for_delivery';
    const tracking = new DeliveryTracking(order.id, driver);
    this.trackings.set(order.id, tracking);
    this.simulateDrive(order, route, tracking, driver);
    return tracking;
  }

  track(orderId: string): DeliveryTracking {
    const tracking = this.trackings.get(orderId);
    if (!tracking) throw new Error(`No active delivery for order ${orderId}`);
    return tracking;
  }

  private simulateDrive(order: Order, route: RouteEstimate, tracking: DeliveryTracking, driver: Driver): void {
    let index = 0;
    const timer = setInterval(() => {
      const position = route.waypoints[index];
      if (position) {
        tracking.emit('position', {
          orderId: order.id,
          driver,
          position,
          waypointIndex: index,
          totalWaypoints: route.waypoints.length,
        } satisfies PositionUpdate);
      }
      index++;
      if (index >= route.waypoints.length) {
        clearInterval(timer);
        tracking.status = 'delivered';
        order.status = 'completed';
        this.availableDrivers.push(driver);
        tracking.emit('delivered', order.id);
      }
    }, this.tickMs);
  }
}
