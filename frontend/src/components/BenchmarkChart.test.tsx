import { cleanup, render, screen } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'

import type { Benchmark } from '../api/client'
import { CurrencyProvider } from '../lib/currency'
import { BenchmarkChart } from './BenchmarkChart'

const data: Benchmark = {
  mine: [
    { date: '2026-01-02', market_value: 1000, market_value_krw: 1_400_000, cost_basis: 1000, cost_basis_krw: 1_400_000 },
    { date: '2026-01-03', market_value: 1100, market_value_krw: 1_500_000, cost_basis: 1000, cost_basis_krw: 1_400_000 },
    { date: '2026-01-04', market_value: 1200, market_value_krw: 1_600_000, cost_basis: 1000, cost_basis_krw: 1_400_000 },
  ],
  benchmarks: [
    {
      symbol: 'SPY',
      name_ko: 'S&P 500 ETF',
      points: [
        { date: '2026-01-02', value: 1000, value_krw: 1_400_000 },
        { date: '2026-01-03', value: 1010, value_krw: 1_410_000 },
        { date: '2026-01-04', value: 1020, value_krw: 1_420_000 },
      ],
    },
    {
      symbol: 'ARKK',
      name_ko: 'ARK 이노베이션 ETF (캐시 우드)',
      points: [
        { date: '2026-01-02', value: 1000, value_krw: 1_400_000 },
        { date: '2026-01-03', value: 1005, value_krw: 1_405_000 },
        { date: '2026-01-04', value: 1021, value_krw: 1_421_000 },
      ],
    },
  ],
}

const realRect = HTMLElement.prototype.getBoundingClientRect

function renderChart(selected: string[], currency: 'KRW' | 'USD' = 'USD') {
  localStorage.setItem('asset-manager.currency', currency)
  return render(
    <CurrencyProvider>
      <BenchmarkChart data={data} selected={selected} />
    </CurrencyProvider>,
  )
}

describe('BenchmarkChart', () => {
  beforeAll(() => {
    // jsdom has no layout: give recharts' ResponsiveContainer a size and a ResizeObserver.
    HTMLElement.prototype.getBoundingClientRect = () =>
      ({ width: 640, height: 256, top: 0, left: 0, right: 640, bottom: 256, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect
    if (!('ResizeObserver' in globalThis)) {
      class RO {
        observe() {}
        unobserve() {}
        disconnect() {}
      }
      Object.assign(globalThis, { ResizeObserver: RO })
    }
  })
  afterAll(() => {
    HTMLElement.prototype.getBoundingClientRect = realRect
  })
  afterEach(() => {
    cleanup()
    localStorage.clear()
  })

  it('exposes the plot as one named image', () => {
    renderChart(['SPY'])
    expect(screen.getByRole('img', { name: '같은 날 같은 돈을 넣었다면 비교 차트' })).toBeInTheDocument()
  })

  it('lists my line and only the selected benchmarks in the legend, in order', () => {
    renderChart(['SPY'])
    const legend = screen.getByRole('list', { name: '범례' })
    expect(legend).toHaveTextContent('내 자산')
    expect(legend).toHaveTextContent('SPY')
    expect(legend).toHaveTextContent('S&P 500 ETF')
    expect(legend).not.toHaveTextContent('ARKK')
  })

  it('writes each line’s ticker and last value at its end, kept apart even when the lines end close', () => {
    const { container } = renderChart(['SPY', 'ARKK'])
    const labels = Array.from(container.querySelectorAll('g[aria-hidden="true"] text'))
    expect(labels.map((t) => t.textContent)).toEqual(
      expect.arrayContaining(['내 자산 $1.2K', 'SPY $1K', 'ARKK $1K']),
    )
    expect(labels).toHaveLength(3)
    // SPY (1020) and ARKK (1021) end a pixel apart; the labels are pushed to the minimum gap.
    const ys = labels.map((t) => Number(t.getAttribute('y'))).sort((a, b) => a - b)
    expect(ys[1] - ys[0]).toBeGreaterThanOrEqual(14)
    expect(ys[2] - ys[1]).toBeGreaterThanOrEqual(14)
  })

  it('switches values to won without recomputing them', () => {
    const { container } = renderChart(['SPY'], 'KRW')
    const labels = Array.from(container.querySelectorAll('g[aria-hidden="true"] text')).map((t) => t.textContent)
    expect(labels).toEqual(expect.arrayContaining(['내 자산 160만', 'SPY 142만']))
  })
})
