# DockYard Fulfillment — Warehouse Order Fulfillment

DockYard runs a high-volume distribution warehouse, turning incoming orders into picked,
packed, and shipped parcels across a floor of pickers, packing stations, and loading docks.

## Requirements

- Incoming orders are batched into pick waves, scheduled by ship-by deadline and priority.
- Each item in a wave is assigned to a picker; a given bin location can be assigned to only one picker at a time to avoid two pickers colliding at the same shelf.
- Picked items for an order are consolidated at a packing station; an order can ship only once all of its items have been packed.
- Items that fail a quality check at packing are sent back to be re-picked from an alternate bin.
- If a loading dock door is not free within a set window, the shipment is rerouted to the next available dock.
- A handheld scanner that stops responding mid-wave marks its picker unavailable and reassigns that picker's open tasks.
- If an order is cancelled mid-fulfillment, any items already picked for it are restocked and its packing slot is released.
- Throughput per zone is rate-limited so no single zone's conveyor is overwhelmed.
