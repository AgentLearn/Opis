# Silicon Sandwiches — Order Flow

Silicon Sandwiches is a franchise sandwich chain. Customers order via mobile app or kiosk.

## Requirements

- Payment must be confirmed before an order is sent to the kitchen.
- After payment confirmation, the system coordinates order creation, validation, and submission to the kitchen.
- Pickup time is estimated based on the current queue length at the chosen location.
- Delivery routing integrates with ≥ 2 external mapping services (traffic-aware) to compute directions.
- Orders are sent to the correct shop location based on routing logic.
- A driver is dispatched and tracked in real time (optional for pickup orders).
- Franchise owners can update their own menu and pricing independently.
- The system tracks loyalty points per customer and applies rewards at checkout.
