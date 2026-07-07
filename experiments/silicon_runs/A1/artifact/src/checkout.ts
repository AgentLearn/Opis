import { nextId } from './domain/types.ts';
import type {
  Customer,
  FulfillmentType,
  GeoPoint,
  Order,
  OrderLine,
  Payment,
} from './domain/types.ts';
import type { MenuService } from './domain/menu.ts';
import { LoyaltyService } from './domain/loyalty.ts';
import type { PaymentGateway } from './services/payment.ts';
import type { KitchenService } from './services/kitchen.ts';
import type { ShopRouter, ShopChoice } from './services/shopRouter.ts';
import type { DriverDispatcher, DeliveryTracking } from './services/dispatch.ts';

export interface CheckoutRequest {
  customer: Customer;
  items: { itemId: string; quantity: number }[];
  fulfillment: FulfillmentType;
  /** Required for pickup: the shop the customer chose. */
  pickupShopId?: string;
  /** Required for delivery: where the food goes. */
  dropoff?: GeoPoint;
  redeemLoyaltyPoints?: boolean;
}

export interface Receipt {
  order: Order;
  payment: Payment;
  loyalty: { discountApplied: number; pointsSpent: number; pointsEarned: number; balance: number };
  /** Minutes until the order is ready for pickup at the shop. */
  pickupEtaMinutes: number;
  /** Live delivery tracking; only present for delivery orders. */
  tracking?: DeliveryTracking;
}

export class PaymentDeclinedError extends Error {
  readonly payment: Payment;
  constructor(payment: Payment) {
    super(`Payment declined: ${payment.reason ?? 'unknown reason'}`);
    this.payment = payment;
  }
}

/**
 * Coordinates a checkout end to end:
 *
 *   1. route the order to a shop (customer's choice for pickup; fastest
 *      traffic-aware ETA for delivery)
 *   2. price the cart from that shop's menu and apply loyalty rewards
 *   3. charge the customer — nothing reaches the kitchen unless this
 *      payment is confirmed
 *   4. create + validate the order, submit it to the shop's kitchen
 *   5. estimate pickup time from the kitchen queue
 *   6. earn loyalty points; for delivery, dispatch a driver with live
 *      tracking along the traffic-aware route
 */
export class CheckoutOrchestrator {
  private readonly menus: MenuService;
  private readonly router: ShopRouter;
  private readonly payments: PaymentGateway;
  private readonly kitchen: KitchenService;
  private readonly loyalty: LoyaltyService;
  private readonly dispatcher: DriverDispatcher;

  constructor(deps: {
    menus: MenuService;
    router: ShopRouter;
    payments: PaymentGateway;
    kitchen: KitchenService;
    loyalty: LoyaltyService;
    dispatcher: DriverDispatcher;
  }) {
    this.menus = deps.menus;
    this.router = deps.router;
    this.payments = deps.payments;
    this.kitchen = deps.kitchen;
    this.loyalty = deps.loyalty;
    this.dispatcher = deps.dispatcher;
  }

  async placeOrder(request: CheckoutRequest): Promise<Receipt> {
    const choice = await this.routeToShop(request);
    const lines = this.priceCart(choice.shop.id, request.items);
    const subtotal = lines.reduce((sum, l) => sum + l.unitPrice * l.quantity, 0);

    const { discount, pointsSpent } = request.redeemLoyaltyPoints
      ? this.loyalty.redeem(request.customer.id, subtotal)
      : { discount: 0, pointsSpent: 0 };
    const total = subtotal - discount;

    // Hard rule: payment is confirmed before any order exists for the kitchen.
    const payment = await this.payments.charge(request.customer.id, total);
    if (payment.status !== 'confirmed') {
      // Give redeemed points back — the customer paid nothing.
      if (pointsSpent > 0) this.loyalty.earn(request.customer.id, pointsSpent * 100);
      throw new PaymentDeclinedError(payment);
    }

    const order: Order = {
      id: nextId('ord'),
      customerId: request.customer.id,
      shopId: choice.shop.id,
      fulfillment: request.fulfillment,
      dropoff: request.dropoff,
      lines,
      subtotal,
      loyaltyDiscount: discount,
      total,
      paymentId: payment.id,
      status: 'created',
    };
    this.validate(order);

    const pickupEtaMinutes = this.kitchen.estimatePickupMinutes(choice.shop.id);
    this.kitchen.submit(order, payment);

    const pointsEarned = this.loyalty.earn(request.customer.id, total);

    let tracking: DeliveryTracking | undefined;
    if (request.fulfillment === 'delivery') {
      tracking = this.dispatcher.dispatch(order, choice.shop.location, choice.route!);
    }

    return {
      order,
      payment,
      loyalty: {
        discountApplied: discount,
        pointsSpent,
        pointsEarned,
        balance: this.loyalty.balance(request.customer.id),
      },
      pickupEtaMinutes,
      tracking,
    };
  }

  private async routeToShop(request: CheckoutRequest): Promise<ShopChoice> {
    if (request.fulfillment === 'pickup') {
      if (!request.pickupShopId) throw new Error('Pickup orders need a pickupShopId');
      return this.router.forPickup(request.pickupShopId);
    }
    const dropoff = request.dropoff ?? request.customer.address;
    if (!dropoff) throw new Error('Delivery orders need a dropoff address');
    request.dropoff = dropoff;
    return this.router.forDelivery(dropoff, request.items.map((i) => i.itemId));
  }

  private priceCart(shopId: string, items: { itemId: string; quantity: number }[]): OrderLine[] {
    if (items.length === 0) throw new Error('Cart is empty');
    return items.map(({ itemId, quantity }) => {
      const item = this.menus.getItem(shopId, itemId);
      if (!item || !item.available) {
        throw new Error(`Item ${itemId} is not available at ${shopId}`);
      }
      if (quantity < 1) throw new Error(`Invalid quantity for ${itemId}`);
      return { itemId, name: item.name, unitPrice: item.price, quantity };
    });
  }

  private validate(order: Order): void {
    if (order.lines.length === 0) throw new Error('Order has no lines');
    if (order.total < 0) throw new Error('Order total is negative');
    if (order.fulfillment === 'delivery' && !order.dropoff) {
      throw new Error('Delivery order is missing a dropoff');
    }
    order.status = 'validated';
  }
}
