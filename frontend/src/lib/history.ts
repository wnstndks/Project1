import type { HistoryPoint } from '../api/client'
import { isoDate } from './format'
import { RANGE_OPTIONS, rangeStart, type RangeKey } from './ranges'

const DAY_MS = 86_400_000

function firstDate(points: HistoryPoint[]): string {
  return points.reduce((a, p) => (p.date < a ? p.date : a), points[0].date)
}

/**
 * Calendar days the portfolio history covers, from its first point to `today` inclusive.
 * Screenshot imports are recorded on the import date, so a fresh portfolio has a span of 1~2 days
 * and no trend worth charting yet.
 */
export function historySpanDays(points: HistoryPoint[], today = new Date()): number {
  if (points.length === 0) return 0
  const start = new Date(`${firstDate(points)}T00:00:00`)
  const end = new Date(`${isoDate(today)}T00:00:00`)
  return Math.max(1, Math.floor((end.getTime() - start.getTime()) / DAY_MS) + 1)
}

/** Below this many days the chart is replaced by a hint about trade dates. */
export const MIN_HISTORY_DAYS = 7

/** The shortest preset range that still shows every point (relative to today); `ALL` when none does. */
export function shortestCoveringRange(points: HistoryPoint[]): RangeKey {
  if (points.length === 0) return 'ALL'
  const first = firstDate(points)
  for (const option of RANGE_OPTIONS) {
    const start = rangeStart(option.value)
    if (start === undefined || start <= first) return option.value
  }
  return 'ALL'
}
