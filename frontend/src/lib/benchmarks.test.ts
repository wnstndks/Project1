import { describe, expect, it } from 'vitest'

import type { BenchmarkSeries, HistoryPoint } from '../api/client'
import {
  BENCHMARK_ORDER,
  buildBenchmarkRows,
  lastValues,
  latestPair,
  spreadLabels,
  toggleBenchmark,
} from './benchmarks'

const mine: HistoryPoint[] = [
  { date: '2026-01-02', market_value: 100, market_value_krw: 140_000, cost_basis: 100, cost_basis_krw: 140_000 },
  { date: '2026-01-03', market_value: 110, market_value_krw: 150_000, cost_basis: 100, cost_basis_krw: 140_000 },
]
const spy: BenchmarkSeries = {
  symbol: 'SPY',
  name_ko: 'S&P 500 ETF',
  points: [
    { date: '2026-01-02', value: 100, value_krw: 140_000 },
    { date: '2026-01-03', value: 105, value_krw: 145_000 },
    { date: '2026-01-04', value: 106, value_krw: 146_000 },
  ],
}
const usd = (u: number) => u
const krw = (_u: number, k: number) => k

describe('buildBenchmarkRows', () => {
  it('merges every series on the union of dates, oldest first, in the picked currency', () => {
    const rows = buildBenchmarkRows(mine, [spy], krw)
    expect(rows.map((r) => r.date)).toEqual(['2026-01-02', '2026-01-03', '2026-01-04'])
    expect(rows[1]).toEqual({ date: '2026-01-03', mine: 150_000, SPY: 145_000 })
    // My history ends a day earlier: that cell is simply absent, never 0.
    expect(rows[2].mine).toBeUndefined()
    expect(rows[2].SPY).toBe(146_000)
    expect(buildBenchmarkRows(mine, [spy], usd)[0]).toEqual({ date: '2026-01-02', mine: 100, SPY: 100 })
  })
})

describe('toggleBenchmark', () => {
  it('adds and removes while keeping the fixed display order', () => {
    expect(toggleBenchmark(['ARKK', 'SPY'], 'BRK-B')).toEqual(['ARKK', 'BRK-B', 'SPY'])
    expect(toggleBenchmark(['ARKK', 'BRK-B', 'SPY'], 'ARKK')).toEqual(['BRK-B', 'SPY'])
    expect(toggleBenchmark([], 'BTC-USD')).toEqual(['BTC-USD'])
  })

  it('puts symbols outside the known order last', () => {
    expect(toggleBenchmark(['SPY'], 'VTI')).toEqual(['SPY', 'VTI'])
    expect(toggleBenchmark(['VTI', 'SPY'], 'ARKK')).toEqual(['ARKK', 'SPY', 'VTI'])
    expect(BENCHMARK_ORDER).toContain('SPY')
  })
})

describe('lastValues', () => {
  it('takes the last defined value per key and skips keys with none', () => {
    const rows = buildBenchmarkRows(mine, [spy], usd)
    expect(lastValues(rows, ['mine', 'SPY', 'QQQ'])).toEqual([
      { key: 'mine', date: '2026-01-03', value: 110 },
      { key: 'SPY', date: '2026-01-04', value: 106 },
    ])
  })
})

describe('spreadLabels', () => {
  const ys = (items: { y: number }[]) => items.map((i) => i.y)

  it('leaves well-separated labels where they are', () => {
    expect(ys(spreadLabels([{ y: 10 }, { y: 50 }], 14, 0, 100))).toEqual([10, 50])
  })

  it('pushes overlapping labels apart without reordering them', () => {
    const out = spreadLabels([{ key: 'a', y: 52 }, { key: 'b', y: 50 }, { key: 'c', y: 51 }], 14, 0, 200)
    expect(out.map((o) => o.key)).toEqual(['b', 'c', 'a'])
    expect(ys(out)).toEqual([50, 64, 78])
  })

  it('keeps the stack inside the bounds', () => {
    expect(ys(spreadLabels([{ y: 95 }, { y: 98 }], 14, 0, 100))).toEqual([86, 100])
    // Already inside the bounds: only the gap is enforced, nothing snaps to the edge.
    expect(ys(spreadLabels([{ y: 1 }, { y: 2 }], 14, 0, 100))).toEqual([1, 15])
    expect(ys(spreadLabels([{ y: -5 }, { y: -3 }], 14, 0, 100))).toEqual([0, 14])
    expect(spreadLabels([], 14, 0, 100)).toEqual([])
  })
})

describe('latestPair', () => {
  it('pairs my latest value with the benchmark on the same date', () => {
    expect(latestPair(mine, [spy], 'SPY')).toEqual({
      date: '2026-01-03',
      mine: { usd: 110, krw: 150_000 },
      benchmark: { usd: 105, krw: 145_000 },
    })
  })

  it('is undefined without a shared date or an unknown symbol', () => {
    expect(latestPair(mine, [spy], 'QQQ')).toBeUndefined()
    expect(latestPair([], [spy], 'SPY')).toBeUndefined()
    const other = { ...spy, points: [{ date: '2025-12-31', value: 1, value_krw: 1 }] }
    expect(latestPair(mine, [other], 'SPY')).toBeUndefined()
  })
})
