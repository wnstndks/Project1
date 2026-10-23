/**
 * Pure data shaping for the "same money on the same days" comparison (BenchmarkChart,
 * CompareCard). The backend (`/api/portfolio/benchmark`) already replays my cash flows into each
 * benchmark and returns USD and KRW values; nothing here converts currencies, it only picks one
 * of the two amounts and arranges rows for the chart.
 */
import type { BenchmarkSeries, HistoryPoint } from '../api/client'

export type Pick = (usd: number, krw: number) => number

/**
 * Fixed per-symbol styling so toggling one benchmark never recolors another. The project palette
 * has two validated series hues (`--series-1` is mine, `--series-2` ARK); the rest are text tones
 * told apart by dash pattern as well, and every line also carries its ticker at its end.
 * `--accent` sits close to `--series-1`, so it goes to the one line that is off by default (QQQ)
 * and stays a sparse dotted line, while mine is a filled area.
 */
export const BENCHMARK_STYLE: Record<string, { cssVar: string; dash?: string }> = {
  ARKK: { cssVar: '--series-2' },
  SPY: { cssVar: '--ink', dash: '6 3' },
  'BTC-USD': { cssVar: '--muted', dash: '2 3' },
  'BRK-B': { cssVar: '--ink-2', dash: '8 3 2 3' },
  QQQ: { cssVar: '--accent', dash: '1 4' },
}

export const MINE_STYLE = { cssVar: '--series-1' }

/** Toggle order on the page (the backend's AM_BENCHMARKS default order). */
export const BENCHMARK_ORDER = ['ARKK', 'BRK-B', 'SPY', 'QQQ', 'BTC-USD']

/** On by default: the three the user asked about first. */
export const DEFAULT_BENCHMARKS = ['ARKK', 'SPY', 'BTC-USD']

export function benchmarkStyle(symbol: string): { cssVar: string; dash?: string } {
  return BENCHMARK_STYLE[symbol] ?? { cssVar: '--ink-2', dash: '4 4' }
}

/** Legend/tooltip label: ticker without the -USD suffix. */
export const benchmarkLabel = (symbol: string) => symbol.replace(/-USD$/, '')

/**
 * Add or remove a symbol, keeping `order`'s sequence so the chips and legend never reorder.
 * Symbols outside `order` go last in insertion order.
 */
export function toggleBenchmark(selected: string[], symbol: string, order = BENCHMARK_ORDER): string[] {
  const next = selected.includes(symbol) ? selected.filter((s) => s !== symbol) : [...selected, symbol]
  const rank = (s: string) => {
    const i = order.indexOf(s)
    return i < 0 ? order.length + next.indexOf(s) : i
  }
  return [...next].sort((a, b) => rank(a) - rank(b))
}

export type BenchmarkRow = { date: string; mine?: number } & Record<string, number | string | undefined>

/**
 * One row per date (union of every series, oldest first). `mine` is my portfolio value and each
 * benchmark sits under its own symbol, all in the selected currency via `pick`. A series without
 * a value on some date leaves that cell undefined so the line simply skips it.
 */
export function buildBenchmarkRows(mine: HistoryPoint[], benchmarks: BenchmarkSeries[], pick: Pick): BenchmarkRow[] {
  const rows = new Map<string, BenchmarkRow>()
  const row = (date: string) => {
    let r = rows.get(date)
    if (!r) {
      r = { date }
      rows.set(date, r)
    }
    return r
  }
  for (const p of mine) row(p.date).mine = pick(p.market_value, p.market_value_krw)
  for (const s of benchmarks) for (const p of s.points) row(p.date)[s.symbol] = pick(p.value, p.value_krw)
  return [...rows.values()].sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0))
}

export type LastValue = { key: string; date: string; value: number }

/** The last defined value of each key (the number drawn at the end of its line). */
export function lastValues(rows: BenchmarkRow[], keys: string[]): LastValue[] {
  const out: LastValue[] = []
  for (const key of keys) {
    for (let i = rows.length - 1; i >= 0; i--) {
      const v = rows[i][key]
      if (typeof v === 'number' && Number.isFinite(v)) {
        out.push({ key, date: rows[i].date, value: v })
        break
      }
    }
  }
  return out
}

/**
 * Nudge label centers apart so none overlap: at least `minGap` pixels between neighbours, all
 * inside [top, bottom]. Order is preserved (a label never jumps past another), and when the stack
 * is taller than the space it is centered on the available range.
 */
export function spreadLabels<T extends { y: number }>(items: T[], minGap: number, top: number, bottom: number): T[] {
  if (items.length === 0) return []
  const sorted = [...items].sort((a, b) => a.y - b.y)
  const ys = sorted.map((it) => it.y)
  // Push down from the top, then pull the stack back up if it ran past the bottom.
  for (let i = 1; i < ys.length; i++) ys[i] = Math.max(ys[i], ys[i - 1] + minGap)
  const overflow = ys[ys.length - 1] - bottom
  if (overflow > 0) for (let i = 0; i < ys.length; i++) ys[i] -= overflow
  for (let i = ys.length - 2; i >= 0; i--) ys[i] = Math.min(ys[i], ys[i + 1] - minGap)
  const underflow = top - ys[0]
  if (underflow > 0) for (let i = 0; i < ys.length; i++) ys[i] += underflow
  return sorted.map((it, i) => ({ ...it, y: ys[i] }))
}

export type LatestPair = { date: string; mine: { usd: number; krw: number }; benchmark: { usd: number; krw: number } }

/**
 * My value and one benchmark's on the latest date both have, for the one-line home summary.
 * Undefined when either series is empty or they share no date.
 */
export function latestPair(
  mine: HistoryPoint[],
  benchmarks: BenchmarkSeries[],
  symbol: string,
): LatestPair | undefined {
  const series = benchmarks.find((b) => b.symbol === symbol)
  if (!series || series.points.length === 0 || mine.length === 0) return undefined
  const byDate = new Map(series.points.map((p) => [p.date, p]))
  for (let i = mine.length - 1; i >= 0; i--) {
    const m = mine[i]
    const b = byDate.get(m.date)
    if (b) {
      return {
        date: m.date,
        mine: { usd: m.market_value, krw: m.market_value_krw },
        benchmark: { usd: b.value, krw: b.value_krw },
      }
    }
  }
  return undefined
}
