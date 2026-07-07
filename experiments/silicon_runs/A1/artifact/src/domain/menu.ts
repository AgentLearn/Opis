import type { MenuItem, Money, Shop } from './types.ts';

/**
 * Per-shop menus. Every shop owns an independent copy of its menu, so a
 * franchise owner can change items and prices without affecting other
 * locations. All mutations are authorized against the shop's owner.
 */
export class MenuService {
  private readonly shops = new Map<string, Shop>();
  private readonly menus = new Map<string, Map<string, MenuItem>>();

  registerShop(shop: Shop, baseMenu: MenuItem[]): void {
    this.shops.set(shop.id, shop);
    this.menus.set(shop.id, new Map(baseMenu.map((i) => [i.id, { ...i }])));
  }

  getShop(shopId: string): Shop {
    const shop = this.shops.get(shopId);
    if (!shop) throw new Error(`Unknown shop: ${shopId}`);
    return shop;
  }

  listShops(): Shop[] {
    return [...this.shops.values()];
  }

  getMenu(shopId: string): MenuItem[] {
    return [...this.menuFor(shopId).values()];
  }

  getItem(shopId: string, itemId: string): MenuItem | undefined {
    return this.menuFor(shopId).get(itemId);
  }

  /** Add or replace an item on the owner's own menu. */
  upsertItem(ownerId: string, shopId: string, item: MenuItem): void {
    this.authorize(ownerId, shopId);
    this.menuFor(shopId).set(item.id, { ...item });
  }

  setPrice(ownerId: string, shopId: string, itemId: string, price: Money): void {
    this.authorize(ownerId, shopId);
    const item = this.menuFor(shopId).get(itemId);
    if (!item) throw new Error(`Unknown item ${itemId} at ${shopId}`);
    item.price = price;
  }

  setAvailability(ownerId: string, shopId: string, itemId: string, available: boolean): void {
    this.authorize(ownerId, shopId);
    const item = this.menuFor(shopId).get(itemId);
    if (!item) throw new Error(`Unknown item ${itemId} at ${shopId}`);
    item.available = available;
  }

  private menuFor(shopId: string): Map<string, MenuItem> {
    const menu = this.menus.get(shopId);
    if (!menu) throw new Error(`Unknown shop: ${shopId}`);
    return menu;
  }

  private authorize(ownerId: string, shopId: string): void {
    const shop = this.getShop(shopId);
    if (shop.ownerId !== ownerId) {
      throw new Error(`Owner ${ownerId} is not authorized to edit ${shop.name}`);
    }
  }
}
