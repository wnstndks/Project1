import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from 'recharts'

import type { HistoryPoint } from '../api/client'
import { formatKrw, formatKrwCompact } from '../lib/format'

const SERIES = [
  { key: 'value', label: '평가금액', color: 'var(--series-1)' },
  { key: 'cost', label: '투자원금', color: 'var(--series-2)' },
] as const

type Row = { date: string; value: number; cost: number }

/** Portfolio value vs. invested cost, both in KRW on one axis. */
export function ValueHistoryChart({ points }: { points: HistoryPoint[] }) {
  const rows: Row[] = points.map((p) => ({
    date: p.date,
    value: p.market_value_krw,
    cost: p.cost_basis_krw,
  }))

  return (
    <div>
      <ul className="mb-3 flex gap-4 text-xs text-ink-2" aria-label="범례">
        {SERIES.map((s) => (
          <li key={s.key} className="flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-4 rounded" style={{ background: s.color }} />
            {s.label}
          </li>
        ))}
      </ul>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--grid)" />
            <XAxis
              dataKey="date"
              tickLine={false}
              axisLine={{ stroke: 'var(--axis)' }}
              tick={{ fill: 'var(--muted)', fontSize: 11 }}
              tickFormatter={(d: string) => d.slice(2, 7).replace('-', '.')}
              minTickGap={40}
            />
            <YAxis
              width={56}
              tickLine={false}
              axisLine={false}
              tick={{ fill: 'var(--muted)', fontSize: 11 }}
              tickFormatter={formatKrwCompact}
              domain={['auto', 'auto']}
            />
            <Tooltip
              content={HistoryTooltip}
              cursor={{ stroke: 'var(--axis)', strokeWidth: 1 }}
            />
            <Area
              dataKey="value"
              type="monotone"
              stroke="var(--series-1)"
              strokeWidth={2}
              fill="var(--series-1)"
              fillOpacity={0.1}
              activeDot={{ r: 4, stroke: 'var(--surface)', strokeWidth: 2 }}
              isAnimationActive={false}
            />
            <Line
              dataKey="cost"
              type="stepAfter"
              stroke="var(--series-2)"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, stroke: 'var(--surface)', strokeWidth: 2 }}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function HistoryTooltip({ active, payload, label }: TooltipContentProps) {
  if (!active || !payload?.length) return null
  const row = payload[0].payload as Row
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-sm">
      <div className="mb-1 text-muted">{String(label)}</div>
      {SERIES.map((s) => (
        <div key={s.key} className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-1.5 text-ink-2">
            <span className="inline-block h-0.5 w-3 rounded" style={{ background: s.color }} />
            {s.label}
          </span>
          <span className="num font-semibold text-ink">{formatKrw(row[s.key])}</span>
        </div>
      ))}
    </div>
  )
}
