import type { Order } from '../domain/types.ts';

const AVG_MINUTES_PER_QUEUED_ORDER = 4;
const BASE_PREP_MINUTES = 3;
const PREP_MINUTES_PER_ITEM = 1.5;

/**
 * One prep queue per shop. Hard-gates on payment: an order without a
 * confirmed payment never reaches a kitchen ticket.
 */
export class KitchenService {
  private readonly queues = new Map<string, string[]>();

  queueLength(locationId: string): number {
    return this.queueFor(locationId).length;
  }

  /** Estimate assuming the order joins the back of the current queue. */
  estimateReadyAt(locationId: string, itemCount: number, from: Date = new Date()): Date {
    const waitMinutes = this.queueLength(locationId) * AVG_MINUTES_PER_QUEUED_ORDER;
    const prepMinutes = BASE_PREP_MINUTES + PREP_MINUTES_PER_ITEM * itemCount;
    return new Date(from.getTime() + (waitMinutes + prepMinutes) * 60_000);
  }

  submitOrder(order: Order): Date {
    if (order.status !== 'paid' || !order.paymentId) {
      throw new Error(`Order ${order.id} cannot be sent to the kitchen without a confirmed payment`);
    }
    const itemCount = order.lines.reduce((n, line) => n + line.quantity, 0);
    const estimatedReadyAt = this.estimateReadyAt(order.locationId, itemCount, order.placedAt);
    this.queueFor(order.locationId).push(order.id);
    order.status = 'submitted_to_kitchen';
    order.estimatedReadyAt = estimatedReadyAt;
    return estimatedReadyAt;
  }

  markReady(order: Order): void {
    const queue = this.queueFor(order.locationId);
    const index = queue.indexOf(order.id);
    if (index === -1) throw new Error(`Order ${order.id} is not in the ${order.locationId} queue`);
    queue.splice(index, 1);
    order.status = 'ready';
  }

  private queueFor(locationId: string): string[] {
    let queue = this.queues.get(locationId);
    if (!queue) {
      queue = [];
      this.queues.set(locationId, queue);
    }
    return queue;
  }
}
