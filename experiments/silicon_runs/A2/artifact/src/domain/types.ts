export interface Coordinates {
  lat: number;
  lng: number;
}

export interface Customer {
  id: string;
  name: string;
}

export interface FranchiseOwner {
  id: string;
  name: string;
}

export interface ShopLocation {
  id: string;
  name: string;
  ownerId: string;
  coordinates: Coordinates;
}

export interface MenuItem {
  id: string;
  name: string;
  priceCents: number;
  available: boolean;
}

export type FulfillmentType = 'pickup' | 'delivery';

export interface OrderItemRequest {
  menuItemId: string;
  quantity: number;
}

export interface OrderLine {
  menuItemId: string;
  name: string;
  quantity: number;
  unitPriceCents: number;
}

export type OrderStatus =
  | 'paid'
  | 'submitted_to_kitchen'
  | 'ready'
  | 'out_for_delivery'
  | 'completed'
  | 'cancelled';

export interface Order {
  id: string;
  customerId: string;
  locationId: string;
  fulfillment: FulfillmentType;
  lines: OrderLine[];
  subtotalCents: number;
  loyaltyDiscountCents: number;
  totalCents: number;
  status: OrderStatus;
  paymentId: string;
  placedAt: Date;
  estimatedReadyAt?: Date;
  deliveryAddress?: Coordinates;
}
