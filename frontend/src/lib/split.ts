/** A split ratio as old → new shares, e.g. 1→10, 2→3, or 30→1 for a reverse split. */
export function splitShares(ratio: number): { from: number; to: number } {
  for (let den = 1; den <= 1000; den++) {
    const num = Math.round(ratio * den)
    if (num > 0 && Math.abs(ratio * den - num) < 1e-6 * den) return { from: den, to: num }
  }
  return { from: 1, to: ratio }
}
