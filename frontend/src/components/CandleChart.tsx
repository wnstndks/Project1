import {
  CandlestickSeries,
  ColorType,
  createChart,
  type CandlestickData,
  type IChartApi,
  type ISeriesApi,
} from 'lightweight-charts'
import { useEffect, useRef } from 'react'

import type { Bar } from '../api/client'

/** lightweight-charts draws on canvas, so CSS variables must be resolved to concrete colors. */
function themeColors() {
  const css = getComputedStyle(document.documentElement)
  const v = (name: string) => css.getPropertyValue(name).trim()
  return {
    surface: v('--surface'),
    muted: v('--muted'),
    grid: v('--grid'),
    axis: v('--axis'),
    up: v('--gain-mark'),
    down: v('--loss-mark'),
  }
}

function applyTheme(chart: IChartApi, series: ISeriesApi<'Candlestick'>) {
  const c = themeColors()
  chart.applyOptions({
    layout: { background: { type: ColorType.Solid, color: c.surface }, textColor: c.muted },
    grid: { vertLines: { visible: false }, horzLines: { color: c.grid } },
    rightPriceScale: { borderColor: c.axis },
    timeScale: { borderColor: c.axis },
  })
  series.applyOptions({
    upColor: c.up,
    downColor: c.down,
    wickUpColor: c.up,
    wickDownColor: c.down,
    borderVisible: false,
  })
}

export function CandleChart({ bars }: { bars: Bar[] }) {
  const container = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)

  useEffect(() => {
    if (!container.current) return
    const chart = createChart(container.current, {
      autoSize: true,
      crosshair: { mode: 0 },
      timeScale: { fixLeftEdge: true, fixRightEdge: true },
      localization: { locale: 'ko-KR' },
    })
    const series = chart.addSeries(CandlestickSeries)
    chartRef.current = chart
    seriesRef.current = series
    applyTheme(chart, series)

    const scheme = window.matchMedia('(prefers-color-scheme: dark)')
    const onScheme = () => applyTheme(chart, series)
    scheme.addEventListener('change', onScheme)
    return () => {
      scheme.removeEventListener('change', onScheme)
      chart.remove()
    }
  }, [])

  useEffect(() => {
    const data: CandlestickData[] = bars.map((b) => ({
      time: b.date,
      open: b.open,
      high: b.high,
      low: b.low,
      close: b.close,
    }))
    // Won prices in the millions need no decimals; sub-dollar coins need four.
    const last = bars.at(-1)?.close ?? 0
    const precision = last >= 1000 ? 0 : last >= 1 ? 2 : 4
    seriesRef.current?.applyOptions({
      priceFormat: { type: 'price', precision, minMove: 1 / 10 ** precision },
    })
    seriesRef.current?.setData(data)
    chartRef.current?.timeScale().fitContent()
  }, [bars])

  return <div ref={container} className="h-80 w-full" />
}
