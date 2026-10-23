import type { ReactNode } from 'react'
import {
  Area,
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from 'recharts'

import { COVERAGE_PHRASE } from '../lib/forecast'
import { formatDate, formatKrwCompact, isoDate } from '../lib/format'
import type { Extreme } from '../lib/indicators'
import {
  buildRows,
  DAY_MS,
  dayStart,
  isNear,
  labelSide,
  MA_STYLE,
  priceDomain,
  tickLabel,
  todayStart,
  type MaLine,
  type ChartBar,
  type ForecastPoint,
  type Row,
} from '../lib/priceChart'
import { BandSwatch, ChartLegend, LineSwatch, VolumeSwatch } from './ui'

type Props = {
  /** Visible bars, already in the display currency. */
  bars: ChartBar[]
  /** Enabled moving averages, values aligned with `bars`. */
  ma: MaLine[]
  horizons?: ForecastPoint[]
  avgCost?: number
  extremes?: Extreme | null
  format: (v: number) => string
  compact: (v: number) => string
}

export const BAND_LEGEND = `예측 범위(${COVERAGE_PHRASE}) · 점선은 예상 중간값`
export const NO_DIRECTION_NOTE = '예측 띠는 변동 폭만 참고하세요. 오를지 내릴지는 우위 없음입니다.'

export function PriceForecastChart({ bars, ma, horizons = [], avgCost, extremes, format, compact }: Props) {
  const rows = buildRows(bars, ma, horizons)
  const first = rows[0]?.t ?? 0
  const lastBar = bars.at(-1)
  const lastT = rows.at(-1)?.t ?? 0
  const inWindow = (date: string) =>
    lastBar !== undefined && dayStart(date) >= first && dayStart(date) <= dayStart(lastBar.date)
  const showHigh = extremes !== null && extremes !== undefined && inWindow(extremes.highDate)
  const showLow = extremes !== null && extremes !== undefined && inWindow(extremes.lowDate)

  // Decide the average-cost line on the price data alone, then let the marks that are shown pad the axis.
  const dataDomain = priceDomain(rows)
  const dataSpan = dataDomain[1] - dataDomain[0]
  const showAvg = avgCost !== undefined && isNear(avgCost, dataDomain[0], dataDomain[1], dataSpan)
  const extras = [
    ...(showAvg ? [avgCost] : []),
    ...(showHigh ? [extremes.high] : []),
    ...(showLow ? [extremes.low] : []),
  ]
  const domain = priceDomain(rows, extras)
  const volumeMax = Math.max(0, ...rows.map((r) => r.volume ?? 0))
  const hasForecast = rows.length > bars.length
  // The band is honest about spread only unless every horizon's direction passed the live verdict.
  const noDirection = hasForecast && !horizons.every((h) => h.direction_edge === true)

  const todayT = todayStart()

  // Legend: the series only. Marks with their own label in the plot (내 평균, 52주) are not repeated.
  const legend: { label: string; swatch: ReactNode }[] = [
    { label: '종가', swatch: <LineSwatch color="var(--series-1)" width={2} /> },
    ...ma.map((m) => {
      const s = MA_STYLE[m.n] ?? { cssVar: '--muted', label: `${m.n}일 평균` }
      return { label: s.label, swatch: <LineSwatch color={`var(${s.cssVar})`} dash={s.dash} /> }
    }),
    { label: '거래량 (상승일·하락일)', swatch: <VolumeSwatch /> },
  ]
  if (hasForecast) legend.push({ label: BAND_LEGEND, swatch: <BandSwatch /> })

  return (
    <div>
      {/* One named image for assistive tech; the legend below carries the series in text. */}
      <div className="h-80" role="img" aria-label="가격과 예측 차트">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 20, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--grid)" />
            <XAxis
              dataKey="t"
              type="number"
              scale="time"
              domain={['dataMin', 'dataMax']}
              tickLine={false}
              axisLine={{ stroke: 'var(--axis)' }}
              tick={{ fill: 'var(--muted)', fontSize: 11 }}
              tickFormatter={(t: number) => tickLabel(t, (lastT - first) / DAY_MS)}
              minTickGap={48}
            />
            <YAxis
              width={64}
              tickLine={false}
              axisLine={false}
              tick={{ fill: 'var(--muted)', fontSize: 11 }}
              tickFormatter={compact}
              domain={domain}
              allowDataOverflow
            />
            {/* Volume gets its own hidden scale so the bars form a strip in the bottom fifth of the plot. */}
            <YAxis yAxisId="volume" orientation="right" hide domain={[0, volumeMax * 5 || 1]} />
            <Tooltip
              content={(props) => <PriceTooltip {...props} ma={ma} format={format} />}
              cursor={{ stroke: 'var(--axis)', strokeWidth: 1 }}
            />
            <Bar yAxisId="volume" dataKey="volume" maxBarSize={8} fillOpacity={0.5} isAnimationActive={false}>
              {rows.map((r) => (
                <Cell key={r.t} fill={r.up ? 'var(--gain-mark)' : 'var(--loss-mark)'} />
              ))}
            </Bar>
            <Area
              dataKey="band"
              stroke="none"
              fill="var(--series-2)"
              fillOpacity={0.18}
              connectNulls
              isAnimationActive={false}
              activeDot={false}
            />
            {ma.map((m) => {
              const s = MA_STYLE[m.n] ?? { cssVar: '--muted' }
              return (
                <Line
                  key={m.n}
                  dataKey={`ma${m.n}`}
                  stroke={`var(${s.cssVar})`}
                  strokeWidth={1.25}
                  strokeDasharray={s.dash}
                  dot={false}
                  activeDot={false}
                  isAnimationActive={false}
                />
              )
            })}
            <Line
              dataKey="close"
              stroke="var(--series-1)"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, stroke: 'var(--surface)', strokeWidth: 2 }}
              isAnimationActive={false}
            />
            <Line
              dataKey="mid"
              stroke="var(--series-2)"
              strokeWidth={2}
              strokeDasharray="4 3"
              dot={{ r: 4, stroke: 'var(--surface)', strokeWidth: 2, fill: 'var(--series-2)' }}
              activeDot={{ r: 4, stroke: 'var(--surface)', strokeWidth: 2 }}
              connectNulls
              isAnimationActive={false}
            />
            <ReferenceLine
              x={todayT}
              stroke="var(--axis)"
              strokeDasharray="3 3"
              ifOverflow="extendDomain"
              label={{ value: '오늘', position: 'insideTopRight', fill: 'var(--muted)', fontSize: 11 }}
            />
            {showAvg && (
              <ReferenceLine
                y={avgCost}
                stroke="var(--ink-2)"
                strokeDasharray="3 3"
                label={{ value: '내 평균', position: 'insideBottomRight', fill: 'var(--ink-2)', fontSize: 11 }}
              />
            )}
            {showHigh && (
              <ReferenceDot
                x={dayStart(extremes.highDate)}
                y={extremes.high}
                r={4}
                fill="var(--surface)"
                stroke="var(--ink-2)"
                strokeWidth={2}
                label={{ value: '52주 최고', position: 'top', fill: 'var(--ink-2)', fontSize: 11 }}
              />
            )}
            {showLow && (
              // Beside the dot, not under it: below is the volume strip.
              <ReferenceDot
                x={dayStart(extremes.lowDate)}
                y={extremes.low}
                r={4}
                fill="var(--surface)"
                stroke="var(--ink-2)"
                strokeWidth={2}
                label={{
                  value: '52주 최저',
                  position: labelSide(dayStart(extremes.lowDate), first, lastT),
                  fill: 'var(--ink-2)',
                  fontSize: 11,
                }}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <ChartLegend items={legend} />
      {noDirection && <p className="mt-2 text-xs text-muted">{NO_DIRECTION_NOTE}</p>}
    </div>
  )
}

