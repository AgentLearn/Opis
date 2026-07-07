import { DriverService } from '../src/dispatch/driverService.ts';
import { FranchiseDirectory } from '../src/franchise/franchiseDirectory.ts';
import { MenuService } from '../src/franchise/menuService.ts';
import { KitchenService } from '../src/kitchen/kitchenService.ts';
import { LoyaltyService } from '../src/loyalty/loyaltyService.ts';
import { OrderOrchestrator } from '../src/orders/orderOrchestrator.ts';
import { MockCardGateway } from '../src/payments/paymentGateway.ts';
import { AtlasRoutingClient } from '../src/routing/providers/atlasRouting.ts';
import { SpeedyMapsClient } from '../src/routing/providers/speedyMaps.ts';
import { RoutePlanner } from '../src/routing/routePlanner.ts';

export const NO_TRAFFIC = () => 1;

export function buildSystem() {
  const directory = new FranchiseDirectory();
  const menus = new MenuService(directory);
  const payments = new MockCardGateway();
  const loyalty = new LoyaltyService();
  const kitchen = new KitchenService();
  const planner = new RoutePlanner([new SpeedyMapsClient(NO_TRAFFIC), new AtlasRoutingClient(NO_TRAFFIC)]);
  const drivers = new DriverService([{ id: 'drv-1', name: 'Test Driver' }], 1);
  const orchestrator = new OrderOrchestrator(directory, menus, payments, loyalty, kitchen, planner, drivers);

  directory.register({ id: 'downtown', name: 'Downtown', ownerId: 'owner-a', coordinates: { lat: 37.7897, lng: -122.4011 } });
  directory.register({ id: 'mission', name: 'Mission', ownerId: 'owner-b', coordinates: { lat: 37.7599, lng: -122.4148 } });

  for (const [locationId, ownerId] of [['downtown', 'owner-a'], ['mission', 'owner-b']] as const) {
    menus.upsertItem(ownerId, locationId, { id: 'blt', name: 'BLT', priceCents: 1000, available: true });
    menus.upsertItem(ownerId, locationId, { id: 'soda', name: 'Soda', priceCents: 300, available: true });
  }

  return { directory, menus, payments, loyalty, kitchen, planner, drivers, orchestrator };
}
