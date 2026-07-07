import { nextId } from "../domain/types.ts";
import type { Customer, FulfilmentType, Order, OrderLine, PricedLine } from "../domain/types.ts";
import type { PaymentGateway } from "../payments/payments.ts";
import type { LoyaltyProgram } from "../loyalty/loyalty.ts";
import type { LocationRouter } from "../routing/locationRouter.ts";
import type { RoutePlanner, RouteEstimate } from "../routing/mapping.ts";
import type { Shop } from "../shops/shop.ts";
import { estimatePickupMinutes } from "../shops/shop.ts";
import type { DeliveryTracking, DriverDispatcher } from "../delivery/dispatch.ts";

export type CheckoutRequest = {
  customer: Customer;
  lines: OrderLine[];
  fulfilment: FulfilmentType;
  /** Required for pickup: the shop the customer chose. Ignored for delivery. */
  pickupShopId?: string;
  /** Loyalty points the customer wants to redeem (whole 100-point blocks). */
  redeemPoints?: number;
};

export type CheckoutResult =
  | {
      accepted: true;
      order: Order;
      shop: Shop;
      loyalty: { pointsUsed: number; discountCents: number; pointsEarned: number; balance: number };
      pickupEstimateMinutes?: number;
      delivery?: { route: RouteEstimate; tracking: DeliveryTracking };
    }
  | { accepted: false; reason: string };

/**
 * Facade over the whole order flow. The invariant lives here: nothing reaches
 * a kitchen until the payment gateway has confirmed the charge.
 */
export class OrderService {
  private readonly shops: Shop[];
  private readonly gateway: PaymentGateway;
  private readonly loyalty: LoyaltyProgram;
  private readonly locationRouter: LocationRouter;
  private readonly routePlanner: RoutePlanner;
  private readonly dispatcher: DriverDispatcher;

  constructor(
    shops: Shop[],
    gateway: PaymentGateway,
    loyalty: LoyaltyProgram,
    locationRouter: LocationRouter,
    routePlanner: RoutePlanner,
    dispatcher: DriverDispatcher,
  ) {
    this.shops = shops;
    this.gateway = gateway;
    this.loyalty = loyalty;
    this.locationRouter = locationRouter;
    this.routePlanner = routePlanner;
    this.dispatcher = dispatcher;
  }

  async checkout(req: CheckoutRequest): Promise<CheckoutResult> {
    // 1. Pick the shop: customer's choice for pickup, routing logic for delivery.
    let shop: Shop;
    let deliveryRoute: RouteEstimate | undefined;
    if (req.fulfilment === "pickup") {
      const chosen = this.shops.find((s) => s.id === req.pickupShopId);
      if (!chosen) return { accepted: false, reason: `Unknown pickup shop: ${req.pickupShopId}` };
      shop = chosen;
    } else {
      const choice = await this.locationRouter.routeToShop(req.customer.location, this.shops);
      shop = choice.shop;
      deliveryRoute = choice.route;
    }

    // 2. Price the cart against this franchise's menu.
    const priced = this.price(req.lines, shop);
    if ("reason" in priced) return { accepted: false, reason: priced.reason };
    const { pricedLines, subtotalCents } = priced;

    // 3. Apply loyalty rewards, then charge. Points are refunded on decline.
    const { pointsUsed, discountCents } = this.loyalty.redeem(
      req.customer.id,
      req.redeemPoints ?? 0,
      subtotalCents,
    );
    const totalCents = subtotalCents - discountCents;
    const payment = await this.gateway.charge(req.customer.id, totalCents);
    if (payment.status !== "confirmed") {
      if (pointsUsed > 0) this.loyalty.earn(req.customer.id, pointsUsed * 100);
      return { accepted: false, reason: `Payment not confirmed: ${payment.reason}` };
    }

    // 4. Payment confirmed — coordinate creation, validation, kitchen submission.
    const queueAhead = shop.kitchen.length;
    const order = this.createOrder(req, shop, pricedLines, subtotalCents, discountCents, totalCents, payment.transactionId);
    this.validate(order, shop);
    order.status = "submitted";
    shop.kitchen.submit(order);

    // 5. Earn points on what was actually paid.
    const pointsEarned = this.loyalty.earn(req.customer.id, totalCents);

    // 6. Fulfilment specifics: pickup ETA from queue depth, or driver dispatch.
    if (req.fulfilment === "pickup") {
      return {
        accepted: true,
        order,
        shop,
        loyalty: { pointsUsed, discountCents, pointsEarned, balance: this.loyalty.pointsOf(req.customer.id) },
        pickupEstimateMinutes: estimatePickupMinutes(queueAhead),
      };
    }

    const route = deliveryRoute ?? (await this.routePlanner.bestRoute(shop.location, req.customer.location));
    const tracking = this.dispatcher.dispatch(order, route);
    return {
      accepted: true,
      order,
      shop,
      loyalty: { pointsUsed, discountCents, pointsEarned, balance: this.loyalty.pointsOf(req.customer.id) },
      delivery: { route, tracking },
    };
  }

  private price(
    lines: OrderLine[],
    shop: Shop,
  ): { pricedLines: PricedLine[]; subtotalCents: number } | { reason: string } {
    if (lines.length === 0) return { reason: "Cart is empty" };
    const pricedLines: PricedLine[] = [];
    for (const line of lines) {
      if (!Number.isInteger(line.quantity) || line.quantity <= 0) {
        return { reason: `Invalid quantity for ${line.itemId}` };
      }
      const item = shop.menu.get(line.itemId);
      if (!item) return { reason: `Item not on ${shop.name} menu: ${line.itemId}` };
      pricedLines.push({
        ...line,
        name: item.name,
        unitPriceCents: item.priceCents,
        lineTotalCents: item.priceCents * line.quantity,
      });
    }
    const subtotalCents = pricedLines.reduce((sum, l) => sum + l.lineTotalCents, 0);
    return { pricedLines, subtotalCents };
  }

  private createOrder(
    req: CheckoutRequest,
    shop: Shop,
    lines: PricedLine[],
    subtotalCents: number,
    discountCents: number,
    totalCents: number,
    paymentTransactionId: string,
  ): Order {
    return {
      id: nextId("order"),
      customerId: req.customer.id,
      shopId: shop.id,
      fulfilment: req.fulfilment,
      lines,
      subtotalCents,
      discountCents,
      totalCents,
      paymentTransactionId,
      status: "created",
      createdAt: new Date(),
    };
  }

  private validate(order: Order, shop: Shop): void {
    // Defensive re-checks before the kitchen sees the ticket.
    if (order.lines.length === 0) throw new Error("Order has no lines");
    if (order.totalCents < 0) throw new Error("Negative total");
    if (!order.paymentTransactionId) throw new Error("Order not paid");
    if (order.shopId !== shop.id) throw new Error("Order routed to wrong shop");
    order.status = "validated";
  }
}