function PriceTooltip({
  active,
  payload,
  label,
  ma,
  format,
}: TooltipContentProps & { ma: MaLine[]; format: (v: number) => string }) {
  if (!active || !payload?.length) return null
  const row = payload[0].payload as Row
  const date = formatDate(isoDate(new Date(Number(label))), 'long')
  const forecast = row.close === undefined
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-sm">
      <div className="mb-1 text-muted">{forecast ? `${date} 예측` : date}</div>
      {forecast ? (
        <>
          {row.mid !== undefined && <TipRow label="예상 중간값" value={format(row.mid)} strong />}
          {row.band && (
            <TipRow label={`${COVERAGE_PHRASE} 범위`} value={`${format(row.band[0])}~${format(row.band[1])}`} />
          )}
        </>
      ) : (
        <>
          <TipRow label="종가" value={format(row.close!)} strong />
          {ma.map((m) => {
            const v = row[`ma${m.n}`]
            return v === undefined ? null : (
              <TipRow key={m.n} label={MA_STYLE[m.n]?.label ?? `${m.n}일 평균`} value={format(v)} />
            )
          })}
          {row.volume !== undefined && <TipRow label="거래량" value={formatKrwCompact(row.volume)} />}
        </>
      )}
    </div>
  )
}

function TipRow({ label, value, strong = false }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-ink-2">{label}</span>
      <span className={`num text-ink ${strong ? 'font-semibold' : ''}`}>{value}</span>
    </div>
  )
}
