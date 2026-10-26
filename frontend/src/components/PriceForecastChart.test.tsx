import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeAll, describe, expect, it } from 'vitest'

import { buildRows } from '../lib/priceChart'
import { NO_DIRECTION_NOTE, PriceForecastChart, PriceTooltipContent } from './PriceForecastChart'

const bar = (
  date: string,
  close: number,
  volume = 1000,
  open = close,
  high = Math.max(open, close),
  low = Math.min(open, close),
) => ({ date, open, high, low, close, volume })
const bars = [bar('2026-10-19', 100), bar('2026-10-20', 102), bar('2026-10-21', 101)]
const horizon = { target_date: '2026-10-28', base_price: 100, p10: 95, p50: 101, p90: 107 }

describe('PriceForecastChart', () => {
  afterEach(cleanup)

  beforeAll(() => {
    // jsdom has no ResizeObserver; recharts' ResponsiveContainer needs one to mount.
    if (!('ResizeObserver' in globalThis)) {
      class RO {
        observe() {}
        unobserve() {}
        disconnect() {}
      }
      Object.assign(globalThis, { ResizeObserver: RO })
    }
  })

  it('exposes the plot as one named image', () => {
    render(
      <PriceForecastChart
        bars={bars}
        ma={[]}
        horizons={[horizon]}
        format={(v) => `$${v}`}
        compact={(v) => `${v}`}
      />,
    )
    expect(screen.getByRole('img', { name: '가격과 예측 차트' })).toBeInTheDocument()
  })

  it('lists the drawn series in the legend and leaves in-plot marks to their own labels', () => {
    render(
      <PriceForecastChart
        bars={bars}
        ma={[{ n: 20, values: [100, 101, 101] }]}
        horizons={[{ ...horizon, direction_edge: false }]}
        avgCost={100}
        extremes={{ high: 102, highDate: '2026-10-20', low: 90, lowDate: '2025-12-01' }}
        format={(v) => `$${v}`}
        compact={(v) => `${v}`}
      />,
    )
    const legend = screen.getByRole('list', { name: '범례' })
    expect(legend).toHaveTextContent('종가')
    expect(legend).toHaveTextContent('20일 평균')
    expect(legend).not.toHaveTextContent('60일 평균')
    expect(legend).toHaveTextContent('예측 범위(10번 중 8번) · 점선은 예상 중간값')
    // 내 평균 and the 52-week marks are labelled inside the plot, so they are not repeated here.
    expect(legend).not.toHaveTextContent('52주')
    expect(legend).not.toHaveTextContent('내 평균')
  })

  it('says the band is about spread only while the direction has no edge', () => {
    render(
      <PriceForecastChart
        bars={bars}
        ma={[]}
        horizons={[{ ...horizon, direction_edge: false }]}
        format={(v) => `$${v}`}
        compact={(v) => `${v}`}
      />,
    )
    expect(screen.getByText(NO_DIRECTION_NOTE)).toBeInTheDocument()
  })

  it('drops the spread-only note once every horizon has a direction edge', () => {
    render(
      <PriceForecastChart
        bars={bars}
        ma={[]}
        horizons={[{ ...horizon, direction_edge: true }]}
        format={(v) => `$${v}`}
        compact={(v) => `${v}`}
      />,
    )
    expect(screen.queryByText(NO_DIRECTION_NOTE)).toBeNull()
  })

  it('shows no forecast entries or note for a plain price history', () => {
    render(
      <PriceForecastChart
        bars={[bar('2026-10-19', 100), bar('2026-10-20', 102)]}
        ma={[]}
        format={(v) => `$${v}`}
        compact={(v) => `${v}`}
      />,
    )
    const legend = screen.getByRole('list', { name: '범례' })
    expect(legend).toHaveTextContent('종가')
    expect(legend).toHaveTextContent('거래량')
    expect(legend).not.toHaveTextContent('예측 범위')
    expect(screen.queryByText(NO_DIRECTION_NOTE)).toBeNull()
  })
})

describe('PriceTooltipContent', () => {
  afterEach(cleanup)

  const fmt = (v: number) => `${v.toLocaleString('en-US')}원`
  const ma = [{ n: 20, values: [100, 101, 101] }]
  // Window opens on 10.19 with the bar before it closing at 104; one horizon a week out.
  const rows = buildRows(
    [bar('2026-10-19', 100, 1000, 99, 104, 98), bar('2026-10-20', 102), bar('2026-10-21', 101)],
    ma,
    [horizon],
    104,
  )
  const valueOf = (label: string) => screen.getByText(label).nextSibling

  it('shows a past day: close, day change with sign/arrow/colour, high, low, open, averages, volume', () => {
    render(<PriceTooltipContent row={rows[0]} ma={ma} format={fmt} />)
    expect(valueOf('종가')).toHaveTextContent('100원')
    const change = screen.getByText(/−4원/)
    expect(change).toHaveClass('text-loss')
    expect(change).toHaveTextContent('▼−4원(−3.85%)')
    expect(valueOf('고가')).toHaveTextContent('104원')
    expect(valueOf('저가')).toHaveTextContent('98원')
    expect(valueOf('시가')).toHaveTextContent('99원')
    expect(valueOf('20일 평균')).toHaveTextContent('100원')
    expect(valueOf('거래량')).toHaveTextContent('1,000')
  })

  it('marks an up day red with ▲ and a plus sign', () => {
    render(<PriceTooltipContent row={rows[1]} ma={[]} format={fmt} />)
    const change = screen.getByText(/\+2원/)
    expect(change).toHaveClass('text-gain')
    expect(change).toHaveTextContent('▲+2원(+2.00%)')
  })

  it('hides the day-change line when no previous close exists', () => {
    const [first] = buildRows([bar('2026-10-19', 100)], [])
    render(<PriceTooltipContent row={first} ma={[]} format={fmt} />)
    expect(screen.getByText('종가')).toBeInTheDocument()
    expect(screen.queryByText('전일 대비')).toBeNull()
  })

  it('shows a forecast day as plain signed percents from the last close: no ▲▼, no gain/loss colour', () => {
    const { container } = render(<PriceTooltipContent row={rows[3]} ma={ma} format={fmt} />)
    expect(screen.getByText(/예측$/)).toBeInTheDocument()
    expect(valueOf('예상 중간값')).toHaveTextContent('102.01원')
    expect(valueOf('10번 중 8번 범위')).toHaveTextContent('95.95원~108.07원')
    expect(valueOf('마지막 종가 대비')).toHaveTextContent('+1.0% (−5.0%~+7.0%)')
    expect(container.textContent).not.toMatch(/[▲▼]/)
    expect(container.querySelector('.text-gain, .text-loss')).toBeNull()
    // Nothing from a trading day leaks into a forecast day.
    expect(screen.queryByText('고가')).toBeNull()
    expect(screen.queryByText('전일 대비')).toBeNull()
  })
})
