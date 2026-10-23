import type { Bar } from '../api/client'
import { isoDate } from './format'

/** Moving-average windows offered on the asset chart, in bars (trading days for stocks, days for coins). */
export const MA_PERIODS = [5, 20, 60, 120] as const
export const DEFAULT_MA_PERIODS: number[] = [20, 60]

/**
 * Simple moving average over the last `n` values. The first n−1 entries are null because
 * there is not enough history yet; callers fetch extra bars before the visible range so the
 * line is defined from the first visible bar.
 */
export function sma(values: number[], n: number): (number | null)[] {
  const out: (number | null)[] = new Array<number | null>(values.length).fill(null)
  if (n < 1) return out
  let sum = 0
  for (let i = 0; i < values.length; i++) {
    sum += values[i]
    if (i >= n) sum -= values[i - n]
    if (i >= n - 1) out[i] = sum / n
  }
  return out
}

export type Extreme = { high: number; highDate: string; low: number; lowDate: string }

/**
 * Highest high and lowest low over the `days` calendar days ending at the last bar
 * (52 weeks by default). Null without bars.
 */
export function fiftyTwoWeek(bars: Pick<Bar, 'date' | 'high' | 'low'>[], days = 365): Extreme | null {
  const last = bars.at(-1)
  if (!last) return null
  const from = new Date(`${last.date}T00:00:00`)
  from.setDate(from.getDate() - days)
  const cutoff = isoDate(from)
  let result: Extreme | null = null
  for (const b of bars) {
    if (b.date < cutoff) continue
    if (!result) {
      result = { high: b.high, highDate: b.date, low: b.low, lowDate: b.date }
      continue
    }
    if (b.high > result.high) {
      result.high = b.high
      result.highDate = b.date
    }
    if (b.low < result.low) {
      result.low = b.low
      result.lowDate = b.date
    }
  }
  return result
}

/**
 * Last close against the close before it, for symbols without a holding (display only; held
 * symbols use the backend's `day_change_pct`, which is based on the live quote).
 */
export function dayChange(bars: Pick<Bar, 'close'>[]): { change: number; pct: number } | null {
  const last = bars.at(-1)
  const prev = bars.at(-2)
  if (!last || !prev || !(prev.close > 0)) return null
  const change = last.close - prev.close
  return { change, pct: (change / prev.close) * 100 }
}
