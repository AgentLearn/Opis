import type { Coordinates, Order } from "../domain/types.ts";
import type { FranchiseMenu } from "../menu/menu.ts";

/** FIFO kitchen queue for one shop; queue length drives pickup estimates. */
export class KitchenQueue {
  private readonly pending: Order[] = [];

  submit(order: Order): void {
    this.pending.push(order);
  }

  markReady(orderId: string): Order | undefined {
    const idx = this.pending.findIndex((o) => o.id === orderId);
    if (idx === -1) return undefined;
    const [order] = this.pending.splice(idx, 1);
    order.status = "ready";
    return order;
  }

  get length(): number {
    return this.pending.length;
  }

  has(orderId: string): boolean {
    return this.pending.some((o) => o.id === orderId);
  }
}

export class Shop {
  readonly kitchen = new KitchenQueue();
  readonly id: string;
  readonly name: string;
  readonly location: Coordinates;
  readonly menu: FranchiseMenu;

  constructor(id: string, name: string, location: Coordinates, menu: FranchiseMenu) {
    this.id = id;
    this.name = name;
    this.location = location;
    this.menu = menu;
  }
}

const PREP_MINUTES_PER_ORDER = 4;
const BASE_PREP_MINUTES = 6;

/** Pickup estimate: fixed prep time plus the backlog ahead of this order. */
export function estimatePickupMinutes(queueLengthAhead: number): number {
  return BASE_PREP_MINUTES + PREP_MINUTES_PER_ORDER * queueLengthAhead;
}
