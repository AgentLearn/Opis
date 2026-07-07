export type PaymentResult =
  | { status: 'confirmed'; paymentId: string }
  | { status: 'declined'; reason: string };

export interface PaymentGateway {
  charge(customerId: string, amountCents: number): Promise<PaymentResult>;
}

/**
 * Stand-in for a real processor (Stripe, Adyen, ...). Declines can be forced
 * per customer to exercise the failure path.
 */
export class MockCardGateway implements PaymentGateway {
  private readonly declinedCustomers = new Set<string>();

  declineNextChargeFor(customerId: string): void {
    this.declinedCustomers.add(customerId);
  }

  async charge(customerId: string, amountCents: number): Promise<PaymentResult> {
    if (amountCents <= 0) {
      return { status: 'declined', reason: 'Charge amount must be positive' };
    }
    if (this.declinedCustomers.delete(customerId)) {
      return { status: 'declined', reason: 'Card declined by issuer' };
    }
    return { status: 'confirmed', paymentId: `pay_${crypto.randomUUID()}` };
  }
}
