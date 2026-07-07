import type { ShopLocation } from '../domain/types.ts';

export class FranchiseDirectory {
  private readonly locations = new Map<string, ShopLocation>();

  register(location: ShopLocation): void {
    this.locations.set(location.id, location);
  }

  get(locationId: string): ShopLocation {
    const location = this.locations.get(locationId);
    if (!location) throw new Error(`Unknown location: ${locationId}`);
    return location;
  }

  all(): ShopLocation[] {
    return [...this.locations.values()];
  }
}
