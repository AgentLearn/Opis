export type PaymentResult =
  | { status: "confirmed"; transactionId: string }
  | { status: "declined"; reason: string };

export interface PaymentGateway {
  charge(customerId: string, amountCents: number): Promise<PaymentResult>;
}

/**
 * Stand-in for a real processor (Stripe, Adyen, ...). Declines can be forced
 * per customer so tests and demos can exercise the failure path.
 */
export class SimulatedPaymentGateway implements PaymentGateway {
  private txCounter = 0;
  private readonly declineList = new Set<string>();

  declineNextChargeFor(customerId: string): void {
    this.declineList.add(customerId);
  }

  async charge(customerId: string, amountCents: number): Promise<PaymentResult> {
    if (amountCents <= 0) return { status: "declined", reason: "invalid amount" };
    if (this.declineList.delete(customerId)) {
      return { status: "declined", reason: "card declined" };
    }
    this.txCounter += 1;
    return { status: "confirmed", transactionId: `tx-${this.txCounter.toString().padStart(6, "0")}` };
  }
}
