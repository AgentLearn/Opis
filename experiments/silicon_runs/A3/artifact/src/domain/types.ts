export type Coordinates = { lat: number; lng: number };

export type FulfilmentType = "pickup" | "delivery";

export type OrderStatus =
  | "created"
  | "validated"
  | "submitted"
  | "ready"
  | "out-for-delivery"
  | "delivered"
  | "picked-up";

export type OrderLine = {
  itemId: string;
  quantity: number;
};

export type PricedLine = OrderLine & {
  name: string;
  unitPriceCents: number;
  lineTotalCents: number;
};

export type Order = {
  id: string;
  customerId: string;
  shopId: string;
  fulfilment: FulfilmentType;
  lines: PricedLine[];
  subtotalCents: number;
  discountCents: number;
  totalCents: number;
  paymentTransactionId: string;
  status: OrderStatus;
  createdAt: Date;
};

export type Customer = {
  id: string;
  name: string;
  location: Coordinates;
};

let counter = 0;

/** Monotonic, human-readable ids — good enough for a single-process system. */
export function nextId(prefix: string): string {
  counter += 1;
  return `${prefix}-${counter.toString().padStart(4, "0")}`;
}
