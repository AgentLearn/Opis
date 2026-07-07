export type MenuItem = {
  id: string;
  name: string;
  priceCents: number;
};

/**
 * The corporate menu is the franchise-wide baseline. Individual shops never
 * mutate it; they layer their own changes on top via FranchiseMenu.
 */
export class CorporateMenu {
  private readonly items = new Map<string, MenuItem>();

  constructor(items: MenuItem[]) {
    for (const item of items) this.items.set(item.id, { ...item });
  }

  get(itemId: string): MenuItem | undefined {
    const item = this.items.get(itemId);
    return item ? { ...item } : undefined;
  }

  list(): MenuItem[] {
    return [...this.items.values()].map((i) => ({ ...i }));
  }
}

/**
 * Each franchise owns one of these. Owners update price/availability/local
 * specials here, independently of corporate and of every other franchise.
 */
export class FranchiseMenu {
  private readonly priceOverrides = new Map<string, number>();
  private readonly localItems = new Map<string, MenuItem>();
  private readonly removed = new Set<string>();

  private readonly corporate: CorporateMenu;

  constructor(corporate: CorporateMenu) {
    this.corporate = corporate;
  }

  setPrice(itemId: string, priceCents: number): void {
    if (!this.corporate.get(itemId) && !this.localItems.has(itemId)) {
      throw new Error(`Unknown menu item: ${itemId}`);
    }
    if (priceCents <= 0) throw new Error("Price must be positive");
    const local = this.localItems.get(itemId);
    if (local) local.priceCents = priceCents;
    else this.priceOverrides.set(itemId, priceCents);
  }

  addLocalItem(item: MenuItem): void {
    this.localItems.set(item.id, { ...item });
    this.removed.delete(item.id);
  }

  removeItem(itemId: string): void {
    this.removed.add(itemId);
    this.localItems.delete(itemId);
    this.priceOverrides.delete(itemId);
  }

  get(itemId: string): MenuItem | undefined {
    if (this.removed.has(itemId)) return undefined;
    const local = this.localItems.get(itemId);
    if (local) return { ...local };
    const base = this.corporate.get(itemId);
    if (!base) return undefined;
    const override = this.priceOverrides.get(itemId);
    return override === undefined ? base : { ...base, priceCents: override };
  }

  list(): MenuItem[] {
    const merged = new Map<string, MenuItem>();
    for (const item of this.corporate.list()) merged.set(item.id, item);
    for (const item of this.localItems.values()) merged.set(item.id, { ...item });
    for (const id of this.removed) merged.delete(id);
    for (const [id, price] of this.priceOverrides) {
      const item = merged.get(id);
      if (item) item.priceCents = price;
    }
    return [...merged.values()];
  }
}
