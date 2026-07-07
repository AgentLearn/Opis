import type { Coordinates } from "../domain/types.ts";
import type { RouteEstimate, RoutePlanner } from "./mapping.ts";
import type { Shop } from "../shops/shop.ts";

export type ShopChoice = { shop: Shop; route: RouteEstimate };

/**
 * Decides which shop an order goes to: the one with the shortest
 * traffic-aware drive time from the customer.
 */
export class LocationRouter {
  private readonly planner: RoutePlanner;

  constructor(planner: RoutePlanner) {
    this.planner = planner;
  }

  async routeToShop(customer: Coordinates, shops: Shop[]): Promise<ShopChoice> {
    if (shops.length === 0) throw new Error("No shops available");
    const choices = await Promise.all(
      shops.map(async (shop) => ({ shop, route: await this.planner.bestRoute(shop.location, customer) })),
    );
    return choices.reduce((best, c) => (c.route.minutes < best.route.minutes ? c : best));
  }
}
