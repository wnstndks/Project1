import {
  CandlestickSeries,
  ColorType,
  createChart,
  HistogramSeries,
  LineSeries,
  LineStyle,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type LineData,
  type MouseEventParams,
  type Time,
} from 'lightweight-charts'
import { useEffect, useRef, useState, type ReactNode } from 'react'

import type { Bar } from '../api/client'
import { MA_STYLE } from '../lib/priceChart'
import { BarReadout } from './BarReadout'
import { CandleSwatch, ChartLegend, LineSwatch, VolumeSwatch } from './ui'

/** A moving average to draw: values aligned with `bars`, color as a CSS variable name (`--ink-2`). */
export type CandleMa = { n: number; values: (number | null)[]; cssVar: string; dash?: string }

/** lightweight-charts draws on canvas, so CSS variables must be resolved to concrete colors. */
function themeColors() {
  const css = getComputedStyle(document.documentElement)
  const v = (name: string) => css.getPropertyValue(name).trim()
  return {
    surface: v('--surface'),
    muted: v('--muted'),
    grid: v('--grid'),
    axis: v('--axis'),
    ink2: v('--ink-2'),
    up: v('--gain-mark'),
    down: v('--loss-mark'),
    resolve: v,
  }
}

/** 50% alpha for a #rrggbb token; anything else is passed through unchanged. */
function translucent(color: string): string {
  return /^#[0-9a-f]{6}$/i.test(color) ? `${color}80` : color
}

