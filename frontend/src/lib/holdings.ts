/**
 * Average cost more than 20x away from the current price is almost never a real holding: the
 * screenshot import read a won amount, a total, or a return as the unit price. The screens
 * flag such rows so the user corrects them; nothing is recomputed here.
 */
export const SUSPICIOUS_COST_RATIO = 20

export function isSuspiciousCost(avgCost: number, price: number): boolean {
  if (!(avgCost > 0) || !(price > 0)) return false
  const ratio = avgCost / price
  return ratio >= SUSPICIOUS_COST_RATIO || ratio <= 1 / SUSPICIOUS_COST_RATIO
}
