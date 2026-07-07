import { nextId, type Money, type Payment } from '../domain/types.ts';

export interface PaymentGateway {
  charge(customerId: string, amount: Money): Promise<Payment>;
}

/**
 * Simulated card processor. Declines can be forced per customer to
 * exercise the "no payment, no kitchen" rule in tests and demos.
 */
export class MockPaymentGateway implements PaymentGateway {
  private readonly declined = new Set<string>();

  declineCustomer(customerId: string): void {
    this.declined.add(customerId);
  }

  async charge(customerId: string, amount: Money): Promise<Payment> {
    if (amount <= 0) {
      return { id: nextId('pay'), customerId, amount, status: 'declined', reason: 'invalid amount' };
    }
    if (this.declined.has(customerId)) {
      return { id: nextId('pay'), customerId, amount, status: 'declined', reason: 'card declined' };
    }
    return { id: nextId('pay'), customerId, amount, status: 'confirmed' };
  }
}
