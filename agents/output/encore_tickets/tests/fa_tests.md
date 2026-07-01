# FA Tests

## Flow-level (FA verifies)

- [x] opis-eval passes with zero errors
- [x] every external locus (source: true) has sentinel_auth upstream

**Requirement coverage** (each one structurally proved, not just described):

- [x] REQ-1: Customers can reserve seats for an event via mobile app or web — reservation orders are accepted through authenticated intake
    - `customer_auth_token`: CustomerSentinel(customer_auth_token) [fired] → ReservationIntake(customer_auth_token)
    - `seat_reservation_order`: Customer(seat_reservation_order) → ReservationIntake(seat_reservation_order)
- [x] REQ-2: Payment must be confirmed before a seat reservation is finalised — inventory validation requires confirmed payment
    - `accepted_reservation_order`: ReservationIntake(accepted_reservation_order) [fired] → InventoryValidator(accepted_reservation_order)
    - `confirmed_ticket_payment`: TicketPaymentProcessor(confirmed_ticket_payment) [fired] → InventoryValidator(confirmed_ticket_payment)
    - `seat_inventory_update`: InventoryReleaseManager(seat_inventory_update) [fired] → InventoryStore(seat_inventory_update) → InventoryValidator(seat_inventory_update)
    - `venue_routing_decision`: VenueRouter(venue_routing_decision) [fired] → InventoryValidator(venue_routing_decision)
- [x] REQ-3: Seat inventory must never be oversold — concurrent reservations are validated against remaining capacity via inventory state
    - `accepted_reservation_order`: ReservationIntake(accepted_reservation_order) [fired] → InventoryValidator(accepted_reservation_order)
    - `confirmed_ticket_payment`: TicketPaymentProcessor(confirmed_ticket_payment) [fired] → InventoryValidator(confirmed_ticket_payment)
    - `seat_inventory_update`: InventoryReleaseManager(seat_inventory_update) [fired] → InventoryStore(seat_inventory_update) → InventoryValidator(seat_inventory_update)
    - `venue_routing_decision`: VenueRouter(venue_routing_decision) [fired] → InventoryValidator(venue_routing_decision)
- [x] REQ-4: Once payment is confirmed and a seat is reserved, the system issues a digital ticket to the customer
    - `accepted_reservation_order`: ReservationIntake(accepted_reservation_order) [fired] → InventoryValidator(accepted_reservation_order) → TicketIssuer(accepted_reservation_order)
    - `venue_routing_decision`: VenueRouter(venue_routing_decision) [fired] → TicketIssuer(venue_routing_decision)
- [x] REQ-5: Event organisers can update event listings, pricing, and seat capacity independently
    - `event_listing_update`: Organiser(event_listing_update) → EventListingManager(event_listing_update)
    - `organiser_auth_token`: OrganiserSentinel(organiser_auth_token) [fired] → EventListingManager(organiser_auth_token)
- [x] REQ-6: Customers can cancel a reservation and request a refund, releasing the seat back to available inventory
    - `event_listing_update`: Organiser(event_listing_update) → InventoryReleaseManager(event_listing_update)
    - `organiser_auth_token`: OrganiserSentinel(organiser_auth_token) [fired] → InventoryReleaseManager(organiser_auth_token)
- [x] REQ-7: The platform tracks loyalty points for frequent attendees and applies rewards at checkout
    - `confirmed_ticket_payment`: TicketPaymentProcessor(confirmed_ticket_payment) [fired] → LoyaltyProcessor(confirmed_ticket_payment)
    - `customer_auth_token`: LoyaltySentinel(customer_auth_token) [fired] → LoyaltyProcessor(customer_auth_token)
    - `loyalty_reward`: Customer(loyalty_reward) → LoyaltyProcessor(loyalty_reward)
- [x] REQ-8: Customers can request a refund before event start time — refund payments are processed via authenticated payment processor
    - `customer_auth_token`: RefundAuthSentinel(customer_auth_token) [fired] → RefundProcessor(customer_auth_token)
    - `refund_payment`: Customer(refund_payment) → RefundProcessor(refund_payment)

## Gate-level (GA verifies)

- [ ] CustomerSentinel: PDs within flow timing bounds
- [ ] OrganiserSentinel: PDs within flow timing bounds
- [ ] ReservationIntake: PDs within flow timing bounds
- [ ] VenueRouter: PDs within flow timing bounds
- [ ] InventoryValidator: PDs within flow timing bounds
- [ ] TicketPaymentSentinel: PDs within flow timing bounds
- [ ] TicketPaymentProcessor: PDs within flow timing bounds
- [ ] TicketIssuer: PDs within flow timing bounds
- [ ] LoyaltySentinel: PDs within flow timing bounds
- [ ] LoyaltyProcessor: PDs within flow timing bounds
- [ ] EventListingManager: PDs within flow timing bounds
- [ ] CancellationIntake: PDs within flow timing bounds
- [ ] CancellationRouter: PDs within flow timing bounds
- [ ] RefundAuthSentinel: PDs within flow timing bounds
- [ ] RefundProcessor: PDs within flow timing bounds
- [ ] InventoryReleaseManager: PDs within flow timing bounds

## Code-level (CA verifies)

- [ ] CustomerSentinel: implementation accepts correct input types and emits correct output types
- [ ] OrganiserSentinel: implementation accepts correct input types and emits correct output types
- [ ] ReservationIntake: implementation accepts correct input types and emits correct output types
- [ ] VenueRouter: implementation accepts correct input types and emits correct output types
- [ ] InventoryValidator: implementation accepts correct input types and emits correct output types
- [ ] TicketPaymentSentinel: implementation accepts correct input types and emits correct output types
- [ ] TicketPaymentProcessor: implementation accepts correct input types and emits correct output types
- [ ] TicketIssuer: implementation accepts correct input types and emits correct output types
- [ ] LoyaltySentinel: implementation accepts correct input types and emits correct output types
- [ ] LoyaltyProcessor: implementation accepts correct input types and emits correct output types
- [ ] EventListingManager: implementation accepts correct input types and emits correct output types
- [ ] CancellationIntake: implementation accepts correct input types and emits correct output types
- [ ] CancellationRouter: implementation accepts correct input types and emits correct output types
- [ ] RefundAuthSentinel: implementation accepts correct input types and emits correct output types
- [ ] RefundProcessor: implementation accepts correct input types and emits correct output types
- [ ] InventoryReleaseManager: implementation accepts correct input types and emits correct output types