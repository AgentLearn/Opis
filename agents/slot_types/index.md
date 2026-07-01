# Slot Types

Computing-level type vocabulary for gate slots. Domain archetypes extend these.
A gate whose input slot is `order` accepts any domain term whose archetype resolves to `order`.

| type               | extends          | description                                          |
|--------------------|------------------|------------------------------------------------------|
| order              | —                | a request to process or fulfill something            |
| accepted_order     | order            | an order that passed validation                      |
| rejected_order     | order            | an order that failed validation                      |
| payment            | —                | a financial transaction request                      |
| payment_confirmed  | payment          | a payment that was authorised                        |
| payment_failed     | payment          | a payment that was declined                          |
| auth_request       | —                | a request to authenticate or authorise an actor      |
| auth_token         | —                | a credential granting access to a protected gate     |
| notification       | —                | an outbound message to an actor                      |
| query              | —                | a request for information (pull interaction)         |
| query_response     | —                | the response to a query                              |
| event              | —                | a fact that something happened (fire and forget)     |
| command            | —                | an instruction to perform an action                  |
| ack                | —                | acknowledgement that a command was received          |
| routing_decision   | —                | the result of a routing computation                  |
| location           | —                | a physical or logical location identifier            |
| estimate           | —                | a computed prediction (time, cost, probability)      |
| inventory_update   | —                | a change to inventory state                          |
| reward             | —                | a loyalty or incentive credit                        |
| menu_update        | —                | a change to a product catalogue                      |
| tracking_update    | —                | a real-time position or status update                |
