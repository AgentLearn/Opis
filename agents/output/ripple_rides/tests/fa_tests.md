# FA Tests

## Flow-level (FA verifies)

- [x] opis-eval passes with zero errors
- [x] every external locus (source: true) has sentinel_auth upstream

**Requirement coverage** (each one structurally proved, not just described):

- [x] REQ-1: Riders request a ride via mobile app specifying pickup and destination locations; the request is validated and accepted or rejected.
    - `auth_token`: RiderAuthSentinel(auth_token) [fired] → RideRequestIntake(auth_token)
    - `ride_request`: RiderApp(ride_request) → SurgeRateLimiter(ride_request) → RideRequestIntake(ride_request)
- [x] REQ-2: Ride requests are rate-limited per zone during high demand using surge zone regulation; excess requests are suppressed.
    - `ride_request`: RiderApp(ride_request) → SurgeRateLimiter(ride_request)
    - `zone_routing_decision`: ZoneRouter(zone_routing_decision) [fired] → SurgeRateLimiter(zone_routing_decision)
- [x] REQ-3: During high demand, surge pricing is applied and a zone inventory update is propagated for use in ride validation.
    - `auth_token`: RiderAuthSentinel(auth_token) [fired] → SurgePricingManager(auth_token)
    - `surge_pricing_update`: ZoneDemandMonitor(surge_pricing_update) → SurgePricingManager(surge_pricing_update)
- [x] REQ-4: Each ride request is matched against multiple nearby drivers simultaneously using threshold-based multi-driver dispatch.
    - `driver_tracking_update`: DriverApp(driver_tracking_update) → MultiDriverDispatcher(driver_tracking_update)
    - `ride_booking`: RideRequestIntake(ride_booking) [fired] → RideBookingValidator(ride_booking) → MultiDriverDispatcher(ride_booking)
    - `zone_routing_decision`: ZoneRouter(zone_routing_decision) [fired] → MultiDriverDispatcher(zone_routing_decision)
- [x] REQ-5: If no driver accepts within the dispatch window, the platform automatically reassigns by recycling the ride request for a new dispatch attempt.
    - `dispatch_event`: MultiDriverDispatcher(dispatch_event) [fired] → ReassignmentThrottle(dispatch_event)
- [x] REQ-6: If a driver repeatedly fails to accept assigned rides within the window, the platform temporarily suspends new assignments to that driver.
    - `driver_no_accept_event`: DriverApp(driver_no_accept_event) → DriverNoAcceptSuspension(driver_no_accept_event)
- [x] REQ-7: Payment must be confirmed before a ride can be marked complete; the ride is finalized only after payment confirmation.
    - `ride_booking`: RideRequestIntake(ride_booking) [fired] → RideBookingValidator(ride_booking) → RideCompletionFinalizer(ride_booking)
    - `ride_payment_confirmed`: RidePaymentProcessor(ride_payment_confirmed) [fired] → RideCompletionFinalizer(ride_payment_confirmed)
- [x] REQ-8: Once a ride is completed, the platform records a rating for both rider and driver.
    - `auth_token`: RiderAuthSentinel(auth_token) [fired] → RatingRecorder(auth_token)
    - `rating_event`: RatingService(rating_event) → RatingRecorder(rating_event)
- [x] REQ-9: Riders can cancel a ride before a driver arrives; repeated late cancellations trigger a cooldown restricting the rider from new requests.
    - `cancellation_event`: RiderApp(cancellation_event) → LateCancellationCooldown(cancellation_event)
- [x] REQ-10: Cancellation events are recorded in the audit log for compliance and pattern detection.
    - `auth_token`: RiderAuthSentinel(auth_token) [fired] → CancellationRecorder(auth_token)
    - `cancellation_event`: RiderApp(cancellation_event) → CancellationRecorder(cancellation_event)
- [x] REQ-11: Arrival estimates are computed and sent to the rider once a driver is dispatched.
    - `driver_location`: DriverApp(driver_location) → ArrivalEstimator(driver_location)
    - `ride_booking`: RideRequestIntake(ride_booking) [fired] → RideBookingValidator(ride_booking) → ArrivalEstimator(ride_booking)
- [x] REQ-12: Ride completion events are recorded in the audit log.
    - `auth_token`: RiderAuthSentinel(auth_token) [fired] → RideCompletionRecorder(auth_token)
    - `ride_complete_event`: RideCompletionFinalizer(ride_complete_event) [fired] → RideCompletionRecorder(ride_complete_event)

## Gate-level (GA verifies)

- [ ] RiderAuthSentinel: PDs within flow timing bounds
- [ ] DriverAuthSentinel: PDs within flow timing bounds
- [ ] RideRequestIntake: PDs within flow timing bounds
- [ ] ZoneRouter: PDs within flow timing bounds
- [ ] SurgeRateLimiter: PDs within flow timing bounds
- [ ] SurgePricingManager: PDs within flow timing bounds
- [ ] RideBookingValidator: PDs within flow timing bounds
- [ ] ArrivalEstimator: PDs within flow timing bounds
- [ ] MultiDriverDispatcher: PDs within flow timing bounds
- [ ] ReassignmentThrottle: PDs within flow timing bounds
- [ ] DriverNoAcceptSuspension: PDs within flow timing bounds
- [ ] RidePaymentProcessor: PDs within flow timing bounds
- [ ] RideCompletionFinalizer: PDs within flow timing bounds
- [ ] RideCompletionRecorder: PDs within flow timing bounds
- [ ] RatingRecorder: PDs within flow timing bounds
- [ ] CancellationRecorder: PDs within flow timing bounds
- [ ] LateCancellationCooldown: PDs within flow timing bounds

## Code-level (CA verifies)

- [ ] RiderAuthSentinel: implementation accepts correct input types and emits correct output types
- [ ] DriverAuthSentinel: implementation accepts correct input types and emits correct output types
- [ ] RideRequestIntake: implementation accepts correct input types and emits correct output types
- [ ] ZoneRouter: implementation accepts correct input types and emits correct output types
- [ ] SurgeRateLimiter: implementation accepts correct input types and emits correct output types
- [ ] SurgePricingManager: implementation accepts correct input types and emits correct output types
- [ ] RideBookingValidator: implementation accepts correct input types and emits correct output types
- [ ] ArrivalEstimator: implementation accepts correct input types and emits correct output types
- [ ] MultiDriverDispatcher: implementation accepts correct input types and emits correct output types
- [ ] ReassignmentThrottle: implementation accepts correct input types and emits correct output types
- [ ] DriverNoAcceptSuspension: implementation accepts correct input types and emits correct output types
- [ ] RidePaymentProcessor: implementation accepts correct input types and emits correct output types
- [ ] RideCompletionFinalizer: implementation accepts correct input types and emits correct output types
- [ ] RideCompletionRecorder: implementation accepts correct input types and emits correct output types
- [ ] RatingRecorder: implementation accepts correct input types and emits correct output types
- [ ] CancellationRecorder: implementation accepts correct input types and emits correct output types
- [ ] LateCancellationCooldown: implementation accepts correct input types and emits correct output types