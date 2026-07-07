import type { MenuItem } from '../domain/types.ts';
import type { FranchiseDirectory } from './franchiseDirectory.ts';

/**
 * Each shop keeps its own menu. Mutations are owner-scoped: a franchise owner
 * can only touch menus of locations they own.
 */
export class MenuService {
  private readonly menus = new Map<string, Map<string, MenuItem>>();
  private readonly directory: FranchiseDirectory;

  constructor(directory: FranchiseDirectory) {
    this.directory = directory;
  }

  getMenu(locationId: string): MenuItem[] {
    return [...this.menuFor(locationId).values()];
  }

  getItem(locationId: string, menuItemId: string): MenuItem | undefined {
    return this.menuFor(locationId).get(menuItemId);
  }

  upsertItem(ownerId: string, locationId: string, item: MenuItem): void {
    this.assertOwnership(ownerId, locationId);
    this.menuFor(locationId).set(item.id, { ...item });
  }

  setPrice(ownerId: string, locationId: string, menuItemId: string, priceCents: number): void {
    this.assertOwnership(ownerId, locationId);
    if (priceCents <= 0) throw new Error('Price must be positive');
    this.requireItem(locationId, menuItemId).priceCents = priceCents;
  }

  setAvailability(ownerId: string, locationId: string, menuItemId: string, available: boolean): void {
    this.assertOwnership(ownerId, locationId);
    this.requireItem(locationId, menuItemId).available = available;
  }

  private assertOwnership(ownerId: string, locationId: string): void {
    const location = this.directory.get(locationId);
    if (location.ownerId !== ownerId) {
      throw new Error(`Owner ${ownerId} is not authorized to modify the menu of ${location.name}`);
    }
  }

  private requireItem(locationId: string, menuItemId: string): MenuItem {
    const item = this.menuFor(locationId).get(menuItemId);
    if (!item) throw new Error(`Unknown menu item ${menuItemId} at location ${locationId}`);
    return item;
  }

  private menuFor(locationId: string): Map<string, MenuItem> {
    let menu = this.menus.get(locationId);
    if (!menu) {
      menu = new Map();
      this.menus.set(locationId, menu);
    }
    return menu;
  }
}
