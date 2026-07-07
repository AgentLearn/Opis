import { EventEmitter } from "node:events";
import type { Order } from "../domain/types.ts";
import type { RouteEstimate } from "../routing/mapping.ts";

export type Driver = { id: string; name: string };

export type TrackingEvent =
  | { type: "dispatched"; orderId: string; driver: Driver; etaMinutes: number }
  | { type: "position"; orderId: string; step: string; remainingMinutes: number }
  | { type: "delivered"; orderId: string };

/**
 * Live tracking for one delivery. Observers subscribe with onUpdate();
 * advance() moves the driver one route step (a real system would feed this
 * from the driver app's GPS pings).
 */
export class DeliveryTracking {
  private readonly emitter = new EventEmitter();
  private stepIndex = 0;
  delivered = false;

  readonly order: Order;
  readonly driver: Driver;
  readonly route: RouteEstimate;

  constructor(order: Order, driver: Driver, route: RouteEstimate) {
    this.order = order;
    this.driver = driver;
    this.route = route;
  }

  onUpdate(listener: (event: TrackingEvent) => void): void {
    this.emitter.on("update", listener);
  }

  private emit(event: TrackingEvent): void {
    this.emitter.emit("update", event);
  }

  start(): void {
    this.order.status = "out-for-delivery";
    this.emit({ type: "dispatched", orderId: this.order.id, driver: this.driver, etaMinutes: this.route.minutes });
  }

  advance(): void {
    if (this.delivered) return;
    if (this.stepIndex < this.route.steps.length) {
      const step = this.route.steps[this.stepIndex];
      const remaining = this.route.minutes * (1 - (this.stepIndex + 1) / this.route.steps.length);
      this.stepIndex += 1;
      this.emit({ type: "position", orderId: this.order.id, step, remainingMinutes: Math.round(remaining * 10) / 10 });
    } else {
      this.delivered = true;
      this.order.status = "delivered";
      this.emit({ type: "delivered", orderId: this.order.id });
    }
  }
}

export class NoDriverAvailableError extends Error {
  constructor() {
    super("No driver available");
  }
}

/** Assigns free drivers to delivery orders and hands back a live tracker. */
export class DriverDispatcher {
  private readonly available: Driver[];
  private readonly active = new Map<string, DeliveryTracking>();

  constructor(drivers: Driver[]) {
    this.available = [...drivers];
  }

  dispatch(order: Order, route: RouteEstimate): DeliveryTracking {
    const driver = this.available.shift();
    if (!driver) throw new NoDriverAvailableError();
    const tracking = new DeliveryTracking(order, driver, route);
    this.active.set(order.id, tracking);
    tracking.onUpdate((e) => {
      if (e.type === "delivered") {
        this.active.delete(order.id);
        this.available.push(driver);
      }
    });
    return tracking;
  }

  trackingFor(orderId: string): DeliveryTracking | undefined {
    return this.active.get(orderId);
  }
}
