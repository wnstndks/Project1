import { Link } from 'react-router-dom'
import {
  Area,
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

import type { HistoryPoint } from '../api/client'
import { useMoney } from '../lib/currency'
import { formatDate } from '../lib/format'
import { Swatch } from './ui'

const SERIES = [
  { key: 'value', label: '평가금액', color: 'var(--series-1)', dashed: false },
  { key: 'cost', label: '투자원금', color: 'var(--series-2)', dashed: true },
] as const

type Row = { date: string; value: number; cost: number }

/**
 * Portfolio value vs. invested cost in the selected currency. No grid or Y axis: the tooltip
 * gives values, and the latest value is written at the end of the line.
 */
export function ValueHistoryChart({ points }: { points: HistoryPoint[] }) {
  const { pick, compact } = useMoney()
  const rows: Row[] = points.map((p) => ({
    date: p.date,
    value: pick(p.market_value, p.market_value_krw),
    cost: pick(p.cost_basis, p.cost_basis_krw),
  }))
  const last = rows.at(-1)

  return (
    <div>
      <ul className="mb-2 flex gap-4 text-xs text-ink-2" aria-label="범례">
        {SERIES.map((s) => (
          <li key={s.key} className="flex items-center gap-1.5">
            <Swatch color={s.color} dashed={s.dashed} />
            {s.label}
          </li>
        ))}
      </ul>
      <div className="h-56" role="img" aria-label="자산 추이 차트">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 8, right: 4, bottom: 0, left: 4 }}>
            <XAxis
              dataKey="date"
              tickLine={false}
              axisLine={false}
              tick={{ fill: 'var(--muted)', fontSize: 11 }}
              tickFormatter={(d: string) => formatDate(d, 'short')}
              minTickGap={40}
            />
            {/* Hidden, but keeps the auto domain so the lines are not squashed against zero. */}
            <YAxis hide domain={['auto', 'auto']} />
            <Tooltip
              content={(props) => <HistoryTooltip {...props} />}
              cursor={{ stroke: 'var(--axis)', strokeWidth: 1 }}
            />
            <Area
              dataKey="value"
              type="monotone"
              stroke="var(--series-1)"
              strokeWidth={2}
              fill="var(--series-1)"
              fillOpacity={0.12}
              activeDot={{ r: 4, stroke: 'var(--surface)', strokeWidth: 2 }}
              isAnimationActive={false}
            />
            <Line
              dataKey="cost"
              type="stepAfter"
              stroke="var(--series-2)"
              strokeWidth={1.5}
              strokeDasharray="4 4"
              dot={false}
              activeDot={{ r: 4, stroke: 'var(--surface)', strokeWidth: 2 }}
              isAnimationActive={false}
            />
            {last && (
              <>
                <ReferenceDot x={last.date} y={last.value} r={3.5} fill="var(--series-1)" stroke="var(--surface)" strokeWidth={2} />
                {/* An invisible line at the last value carries its label, right-aligned just above the line end. */}
                <ReferenceLine
                  y={last.value}
                  stroke="none"
                  label={{
                    value: compact(last.value),
                    position: 'insideRight',
                    dy: -10,
                    fill: 'var(--ink)',
                    fontSize: 11,
                    fontWeight: 600,
                  }}
                />
              </>
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

/**
 * Shown instead of the chart while the history is shorter than a week. Screenshot imports are
 * dated the day they were imported, so the usual fix is to correct the trade dates.
 */
export function HistoryEmpty({ days }: { days: number }) {
  return (
    <p className="py-4 text-[15px] leading-relaxed text-ink-2">
      거래 기록이 <span className="num font-semibold text-ink">{days}일</span>뿐이라 추이가 아직 없어요. 스크린샷으로
      가져온 거래는 가져온 날짜로 기록돼요.{' '}
      <Link to="/transactions" className="text-accent underline">
        거래 페이지
      </Link>
      에서 실제 매수일로 고치면 과거 추이가 보여요.
    </p>
  )
}

function HistoryTooltip({ active, payload, label }: TooltipContentProps) {
  const { format } = useMoney()
  if (!active || !payload?.length) return null
  const row = payload[0].payload as Row
  return (
    <div className="rounded-xl border border-line bg-surface px-3 py-2 text-xs shadow-lg">
      <div className="mb-1 text-muted">{formatDate(String(label), 'long')}</div>
      {SERIES.map((s) => (
        <div key={s.key} className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-1.5 text-ink-2">
            <Swatch color={s.color} dashed={s.dashed} />
            {s.label}
          </span>
          <span className="num font-semibold text-ink">{format(row[s.key])}</span>
        </div>
      ))}
    </div>
  )
}
