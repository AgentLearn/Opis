/** Shared domain types. All money values are integer cents. */

export type Money = number;

export interface GeoPoint {
  lat: number;
  lng: number;
}

export type FulfillmentType = 'pickup' | 'delivery';

export interface Customer {
  id: string;
  name: string;
  /** Default delivery address, if any. */
  address?: GeoPoint;
}

export interface FranchiseOwner {
  id: string;
  name: string;
}

export interface Shop {
  id: string;
  ownerId: string;
  name: string;
  location: GeoPoint;
}

export interface MenuItem {
  id: string;
  name: string;
  price: Money;
  available: boolean;
}

export interface OrderLine {
  itemId: string;
  name: string;
  unitPrice: Money;
  quantity: number;
}

export type OrderStatus =
  | 'created'
  | 'validated'
  | 'in-kitchen'
  | 'ready'
  | 'out-for-delivery'
  | 'completed'
  | 'rejected';

export interface Payment {
  id: string;
  customerId: string;
  amount: Money;
  status: 'confirmed' | 'declined';
  reason?: string;
}

export interface Order {
  id: string;
  customerId: string;
  shopId: string;
  fulfillment: FulfillmentType;
  dropoff?: GeoPoint;
  lines: OrderLine[];
  subtotal: Money;
  loyaltyDiscount: Money;
  total: Money;
  paymentId: string;
  status: OrderStatus;
}

export function haversineKm(a: GeoPoint, b: GeoPoint): number {
  const R = 6371;
  const dLat = ((b.lat - a.lat) * Math.PI) / 180;
  const dLng = ((b.lng - a.lng) * Math.PI) / 180;
  const la = (a.lat * Math.PI) / 180;
  const lb = (b.lat * Math.PI) / 180;
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(la) * Math.cos(lb) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

let seq = 0;
export function nextId(prefix: string): string {
  seq += 1;
  return `${prefix}_${seq.toString(36).padStart(4, '0')}`;
}
