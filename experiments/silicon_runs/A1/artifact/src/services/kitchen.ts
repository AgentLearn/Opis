import type { Order } from '../domain/types.ts';

const BASE_PREP_MINUTES = 6;
const MINUTES_PER_QUEUED_ORDER = 4;

/**
 * One work queue per shop. Submission is the hard gate for the core
 * business rule: an order is only accepted with a confirmed payment.
 */
export class KitchenService {
  private readonly queues = new Map<string, Order[]>();

  queueLength(shopId: string): number {
    return (this.queues.get(shopId) ?? []).length;
  }

  /** Estimated wait for a *new* order placed now at this shop. */
  estimatePickupMinutes(shopId: string): number {
    return BASE_PREP_MINUTES + this.queueLength(shopId) * MINUTES_PER_QUEUED_ORDER;
  }

  submit(order: Order, payment: { status: string }): void {
    if (payment.status !== 'confirmed') {
      throw new Error(`Order ${order.id} rejected by kitchen: payment not confirmed`);
    }
    if (order.status !== 'validated') {
      throw new Error(`Order ${order.id} rejected by kitchen: not validated`);
    }
    const queue = this.queues.get(order.shopId) ?? [];
    queue.push(order);
    this.queues.set(order.shopId, queue);
    order.status = 'in-kitchen';
  }

  /** Kitchen finished the order; removes it from the queue. */
  markReady(orderId: string, shopId: string): Order {
    const queue = this.queues.get(shopId) ?? [];
    const idx = queue.findIndex((o) => o.id === orderId);
    if (idx === -1) throw new Error(`Order ${orderId} is not in the ${shopId} queue`);
    const [order] = queue.splice(idx, 1);
    order.status = 'ready';
    return order;
  }
}
