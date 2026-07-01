# FA Tests

## Flow-level (FA verifies)

- [x] opis-eval passes with zero errors
- [x] every external locus (source: true) has sentinel_auth upstream

**Requirement coverage** (each one structurally proved, not just described):

- [x] REQ-1: Payment must be confirmed before an order is sent to the kitchen — PaymentProcessor confirms payment, which is required by both OrderIntake and OrderValidator before the order proceeds.
    - `auth_token`: AuthCustomer(auth_token) [fired] → PaymentProcessor(auth_token)
    - `sandwich_payment`: CustomerApp(sandwich_payment) → PaymentProcessor(sandwich_payment)
- [x] REQ-2: After payment confirmation, the system coordinates order creation, validation, and submission to the kitchen via OrderIntake, OrderValidator, and ProducerSubmitter.
    - `routing_decision`: DeliveryRouterA(routing_decision) [fired] → ProducerSubmitter(routing_decision)
    - `sandwich_order_accepted`: OrderIntake(sandwich_order_accepted) [fired] → OrderValidator(sandwich_order_accepted) → ProducerSubmitter(sandwich_order_accepted)
- [x] REQ-3: Pickup time is estimated based on the current queue length at the chosen location via PickupEstimator.
    - `sandwich_order_accepted`: OrderIntake(sandwich_order_accepted) [fired] → OrderValidator(sandwich_order_accepted) → PickupEstimator(sandwich_order_accepted)
    - `shop_location`: MappingServiceA(shop_location) → PickupEstimator(shop_location)
- [x] REQ-4: Delivery routing integrates with two external mapping services (DeliveryRouterA and DeliveryRouterB) to compute traffic-aware directions.
    - `sandwich_order`: CustomerApp(sandwich_order) → DeliveryRouterB(sandwich_order)
    - `shop_location`: MappingServiceB(shop_location) → DeliveryRouterB(shop_location)
- [x] REQ-5: Orders are sent to the correct shop location based on routing logic — ProducerSubmitter uses the routing_decision to submit the order to the right kitchen.
    - `routing_decision`: DeliveryRouterA(routing_decision) [fired] → ProducerSubmitter(routing_decision)
    - `sandwich_order_accepted`: OrderIntake(sandwich_order_accepted) [fired] → OrderValidator(sandwich_order_accepted) → ProducerSubmitter(sandwich_order_accepted)
- [x] REQ-6: A driver is dispatched and tracked in real time via DriverDispatcher (optional for pickup orders).
    - `driver_tracking_update`: DriverApp(driver_tracking_update) → DriverDispatcher(driver_tracking_update)
    - `routing_decision`: DeliveryRouterB(routing_decision) [fired] → DriverDispatcher(routing_decision)
    - `sandwich_order_accepted`: OrderIntake(sandwich_order_accepted) [fired] → OrderValidator(sandwich_order_accepted) → DriverDispatcher(sandwich_order_accepted)
- [x] REQ-7: Franchise owners can update their own menu and pricing independently via MenuManager, authenticated by AuthFranchiseOwner.
    - `auth_token`: AuthFranchiseOwner(auth_token) [fired] → MenuManager(auth_token)
    - `franchise_menu_update`: FranchiseOwner(franchise_menu_update) → MenuManager(franchise_menu_update)
- [x] REQ-8: The system tracks loyalty points per customer and applies rewards at checkout via LoyaltyProcessor.
    - `auth_token`: AuthLoyalty(auth_token) [fired] → LoyaltyProcessor(auth_token)
    - `loyalty_reward`: CustomerApp(loyalty_reward) → LoyaltyProcessor(loyalty_reward)
    - `sandwich_payment_confirmed`: PaymentProcessor(sandwich_payment_confirmed) [fired] → LoyaltyProcessor(sandwich_payment_confirmed)

## Gate-level (GA verifies)

- [ ] AuthCustomer: PDs within flow timing bounds
- [ ] AuthFranchiseOwner: PDs within flow timing bounds
- [ ] AuthLoyalty: PDs within flow timing bounds
- [ ] PaymentProcessor: PDs within flow timing bounds
- [ ] OrderIntake: PDs within flow timing bounds
- [ ] DeliveryRouterA: PDs within flow timing bounds
- [ ] DeliveryRouterB: PDs within flow timing bounds
- [ ] OrderValidator: PDs within flow timing bounds
- [ ] AuthOrderValidator: PDs within flow timing bounds
- [ ] PickupEstimator: PDs within flow timing bounds
- [ ] ProducerSubmitter: PDs within flow timing bounds
- [ ] AuthProducerSubmitter: PDs within flow timing bounds
- [ ] DriverDispatcher: PDs within flow timing bounds
- [ ] AuthDriverDispatcher: PDs within flow timing bounds
- [ ] MenuManager: PDs within flow timing bounds
- [ ] LoyaltyProcessor: PDs within flow timing bounds

## Code-level (CA verifies)

- [ ] AuthCustomer: implementation accepts correct input types and emits correct output types
- [ ] AuthFranchiseOwner: implementation accepts correct input types and emits correct output types
- [ ] AuthLoyalty: implementation accepts correct input types and emits correct output types
- [ ] PaymentProcessor: implementation accepts correct input types and emits correct output types
- [ ] OrderIntake: implementation accepts correct input types and emits correct output types
- [ ] DeliveryRouterA: implementation accepts correct input types and emits correct output types
- [ ] DeliveryRouterB: implementation accepts correct input types and emits correct output types
- [ ] OrderValidator: implementation accepts correct input types and emits correct output types
- [ ] AuthOrderValidator: implementation accepts correct input types and emits correct output types
- [ ] PickupEstimator: implementation accepts correct input types and emits correct output types
- [ ] ProducerSubmitter: implementation accepts correct input types and emits correct output types
- [ ] AuthProducerSubmitter: implementation accepts correct input types and emits correct output types
- [ ] DriverDispatcher: implementation accepts correct input types and emits correct output types
- [ ] AuthDriverDispatcher: implementation accepts correct input types and emits correct output types
- [ ] MenuManager: implementation accepts correct input types and emits correct output types
- [ ] LoyaltyProcessor: implementation accepts correct input types and emits correct output types