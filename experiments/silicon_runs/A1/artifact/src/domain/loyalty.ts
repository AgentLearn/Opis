import type { Money } from './types.ts';

export const POINTS_PER_DOLLAR = 1;
/** Points are redeemed in blocks: 100 points = $5 off. */
export const REDEEM_BLOCK_POINTS = 100;
export const REDEEM_BLOCK_VALUE: Money = 500;

/**
 * Tracks loyalty points per customer. Points are earned on the amount
 * actually paid and redeemed at checkout in fixed blocks.
 */
export class LoyaltyService {
  private readonly balances = new Map<string, number>();

  balance(customerId: string): number {
    return this.balances.get(customerId) ?? 0;
  }

  /** Earn points on a confirmed payment (1 point per whole dollar paid). */
  earn(customerId: string, amountPaid: Money): number {
    const earned = Math.floor(amountPaid / 100) * POINTS_PER_DOLLAR;
    this.balances.set(customerId, this.balance(customerId) + earned);
    return earned;
  }

  /**
   * Redeem as many whole blocks as the balance and subtotal allow.
   * Returns the discount; deducts the spent points from the balance.
   */
  redeem(customerId: string, subtotal: Money): { discount: Money; pointsSpent: number } {
    const affordableBlocks = Math.floor(this.balance(customerId) / REDEEM_BLOCK_POINTS);
    const usefulBlocks = Math.ceil(subtotal / REDEEM_BLOCK_VALUE);
    const blocks = Math.min(affordableBlocks, usefulBlocks);
    const pointsSpent = blocks * REDEEM_BLOCK_POINTS;
    const discount = Math.min(blocks * REDEEM_BLOCK_VALUE, subtotal);
    this.balances.set(customerId, this.balance(customerId) - pointsSpent);
    return { discount, pointsSpent };
  }
}
