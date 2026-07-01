# Ripple Rides — On-Demand Ride Hailing

Ripple Rides is an on-demand ride-hailing platform connecting riders with nearby available drivers in real time.

## Requirements

- Riders request a ride via mobile app, specifying pickup and destination locations.
- Each ride request is matched against multiple currently available nearby drivers at once, not just the first driver found — matching must weigh proximity and availability across several candidates simultaneously.
- If no matched driver accepts within a short window, the platform automatically reassigns the request to the next best available driver.
- During periods of high demand, the platform applies surge pricing and rate-limits new ride requests per zone so the driver pool isn't overwhelmed.
- Payment must be confirmed before a ride can be marked complete.
- If a driver repeatedly fails to accept assigned rides within a short window, the platform temporarily suspends new assignments to that driver.
- Once a ride is completed, the platform records a rating for both rider and driver.
- Riders can cancel a requested ride before a driver arrives; repeated late cancellations trigger a cooldown restricting that rider from requesting new rides for a period.
