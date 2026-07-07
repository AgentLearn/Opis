import type { GeoPoint, Shop } from '../domain/types.ts';
import type { MenuService } from '../domain/menu.ts';
import type { RoutePlanner, RouteResult } from './mapping.ts';

export interface ShopChoice {
  shop: Shop;
  /** Traffic-aware route shop → dropoff. Only present for delivery. */
  route?: RouteResult;
}

/**
 * Decides which shop location an order goes to.
 * Pickup: the customer's chosen shop. Delivery: the shop with the fastest
 * traffic-aware ETA to the dropoff that can actually make every item.
 */
export class ShopRouter {
  private readonly menus: MenuService;
  private readonly planner: RoutePlanner;

  constructor(menus: MenuService, planner: RoutePlanner) {
    this.menus = menus;
    this.planner = planner;
  }

  forPickup(shopId: string): ShopChoice {
    return { shop: this.menus.getShop(shopId) };
  }

  async forDelivery(dropoff: GeoPoint, itemIds: string[]): Promise<ShopChoice> {
    const candidates = this.menus
      .listShops()
      .filter((shop) => itemIds.every((id) => this.menus.getItem(shop.id, id)?.available));
    if (candidates.length === 0) {
      throw new Error('No shop can fulfill every item in this order');
    }
    const routed = await Promise.all(
      candidates.map(async (shop) => ({
        shop,
        route: await this.planner.bestRoute(shop.location, dropoff),
      })),
    );
    return routed.reduce((best, c) =>
      c.route.durationMinutes < best.route.durationMinutes ? c : best,
    );
  }
}
