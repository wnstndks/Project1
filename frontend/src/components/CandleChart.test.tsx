import { act, cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import type { Bar } from '../api/client'

// lightweight-charts draws on canvas, which jsdom cannot provide, so the chart API is stubbed
// just enough to mount the component and feed it crosshair events. Series stubs are recorded by
// kind so a test can address the candlestick series the way the real event handler does.
const lwc = vi.hoisted(() => {
  const state = {
    crosshair: undefined as ((p: { seriesData: Map<object, object> }) => void) | undefined,
    series: [] as { kind: string; api: object }[],
  }
  const addSeries = (def: { kind: string }) => {
    const api = {
      applyOptions: vi.fn(),
      setData: vi.fn(),
      priceScale: () => ({ applyOptions: vi.fn() }),
      createPriceLine: vi.fn(() => ({})),
      removePriceLine: vi.fn(),
    }
    state.series.push({ kind: def.kind, api })
    return api
  }
  const createChart = () => ({
    addSeries,
    applyOptions: vi.fn(),
    timeScale: () => ({ fitContent: vi.fn() }),
    subscribeCrosshairMove: (cb: typeof state.crosshair) => {
      state.crosshair = cb
    },
    unsubscribeCrosshairMove: vi.fn(),
    removeSeries: vi.fn(),
    remove: vi.fn(),
  })
  return { state, createChart }
})

vi.mock('lightweight-charts', () => ({
  createChart: lwc.createChart,
  CandlestickSeries: { kind: 'candle' },
  HistogramSeries: { kind: 'volume' },
  LineSeries: { kind: 'line' },
  LineStyle: { Solid: 0, Dashed: 2 },
  ColorType: { Solid: 'solid' },
}))

import { CandleChart } from './CandleChart'

const bar = (date: string, open: number, high: number, low: number, close: number): Bar => ({
  date,
  open,
  high,
  low,
  close,
  adj_close: close,
  volume: 1000,
})
const bars = [bar('2026-10-19', 99, 104, 98, 100), bar('2026-10-20', 100, 103, 99, 102), bar('2026-10-21', 102, 102, 100, 101)]
const fmt = (v: number) => `${v}원`
const valueOf = (label: string) => screen.getByText(label).nextSibling
const candleSeries = () => lwc.state.series.find((s) => s.kind === 'candle')!.api
const hover = (item: object | undefined) =>
  act(() => lwc.state.crosshair?.({ seriesData: item ? new Map([[candleSeries(), item]]) : new Map() }))

describe('CandleChart readout', () => {
  beforeAll(() => {
    // jsdom has no matchMedia; the chart listens to it for the OS colour scheme.
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: () => ({ addEventListener() {}, removeEventListener() {} }),
    })
  })

  afterEach(() => {
    cleanup()
    lwc.state.series = []
    lwc.state.crosshair = undefined
  })

  it('sits above the chart canvases and starts on the last bar', () => {
    render(<CandleChart bars={bars} ma={[{ n: 20, values: [100, 101, 101.5], cssVar: '--ink' }]} prevClose={104} format={fmt} />)
    expect(valueOf('종가')).toHaveTextContent('101원')
    const overlay = screen.getByText('종가').closest('.absolute') as HTMLElement
    // The legend names the average too, so read its value inside the overlay only.
    expect(within(overlay).getByText('20일 평균').nextSibling).toHaveTextContent('101.5원')
    // lightweight-charts paints opaque canvases at z-index 1 and 2: without a higher z-index the
    // readout exists in the DOM but is never visible.
    expect(overlay.className).toMatch(/\bz-10\b/)
    expect(overlay).toHaveClass('pointer-events-none')
    // The chart itself stays the one named image; the readout is plain text beside it.
    expect(screen.getByRole('img', { name: '캔들 차트' })).toBeInTheDocument()
  })

  it('follows the candle under the crosshair and falls back to the last bar when the pointer leaves', () => {
    render(<CandleChart bars={bars} prevClose={104} format={fmt} />)
    hover({ time: '2026-10-19', open: 99, high: 104, low: 98, close: 100 })
    expect(valueOf('종가')).toHaveTextContent('100원')
    expect(valueOf('고가')).toHaveTextContent('104원')
    // First visible bar: its move comes from the close before the window (104).
    const change = screen.getByText(/−4원/)
    expect(change).toHaveClass('text-loss')
    expect(change).toHaveTextContent('▼−4원(−3.85%)')
    // A BusinessDay-shaped time resolves to the same bar date.
    hover({ time: { year: 2026, month: 10, day: 20 }, open: 100, high: 103, low: 99, close: 102 })
    expect(valueOf('종가')).toHaveTextContent('102원')
    expect(screen.getByText(/\+2원/)).toHaveClass('text-gain')
    hover(undefined)
    expect(valueOf('종가')).toHaveTextContent('101원')
  })
})