/** The bar date (YYYY-MM-DD) behind a lightweight-charts time, whichever shape it comes back in. */
function timeKey(t: Time): string {
  if (typeof t === 'string') return t
  if (typeof t === 'number') return new Date(t * 1000).toISOString().slice(0, 10)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${t.year}-${pad(t.month)}-${pad(t.day)}`
}

type Props = {
  bars: Bar[]
  ma?: CandleMa[]
  avgCost?: number
  /** Close of the bar just before `bars`, so the first candle has its day change too. */
  prevClose?: number
  /** The page's price formatter (display currency), for the corner readout. */
  format: (v: number) => string
}

export function CandleChart({ bars, ma = [], avgCost, prevClose, format }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const maRef = useRef<Map<number, ISeriesApi<'Line'>>>(new Map())
  const avgLineRef = useRef<IPriceLine | null>(null)
  // Bumped when the theme changes (the app's <html data-theme>, or the OS scheme while on
  // "system") so every series re-reads the CSS variables.
  const [theme, setTheme] = useState(0)
  // Date of the bar under the crosshair; null when the pointer is off the data (readout shows the last bar).
  const [hoverDate, setHoverDate] = useState<string | null>(null)

  useEffect(() => {
    if (!container.current) return
    const chart = createChart(container.current, {
      autoSize: true,
      crosshair: { mode: 0 },
      timeScale: { fixLeftEdge: true, fixRightEdge: true },
      localization: { locale: 'ko-KR' },
    })
    const candle = chart.addSeries(CandlestickSeries, { borderVisible: false })
    const maSeries = new Map<number, ISeriesApi<'Line'>>()
    // Volume is a strip in the bottom fifth on its own hidden scale; candles keep the top 75%.
    const volume = chart.addSeries(HistogramSeries, {
      priceScaleId: '',
      priceFormat: { type: 'volume' },
      priceLineVisible: false,
      lastValueVisible: false,
    })
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } })
    candle.priceScale().applyOptions({ scaleMargins: { top: 0.05, bottom: 0.25 } })
    chartRef.current = chart
    candleRef.current = candle
    volumeRef.current = volume
    maRef.current = maSeries

    // The readout follows the candle under the crosshair; seriesData carries the original item,
    // whose time is the bar date we set. Off the data (or on mouse leave) it falls back to null.
    const onCrosshair = (param: MouseEventParams) => {
      const item = param.seriesData.get(candle) as CandlestickData | undefined
      setHoverDate(item ? timeKey(item.time) : null)
    }
    chart.subscribeCrosshairMove(onCrosshair)

    const scheme = window.matchMedia('(prefers-color-scheme: dark)')
    const onScheme = () => setTheme((n) => n + 1)
    scheme.addEventListener('change', onScheme)
    // The theme toggle writes data-theme on <html>; CSS updates itself, the canvas needs a nudge.
    const observer = new MutationObserver(onScheme)
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => {
      scheme.removeEventListener('change', onScheme)
      observer.disconnect()
      chart.unsubscribeCrosshairMove(onCrosshair)
      chart.remove()
      chartRef.current = null
      candleRef.current = null
      volumeRef.current = null
      maSeries.clear()
      avgLineRef.current = null
    }
  }, [])

  useEffect(() => {
    const chart = chartRef.current
    const candle = candleRef.current
    const volume = volumeRef.current
    if (!chart || !candle || !volume) return
    const c = themeColors()
    chart.applyOptions({
      layout: { background: { type: ColorType.Solid, color: c.surface }, textColor: c.muted },
      grid: { vertLines: { visible: false }, horzLines: { color: c.grid } },
      rightPriceScale: { borderColor: c.axis },
      timeScale: { borderColor: c.axis },
    })
    // Won prices in the millions need no decimals; sub-dollar coins need four.
    const last = bars.at(-1)?.close ?? 0
    const precision = last >= 1000 ? 0 : last >= 1 ? 2 : 4
    candle.applyOptions({
      upColor: c.up,
      downColor: c.down,
      wickUpColor: c.up,
      wickDownColor: c.down,
      priceFormat: { type: 'price', precision, minMove: 1 / 10 ** precision },
    })
    const candles: CandlestickData[] = bars.map((b) => ({
      time: b.date,
      open: b.open,
      high: b.high,
      low: b.low,
      close: b.close,
    }))
    const volumes: HistogramData[] = bars.map((b, i) => {
      const prev = i > 0 ? bars[i - 1].close : prevClose
      return { time: b.date, value: b.volume, color: translucent(b.close >= (prev ?? b.open) ? c.up : c.down) }
    })
    candle.setData(candles)
    volume.setData(volumes)
    chart.timeScale().fitContent()
  }, [bars, prevClose, theme])

  // One line series per enabled average, created on demand and removed when toggled off.
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    const c = themeColors()
    const wanted = new Set(ma.map((m) => m.n))
    for (const [n, series] of maRef.current) {
      if (!wanted.has(n)) {
        chart.removeSeries(series)
        maRef.current.delete(n)
      }
    }
    for (const m of ma) {
      let series = maRef.current.get(m.n)
      if (!series) {
        series = chart.addSeries(LineSeries, {
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        })
        maRef.current.set(m.n, series)
      }
      series.applyOptions({ color: c.resolve(m.cssVar), lineStyle: m.dash ? LineStyle.Dashed : LineStyle.Solid })
      const data: LineData[] = []
      m.values.forEach((v, i) => {
        const b = bars[i]
        if (v !== null && b) data.push({ time: b.date, value: v })
      })
      series.setData(data)
    }
  }, [bars, ma, theme])

  // My average cost as a dashed price line while the symbol is held.
  useEffect(() => {
    const candle = candleRef.current
    if (!candle) return
    if (avgLineRef.current) {
      candle.removePriceLine(avgLineRef.current)
      avgLineRef.current = null
    }
    if (avgCost === undefined) return
    const c = themeColors()
    avgLineRef.current = candle.createPriceLine({
      price: avgCost,
      color: c.ink2,
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      title: '내 평균',
    })
  }, [avgCost, theme])

  // The same legend as the line view, so switching views does not drop the key to the colors.
  const legend: { label: string; swatch: ReactNode }[] = [
    { label: '캔들 (상승·하락)', swatch: <CandleSwatch /> },
    ...ma.map((m) => ({
      label: MA_STYLE[m.n]?.label ?? `${m.n}일 평균`,
      swatch: <LineSwatch color={`var(${m.cssVar})`} dash={m.dash} />,
    })),
    { label: '거래량 (상승일·하락일)', swatch: <VolumeSwatch /> },
  ]
  if (avgCost !== undefined) legend.push({ label: '내 평균단가', swatch: <LineSwatch color="var(--ink-2)" dash="3 3" /> })

  // The bar the readout describes: the hovered one, else the last. A hover date that is no
  // longer in `bars` (range just changed) also falls back to the last bar.
  const hovered = hoverDate === null ? -1 : bars.findIndex((b) => b.date === hoverDate)
  const focusIndex = hovered >= 0 ? hovered : bars.length - 1
  const focus = bars[focusIndex]

  return (
    <div>
      <div className="relative">
        <div ref={container} className="h-80 w-full" role="img" aria-label="캔들 차트" />
        {focus && (
          // Top-left, clear of the price scale on the right; pointer events pass through to the canvas.
          // lightweight-charts stacks its canvases at z-index 1 and 2 with an opaque background, so
          // the readout needs its own z-index or it is painted over (DOM order alone is not enough).
          <div className="pointer-events-none absolute top-2 left-2 z-10 max-w-[calc(100%-88px)] rounded-md bg-surface/85 px-2 py-1">
            <BarReadout
              bar={focus}
              prevClose={focusIndex > 0 ? bars[focusIndex - 1].close : prevClose}
              ma={ma.map((m) => ({ n: m.n, value: m.values[focusIndex] ?? null }))}
              format={format}
            />
          </div>
        )}
      </div>
      <ChartLegend items={legend} />
    </div>
  )
}
