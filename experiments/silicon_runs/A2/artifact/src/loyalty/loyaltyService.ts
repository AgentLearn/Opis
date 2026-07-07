/** 1 point per whole dollar spent; each point is worth 5 cents when redeemed. */
export const CENTS_PER_POINT_REDEEMED = 5;
export const CENTS_SPENT_PER_POINT_EARNED = 100;

export class LoyaltyService {
  private readonly balances = new Map<string, number>();

  balance(customerId: string): number {
    return this.balances.get(customerId) ?? 0;
  }

  earnFromPurchase(customerId: string, amountCents: number): number {
    const points = Math.floor(amountCents / CENTS_SPENT_PER_POINT_EARNED);
    this.balances.set(customerId, this.balance(customerId) + points);
    return points;
  }

  /** Deducts points and returns the discount they buy. */
  redeem(customerId: string, points: number): number {
    if (points <= 0 || !Number.isInteger(points)) {
      throw new Error('Redeemed points must be a positive integer');
    }
    const balance = this.balance(customerId);
    if (points > balance) {
      throw new Error(`Insufficient loyalty points: have ${balance}, requested ${points}`);
    }
    this.balances.set(customerId, balance - points);
    return points * CENTS_PER_POINT_REDEEMED;
  }

  refund(customerId: string, points: number): void {
    this.balances.set(customerId, this.balance(customerId) + points);
  }
}
