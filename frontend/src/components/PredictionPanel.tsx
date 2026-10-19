import {
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from 'recharts'

import { ApiError, type Forecast } from '../api/client'
import { useBacktest, useForecast, useTraining } from '../api/hooks'
import { useMoney } from '../lib/currency'
import { formatPct } from '../lib/format'
import { ErrorBox, Muted } from './ui'

type Row = { date: string; actual?: number; predicted?: number }

const SERIES = [
  { key: 'actual', label: '실제 종가', color: 'var(--series-1)' },
  { key: 'predicted', label: 'LSTM 예측', color: 'var(--series-2)' },
] as const

export function PredictionPanel({ symbol, fx }: { symbol: string; fx?: number }) {
  const forecast = useForecast(symbol)
  const { job, start } = useTraining(symbol)
  const running = job?.state === 'running' || start.isPending
  const notTrained = forecast.error instanceof ApiError && forecast.error.status === 404

  const trainButton = (
    <button
      type="button"
      disabled={running}
      onClick={() => start.mutate()}
      className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium hover:bg-hover disabled:opacity-50"
    >
      {running ? '학습 중…' : notTrained ? '모델 학습하기' : '다시 학습'}
    </button>
  )

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-muted">
          과거 60일 데이터로 향후 5거래일 종가를 예측합니다. 참고용이며 투자 조언이 아닙니다.
        </p>
        {trainButton}
      </div>

      {running && (
        <p className="text-sm text-ink-2">
          학습에는 1~3분 정도 걸립니다. {job?.log.at(-1) && <span className="text-muted">({job.log.at(-1)})</span>}
        </p>
      )}
      {job?.state === 'failed' && <ErrorBox error={`학습 실패: ${job.error}`} />}
      {start.error && <ErrorBox error={start.error} />}

      {notTrained ? (
        !running && <Muted>아직 학습된 모델이 없습니다. 위 버튼으로 학습을 시작하세요.</Muted>
      ) : forecast.error ? (
        <ErrorBox error={forecast.error} />
      ) : !forecast.data ? (
        <Muted>불러오는 중…</Muted>
      ) : (
        <ForecastView data={forecast.data} symbol={symbol} fx={fx} />
      )}
    </div>
  )
}

