/**
 * Pure data shaping for the asset page's price-and-forecast chart (PriceForecastChart). No
 * React or recharts here so the row and axis logic can be unit tested directly.
 */
import { formatDate, isoDate } from './format'

/**
 * Moving-average styling is fixed per period, never by position in the list, so toggling one
 * line never recolors another. The close takes --series-1 and the forecast band --series-2, so
 * the averages use the accent and the text tones, and differ by dash pattern as well as color.
 */
export const MA_STYLE: Record<number, { cssVar: string; dash?: string; label: string }> = {
  5: { cssVar: '--accent', dash: '4 2', label: '5일 평균' },
  20: { cssVar: '--ink', label: '20일 평균' },
  60: { cssVar: '--ink-2', dash: '6 3', label: '60일 평균' },
  120: { cssVar: '--muted', dash: '2 3', label: '120일 평균' },
}

export type MaLine = { n: number; values: (number | null)[] }
export type ChartBar = { date: string; open: number; close: number; volume: number }
export type ForecastPoint = {
  target_date: string
  base_price: number
  p10: number
  p50: number
  p90: number
  /** Live verdict on the direction; when false or absent the chart says the band is about spread only. */
  direction_edge?: boolean
}

export type Row = {
  t: number
  close?: number
  volume?: number
  /** Close at or above the previous close: colors the volume bar. */
  up?: boolean
  mid?: number
  band?: [number, number]
  [ma: `ma${number}`]: number | undefined
}

export const DAY_MS = 86_400_000

/** Local midnight of a YYYY-MM-DD date, as epoch ms (the chart's x value). */
export const dayStart = (d: string) => new Date(`${d}T00:00:00`).getTime()

/** Local midnight today, for the "오늘" marker. */
export function todayStart(): number {
  const d = new Date()
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}

/**
 * Chart rows: one per bar, then one per forecast horizon. The fan starts at the last close
 * (mid = close, band collapsed) so it grows out of the price line. The model forecasts
 * returns from its own base close (the last final bar, in USD); those returns are re-anchored
 * on the last close drawn, so the band stays continuous when the last bar is still trading
 * or the chart is in won. Horizons whose target date is not after the last bar are skipped;
 * without any usable horizon the rows carry no fan at all (no stray anchor dot).
 */
export function buildRows(bars: ChartBar[], ma: MaLine[], horizons: ForecastPoint[] = []): Row[] {
  const rows: Row[] = bars.map((b, i) => {
    const row: Row = {
      t: dayStart(b.date),
      close: b.close,
      volume: b.volume,
      up: b.close >= (bars[i - 1]?.close ?? b.open),
    }
    for (const m of ma) row[`ma${m.n}`] = m.values[i] ?? undefined
    return row
  })
  const last = rows.at(-1)
  if (!last || last.close === undefined) return rows
  const future = horizons
    .filter((h) => h.base_price > 0 && dayStart(h.target_date) > last.t)
    .sort((a, b) => dayStart(a.target_date) - dayStart(b.target_date))
  if (future.length === 0) return rows
  const anchor = last.close
  last.mid = anchor
  last.band = [anchor, anchor]
  for (const h of future) {
    const k = anchor / h.base_price
    rows.push({ t: dayStart(h.target_date), mid: h.p50 * k, band: [h.p10 * k, h.p90 * k] })
  }
  return rows
}

/**
 * Price axis range. The data is padded so the volume strip (bottom 20% of the plot) stays
 * clear of the price line, and labels above the 52-week high fit. `extras` (my average cost,
 * 52-week marks) join the range only when they are near the data; an average cost 20x away
 * from the price would otherwise squash the chart into a flat line.
 */
export function priceDomain(rows: Row[], extras: number[] = []): [number, number] {
  let min = Infinity
  let max = -Infinity
  for (const r of rows) {
    for (const [k, v] of Object.entries(r)) {
      if (k === 't' || k === 'volume' || k === 'up' || v === undefined || v === null) continue
      for (const x of Array.isArray(v) ? v : [v]) {
        if (typeof x !== 'number' || !Number.isFinite(x)) continue
        if (x < min) min = x
        if (x > max) max = x
      }
    }
  }
  if (!Number.isFinite(min)) return [0, 1]
  const span = max - min || Math.abs(max) * 0.02 || 1
  for (const x of extras) {
    if (!isNear(x, min, max, span)) continue
    if (x < min) min = x
    if (x > max) max = x
  }
  const padded = max - min || span
  return [min - padded * 0.33, max + padded * 0.08]
}

/** Within half the data range of either end: close enough to draw without distorting the scale. */
export function isNear(x: number, min: number, max: number, span = max - min): boolean {
  return Number.isFinite(x) && x >= min - span * 0.5 && x <= max + span * 0.5
}

/**
 * Axis tick text: `formatDate(short)` (month.day) for short ranges, yy.month once the window
 * is longer than ~7 months. `today` only decides whether the short form needs a year prefix.
 */
export function tickLabel(t: number, spanDays: number, today = new Date()): string {
  const d = new Date(t)
  return spanDays > 200
    ? `${String(d.getFullYear()).slice(2)}.${d.getMonth() + 1}`
    : formatDate(isoDate(d), 'short', today)
}

/**
 * Which side of a marker its label goes, so a 52-week mark near the right edge of the window
 * does not run off the plot: the last fifth of the window labels to the left.
 */
export function labelSide(t: number, first: number, last: number): 'left' | 'right' {
  return last > first && t > first + (last - first) * 0.8 ? 'left' : 'right'
}
