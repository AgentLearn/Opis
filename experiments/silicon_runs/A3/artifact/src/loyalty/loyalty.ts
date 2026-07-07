const POINTS_PER_DOLLAR = 1;
const REDEEM_BLOCK_POINTS = 100; // points per reward block
const REDEEM_BLOCK_VALUE_CENTS = 500; // each block is worth $5 off

/**
 * Tracks points per customer. Points accrue on paid orders; at checkout a
 * customer may redeem whole 100-point blocks for $5 discounts.
 */
export class LoyaltyProgram {
  private readonly balances = new Map<string, number>();

  pointsOf(customerId: string): number {
    return this.balances.get(customerId) ?? 0;
  }

  earn(customerId: string, paidCents: number): number {
    const earned = Math.floor(paidCents / 100) * POINTS_PER_DOLLAR;
    this.balances.set(customerId, this.pointsOf(customerId) + earned);
    return earned;
  }

  /**
   * Converts up to `requestedPoints` into a discount, capped by the balance,
   * whole blocks, and the order subtotal. Deducts the points it uses.
   */
  redeem(customerId: string, requestedPoints: number, subtotalCents: number): { pointsUsed: number; discountCents: number } {
    const available = this.pointsOf(customerId);
    const maxBlocksByPoints = Math.floor(Math.min(requestedPoints, available) / REDEEM_BLOCK_POINTS);
    const maxBlocksByTotal = Math.floor(subtotalCents / REDEEM_BLOCK_VALUE_CENTS);
    const blocks = Math.max(0, Math.min(maxBlocksByPoints, maxBlocksByTotal));
    const pointsUsed = blocks * REDEEM_BLOCK_POINTS;
    this.balances.set(customerId, available - pointsUsed);
    return { pointsUsed, discountCents: blocks * REDEEM_BLOCK_VALUE_CENTS };
  }
}
