import type { Customer, FranchiseOwner, MenuItem, Shop } from './domain/types.ts';
import type { Driver } from './services/dispatch.ts';
import { MenuService } from './domain/menu.ts';
import { LoyaltyService } from './domain/loyalty.ts';
import { MockPaymentGateway } from './services/payment.ts';
import { GoogleMapsAdapter, OsrmAdapter, RoutePlanner, type TrafficFeed, freeFlow } from './services/mapping.ts';
import { KitchenService } from './services/kitchen.ts';
import { ShopRouter } from './services/shopRouter.ts';
import { DriverDispatcher } from './services/dispatch.ts';
import { CheckoutOrchestrator } from './checkout.ts';

export const owners: FranchiseOwner[] = [
  { id: 'own_ada', name: 'Ada' },
  { id: 'own_bob', name: 'Bob' },
];

export const shops: Shop[] = [
  { id: 'shop_soma', ownerId: 'own_ada', name: 'SoMa', location: { lat: 37.778, lng: -122.405 } },
  { id: 'shop_mission', ownerId: 'own_bob', name: 'Mission', location: { lat: 37.76, lng: -122.419 } },
];

export const baseMenu: MenuItem[] = [
  { id: 'blt', name: 'Bacon Lettuce Tomato', price: 1150, available: true },
  { id: 'veggie', name: 'Roasted Veggie', price: 995, available: true },
  { id: 'turkey', name: 'Turkey Club', price: 1250, available: true },
  { id: 'soda', name: 'Fountain Soda', price: 295, available: true },
];

export const customers: Record<string, Customer> = {
  nia: { id: 'cus_nia', name: 'Nia', address: { lat: 37.77, lng: -122.41 } },
  raj: { id: 'cus_raj', name: 'Raj', address: { lat: 37.755, lng: -122.423 } },
};

export interface System {
  menus: MenuService;
  loyalty: LoyaltyService;
  payments: MockPaymentGateway;
  kitchen: KitchenService;
  planner: RoutePlanner;
  dispatcher: DriverDispatcher;
  drivers: Driver[];
  checkout: CheckoutOrchestrator;
}

/** Wire up a full system with two shops, two mapping providers, two drivers. */
export function buildSystem(traffic: TrafficFeed = freeFlow): System {
  const menus = new MenuService();
  for (const shop of shops) menus.registerShop(shop, baseMenu);

  const planner = new RoutePlanner([new GoogleMapsAdapter(traffic), new OsrmAdapter(traffic)]);
  const drivers: Driver[] = [
    { id: 'drv_1', name: 'Kim', location: { lat: 37.775, lng: -122.41 }, available: true },
    { id: 'drv_2', name: 'Leo', location: { lat: 37.758, lng: -122.42 }, available: true },
  ];

  const loyalty = new LoyaltyService();
  const payments = new MockPaymentGateway();
  const kitchen = new KitchenService();
  const dispatcher = new DriverDispatcher(drivers);
  const router = new ShopRouter(menus, planner);
  const checkout = new CheckoutOrchestrator({ menus, router, payments, kitchen, loyalty, dispatcher });

  return { menus, loyalty, payments, kitchen, planner, dispatcher, drivers, checkout };
}
