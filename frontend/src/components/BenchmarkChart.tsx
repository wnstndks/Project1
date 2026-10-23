import {
  Area,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  usePlotArea,
  useXAxisScale,
  useYAxisScale,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from 'recharts'

import type { Benchmark } from '../api/client'
import {
  benchmarkLabel,
  benchmarkStyle,
  buildBenchmarkRows,
  lastValues,
  MINE_STYLE,
  spreadLabels,
  type BenchmarkRow,
} from '../lib/benchmarks'
import { useMoney } from '../lib/currency'
import { Swatch } from './ui'

type SeriesSpec = { key: string; label: string; color: string; dash?: string }

/** Room on the right for the value written at the end of each line. */
const LABEL_MARGIN = 72
const LABEL_GAP = 14

/**
 * My portfolio value (filled area) beside each selected benchmark bought and sold with the same
 * won flows on the same days. Every line is identified three ways: color, dash pattern and the
 * ticker + last value written at its end, so none relies on color alone. No Y axis: the end labels
 * and tooltip carry the numbers.
 */
export function BenchmarkChart({ data, selected }: { data: Benchmark; selected: string[] }) {
  const { pick, format, compact } = useMoney()
  const shown = data.benchmarks.filter((b) => selected.includes(b.symbol))
  const rows = buildBenchmarkRows(data.mine, shown, pick)
  const series: SeriesSpec[] = [
    { key: 'mine', label: '내 자산', color: `var(${MINE_STYLE.cssVar})` },
    ...shown.map((b) => {
      const s = benchmarkStyle(b.symbol)
      return { key: b.symbol, label: benchmarkLabel(b.symbol), color: `var(${s.cssVar})`, dash: s.dash }
    }),
  ]
  const names = new Map(data.benchmarks.map((b) => [b.symbol, b.name_ko]))

  return (
    <div>
      <ul className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2" aria-label="범례">
        {series.map((s) => (
          <li key={s.key} className="flex items-center gap-1.5">
            <Swatch color={s.color} dashed={s.dash !== undefined} />
            {s.label}
            {s.key !== 'mine' && <span className="text-muted">{names.get(s.key)}</span>}
          </li>
        ))}
      </ul>
      <div className="h-64" role="img" aria-label="같은 날 같은 돈을 넣었다면 비교 차트">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 8, right: LABEL_MARGIN, bottom: 0, left: 4 }}>
            <XAxis
              dataKey="date"
              tickLine={false}
              axisLine={false}
              tick={{ fill: 'var(--muted)', fontSize: 11 }}
              tickFormatter={(d: string) => d.slice(2, 7).replace('-', '.')}
              minTickGap={40}
            />
            <YAxis hide domain={['auto', 'auto']} />
            <Tooltip
              content={(props) => <BenchmarkTooltip {...props} series={series} format={format} />}
              cursor={{ stroke: 'var(--axis)', strokeWidth: 1 }}
            />
            <Area
              dataKey="mine"
              type="monotone"
              stroke={series[0].color}
              strokeWidth={2.5}
              fill={series[0].color}
              fillOpacity={0.12}
              connectNulls
              activeDot={{ r: 4, stroke: 'var(--surface)', strokeWidth: 2 }}
              isAnimationActive={false}
            />
            {series.slice(1).map((s) => (
              <Line
                key={s.key}
                dataKey={s.key}
                type="monotone"
                stroke={s.color}
                strokeWidth={1.75}
                strokeDasharray={s.dash}
                dot={false}
                connectNulls
                activeDot={{ r: 4, stroke: 'var(--surface)', strokeWidth: 2 }}
                isAnimationActive={false}
              />
            ))}
            <EndLabels rows={rows} series={series} format={compact} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

/**
 * Ticker and last value at the end of each line, nudged apart so they never overlap. Rendered
 * inside the chart so it can use the axis scales; the chart's right margin leaves it room.
 */
function EndLabels({ rows, series, format }: { rows: BenchmarkRow[]; series: SeriesSpec[]; format: (v: number) => string }) {
  const xScale = useXAxisScale()
  const yScale = useYAxisScale()
  const plot = usePlotArea()
  if (!xScale || !yScale || !plot) return null
  const last = lastValues(rows, series.map((s) => s.key))
  const placed = spreadLabels(
    last.flatMap((l) => {
      const x = xScale(l.date)
      const y = yScale(l.value)
      return x === undefined || y === undefined ? [] : [{ ...l, x, y }]
    }),
    LABEL_GAP,
    plot.y + 6,
    plot.y + plot.height - 6,
  )
  return (
    <g aria-hidden="true">
      {placed.map((l) => {
        const s = series.find((x) => x.key === l.key)
        return (
          <text key={l.key} x={l.x + 6} y={l.y} dominantBaseline="middle" fontSize={11} fill="var(--ink-2)">
            <tspan fill={s?.color} fontWeight={600}>
              {s?.label}
            </tspan>{' '}
            {format(l.value)}
          </text>
        )
      })}
    </g>
  )
}

function BenchmarkTooltip({
  active,
  payload,
  label,
  series,
  format,
}: TooltipContentProps & { series: SeriesSpec[]; format: (v: number) => string }) {
  if (!active || !payload?.length) return null
  const row = payload[0].payload as BenchmarkRow
  return (
    <div className="rounded-xl border border-line bg-surface px-3 py-2 text-xs shadow-lg">
      <div className="mb-1 text-muted">{String(label)}</div>
      {series.map((s) => {
        const v = row[s.key]
        if (typeof v !== 'number') return null
        return (
          <div key={s.key} className="flex items-center justify-between gap-4">
            <span className="flex items-center gap-1.5 text-ink-2">
              <Swatch color={s.color} dashed={s.dash !== undefined} />
              {s.label}
            </span>
            <span className="num font-semibold text-ink">{format(v)}</span>
          </div>
        )
      })}
    </div>
  )
}