function ForecastView({ data, symbol, fx }: { data: Forecast; symbol: string; fx?: number }) {
  const { currency, format, compact } = useMoney()
  const backtest = useBacktest(symbol, true)
  // Prices are USD; in KRW mode convert at today's rate (the best guess for future rates too).
  const conv = (usd: number) => (currency === 'KRW' && fx ? usd * fx : usd)

  const rows: Row[] = [
    ...data.recent.map((p) => ({ date: p.date, actual: conv(p.close) })),
    ...data.forecast.map((p) => ({ date: p.date, predicted: conv(p.price) })),
  ]
  // Start the forecast line at the last actual close so the two lines connect.
  const lastActual = rows[data.recent.length - 1]
  if (lastActual) lastActual.predicted = lastActual.actual

  const backtestRows: Row[] = (backtest.data ?? []).map((p) => ({
    date: p.date,
    actual: conv(p.actual),
    predicted: conv(p.predicted),
  }))

  const day1 = data.metrics.by_horizon[0]
  const day5 = data.metrics.by_horizon.at(-1)!

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Legend />
          <PriceChart rows={rows} compact={compact} format={format} />
        </div>
        <table className="num h-fit w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs text-muted">
              <th className="py-2 font-medium">예측일</th>
              <th className="py-2 text-right font-medium">예측가</th>
              <th className="py-2 text-right font-medium">변화</th>
            </tr>
          </thead>
          <tbody>
            {data.forecast.map((p) => (
              <tr key={p.date} className="border-b border-line last:border-0">
                <td className="py-2 text-ink-2">{p.date.slice(5)}</td>
                <td className="py-2 text-right">{format(conv(p.price))}</td>
                <td className={`py-2 text-right ${p.return_pct >= 0 ? 'text-gain' : 'text-loss'}`}>
                  {formatPct(p.return_pct)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold text-ink-2">
          테스트 구간 성능 ({data.test_range[0]} ~ {data.test_range[1]}, {data.metrics.samples}일)
        </h3>
        <div className="-mx-5 overflow-x-auto">
          <table className="num w-full min-w-[520px] text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs text-muted">
                <th className="px-5 py-2 font-medium">지표</th>
                <th className="px-3 py-2 text-right font-medium">LSTM (1일)</th>
                <th className="px-3 py-2 text-right font-medium">기준선 (1일)</th>
                <th className="px-3 py-2 text-right font-medium">LSTM (5일)</th>
                <th className="px-5 py-2 text-right font-medium">기준선 (5일)</th>
              </tr>
            </thead>
            <tbody>
              <MetricRow label="평균 오차율 (MAPE)" a={day1.model.mape} b={day1.baseline.mape} c={day5.model.mape} d={day5.baseline.mape} unit="%" lowerIsBetter />
              <MetricRow label="방향 적중률" a={day1.model.direction_acc} b={day1.baseline.direction_acc} c={day5.model.direction_acc} d={day5.baseline.direction_acc} unit="%" />
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-muted">
          기준선: 가격은 &lsquo;전일 종가 유지&rsquo;, 방향은 &lsquo;학습 기간에 더 많았던 방향&rsquo;. 기준선보다 나은
          값을 굵게 표시합니다. 학습 {data.trained_at.slice(0, 10)}.
        </p>
      </div>

      {backtestRows.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-semibold text-ink-2">백테스트: 1일 뒤 예측 vs 실제</h3>
          <Legend />
          <PriceChart rows={backtestRows} compact={compact} format={format} height="h-56" />
        </div>
      )}
    </div>
  )
}

function MetricRow({ label, a, b, c, d, unit, lowerIsBetter = false }: {
  label: string
  a: number
  b: number
  c: number
  d: number
  unit: string
  lowerIsBetter?: boolean
}) {
  // Compare what is shown: a difference hidden by rounding must not be highlighted.
  const better = (model: number, base: number) => {
    const [m, b] = [Number(model.toFixed(2)), Number(base.toFixed(2))]
    return lowerIsBetter ? m < b : m > b
  }
  const cell = (v: number, bold: boolean) => (
    <span className={bold ? 'font-semibold text-ink' : 'text-ink-2'}>
      {v.toFixed(2)}
      {unit}
    </span>
  )
  return (
    <tr className="border-b border-line last:border-0">
      <td className="px-5 py-2 text-ink-2">{label}</td>
      <td className="px-3 py-2 text-right">{cell(a, better(a, b))}</td>
      <td className="px-3 py-2 text-right">{cell(b, false)}</td>
      <td className="px-3 py-2 text-right">{cell(c, better(c, d))}</td>
      <td className="px-5 py-2 text-right">{cell(d, false)}</td>
    </tr>
  )
}

function Legend() {
  return (
    <ul className="mb-3 flex gap-4 text-xs text-ink-2" aria-label="범례">
      {SERIES.map((s) => (
        <li key={s.key} className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4 rounded" style={{ background: s.color }} />
          {s.label}
        </li>
      ))}
    </ul>
  )
}

function PriceChart({ rows, compact, format, height = 'h-64' }: {
  rows: Row[]
  compact: (v: number) => string
  format: (v: number) => string
  height?: string
}) {
  return (
    <div className={height}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--grid)" />
          <XAxis
            dataKey="date"
            tickLine={false}
            axisLine={{ stroke: 'var(--axis)' }}
            tick={{ fill: 'var(--muted)', fontSize: 11 }}
            tickFormatter={(d: string) => d.slice(5).replace('-', '.')}
            minTickGap={40}
          />
          <YAxis
            width={60}
            tickLine={false}
            axisLine={false}
            tick={{ fill: 'var(--muted)', fontSize: 11 }}
            tickFormatter={compact}
            domain={['auto', 'auto']}
          />
          <Tooltip
            content={(props) => <ChartTooltip {...props} format={format} />}
            cursor={{ stroke: 'var(--axis)', strokeWidth: 1 }}
          />
          {SERIES.map((s) => (
            <Line
              key={s.key}
              dataKey={s.key}
              type="monotone"
              stroke={s.color}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, stroke: 'var(--surface)', strokeWidth: 2 }}
              connectNulls={false}
              isAnimationActive={false}
            />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

function ChartTooltip({ active, payload, label, format }: TooltipContentProps & { format: (v: number) => string }) {
  if (!active || !payload?.length) return null
  const row = payload[0].payload as Row
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-sm">
      <div className="mb-1 text-muted">{String(label)}</div>
      {SERIES.filter((s) => row[s.key] !== undefined).map((s) => (
        <div key={s.key} className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-1.5 text-ink-2">
            <span className="inline-block h-0.5 w-3 rounded" style={{ background: s.color }} />
            {s.label}
          </span>
          <span className="num font-semibold text-ink">{format(row[s.key]!)}</span>
        </div>
      ))}
    </div>
  )
}
