import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeAll, describe, expect, it } from 'vitest'

import { NO_DIRECTION_NOTE, PriceForecastChart } from './PriceForecastChart'

const bar = (date: string, close: number, volume = 1000, open = close) => ({ date, open, close, volume })
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
