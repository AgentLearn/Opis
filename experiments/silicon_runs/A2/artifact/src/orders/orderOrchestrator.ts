import type {
  Coordinates,
  Order,
  OrderItemRequest,
  OrderLine,
  ShopLocation,
} from '../domain/types.ts';
import type { DeliveryTracking, DriverService } from '../dispatch/driverService.ts';
import type { FranchiseDirectory } from '../franchise/franchiseDirectory.ts';
import type { MenuService } from '../franchise/menuService.ts';
import type { KitchenService } from '../kitchen/kitchenService.ts';
import type { LoyaltyService } from '../loyalty/loyaltyService.ts';
import type { PaymentGateway } from '../payments/paymentGateway.ts';
import type { RouteEstimate } from '../routing/mappingService.ts';
import type { RoutePlanner } from '../routing/routePlanner.ts';

export type CheckoutRequest =
  | {
      customerId: string;
      items: OrderItemRequest[];
      redeemPoints?: number;
      fulfillment: 'pickup';
      locationId: string;
    }
  | {
      customerId: string;
      items: OrderItemRequest[];
      redeemPoints?: number;
      fulfillment: 'delivery';
      deliveryAddress: Coordinates;
    };

export interface CheckoutResult {
  order: Order;
  location: ShopLocation;
  estimatedReadyAt: Date;
  pointsEarned: number;
  deliveryRoute?: RouteEstimate;
  tracking?: DeliveryTracking;
}

export class PaymentDeclinedError extends Error {
  constructor(reason: string) {
    super(`Payment declined: ${reason}`);
    this.name = 'PaymentDeclinedError';
  }
}

/**
 * Facade over the whole order flow. Sequencing is the point: nothing is
 * created or sent to a kitchen until the payment gateway confirms the charge.
 */
export class OrderOrchestrator {
  private readonly orders = new Map<string, Order>();
  private readonly directory: FranchiseDirectory;
  private readonly menus: MenuService;
  private readonly payments: PaymentGateway;
  private readonly loyalty: LoyaltyService;
  private readonly kitchen: KitchenService;
  private readonly routePlanner: RoutePlanner;
  private readonly drivers: DriverService;

  constructor(
    directory: FranchiseDirectory,
    menus: MenuService,
    payments: PaymentGateway,
    loyalty: LoyaltyService,
    kitchen: KitchenService,
    routePlanner: RoutePlanner,
    drivers: DriverService,
  ) {
    this.directory = directory;
    this.menus = menus;
    this.payments = payments;
    this.loyalty = loyalty;
    this.kitchen = kitchen;
    this.routePlanner = routePlanner;
    this.drivers = drivers;
  }

  async checkout(request: CheckoutRequest): Promise<CheckoutResult> {
    // 1. Route the order to the right shop.
    let location: ShopLocation;
    let deliveryRoute: RouteEstimate | undefined;
    if (request.fulfillment === 'delivery') {
      const choice = await this.routePlanner.pickBestLocation(this.directory.all(), request.deliveryAddress);
      location = choice.location;
      deliveryRoute = choice.route;
    } else {
      location = this.directory.get(request.locationId);
    }

    // 2. Validate the basket against that shop's menu and price it.
    const lines = this.buildLines(location.id, request.items);
    const subtotalCents = lines.reduce((sum, l) => sum + l.unitPriceCents * l.quantity, 0);

    // 3. Apply loyalty reward, capped at the subtotal.
    const redeemedPoints = request.redeemPoints ?? 0;
    const loyaltyDiscountCents =
      redeemedPoints > 0
        ? Math.min(this.loyalty.redeem(request.customerId, redeemedPoints), subtotalCents)
        : 0;
    const totalCents = subtotalCents - loyaltyDiscountCents;

    // 4. Confirm payment — the gate in front of everything downstream.
    const payment = await this.payments.charge(request.customerId, totalCents);
    if (payment.status === 'declined') {
      if (redeemedPoints > 0) this.loyalty.refund(request.customerId, redeemedPoints);
      throw new PaymentDeclinedError(payment.reason);
    }

    // 5. Create the order and submit it to the kitchen queue.
    const order: Order = {
      id: `ord_${crypto.randomUUID()}`,
      customerId: request.customerId,
      locationId: location.id,
      fulfillment: request.fulfillment,
      lines,
      subtotalCents,
      loyaltyDiscountCents,
      totalCents,
      status: 'paid',
      paymentId: payment.paymentId,
      placedAt: new Date(),
      deliveryAddress: request.fulfillment === 'delivery' ? request.deliveryAddress : undefined,
    };
    const estimatedReadyAt = this.kitchen.submitOrder(order);
    this.orders.set(order.id, order);

    // 6. Award loyalty points on what the customer actually paid.
    const pointsEarned = this.loyalty.earnFromPurchase(request.customerId, totalCents);

    return { order, location, estimatedReadyAt, pointsEarned, deliveryRoute };
  }

  /** Kitchen marks the order ready; delivery orders get a driver dispatched. */
  async markReady(orderId: string): Promise<DeliveryTracking | undefined> {
    const order = this.getOrder(orderId);
    this.kitchen.markReady(order);
    if (order.fulfillment !== 'delivery' || !order.deliveryAddress) return undefined;
    const location = this.directory.get(order.locationId);
    // Re-route at dispatch time so the driver gets current traffic conditions.
    const route = await this.routePlanner.bestRoute(location.coordinates, order.deliveryAddress);
    return this.drivers.dispatch(order, route);
  }

  completePickup(orderId: string): void {
    const order = this.getOrder(orderId);
    if (order.status !== 'ready') throw new Error(`Order ${orderId} is not ready for pickup`);
    order.status = 'completed';
  }

  getOrder(orderId: string): Order {
    const order = this.orders.get(orderId);
    if (!order) throw new Error(`Unknown order: ${orderId}`);
    return order;
  }

  private buildLines(locationId: string, items: OrderItemRequest[]): OrderLine[] {
    if (items.length === 0) throw new Error('Order must contain at least one item');
    return items.map(({ menuItemId, quantity }) => {
      if (quantity <= 0 || !Number.isInteger(quantity)) {
        throw new Error(`Invalid quantity ${quantity} for item ${menuItemId}`);
      }
      const item = this.menus.getItem(locationId, menuItemId);
      if (!item) throw new Error(`Item ${menuItemId} is not on the menu at ${locationId}`);
      if (!item.available) throw new Error(`${item.name} is currently unavailable at ${locationId}`);
      return { menuItemId, name: item.name, quantity, unitPriceCents: item.priceCents };
    });
  }
}
