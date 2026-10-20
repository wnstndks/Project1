import { useState } from 'react'
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

import { ApiError, type HorizonForecast, type SymbolForecast } from '../api/client'
import {
  useForecast,
  useForecastBacktest,
  useForecastStatus,
  useForecastTraining,
  useTrackRecord,
} from '../api/hooks'
import { useMoney } from '../lib/currency'
import { HORIZON_LABEL } from '../lib/forecast'
import { formatPct } from '../lib/format'
import { ErrorBox, Muted, SegmentedControl } from './ui'

const HORIZON_OPTIONS = Object.entries(HORIZON_LABEL).map(([value, label]) => ({ value, label }))

const ACTUAL = { label: '실제 종가', color: 'var(--series-1)' }
const FORECAST = { label: '예측 중앙값 · 10~90% 범위', color: 'var(--series-2)' }

type Row = { t: number; actual?: number; mid?: number; band?: [number, number] }

const day = (d: string) => new Date(`${d}T00:00:00`).getTime()
const pct = (v: number) => formatPct(v * 100)

/** Training controls for the one global model, shared by every page that shows forecasts. */
export function TrainButton({ notTrained }: { notTrained: boolean }) {
  const { running, start, status } = useForecastTraining()
  const job = status.data?.job
  return (
    <div className="space-y-2">
      <button
        type="button"
        disabled={running}
        onClick={() => start.mutate()}
        className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium hover:bg-hover disabled:opacity-50"
      >
        {running ? '학습 중…' : notTrained ? '예측 모델 학습하기' : '다시 학습'}
      </button>
      {running && job?.log.at(-1) && <p className="text-xs text-muted">{job.log.at(-1)}</p>}
      {job?.state === 'failed' && <ErrorBox error={`학습 실패: ${job.error}`} />}
      {start.error && <ErrorBox error={start.error} />}
    </div>
  )
}

export function ForecastPanel({ symbol, fx }: { symbol: string; fx?: number }) {
  const forecast = useForecast(symbol)
  const notTrained =
    forecast.error instanceof ApiError && forecast.error.status === 404 && /학습/.test(forecast.error.message)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-2xl text-xs text-muted">
          보유 종목과 참조 종목 약 60개를 함께 학습한 LightGBM 분위수 모델이 1일·1주·1개월 뒤 가격의 범위(10~90%)와
          오를 확률을 추정합니다. 기준선을 통계적으로 이기지 못하면 &lsquo;우위 없음&rsquo;으로 표시합니다. 참고용이며
          투자 조언이 아닙니다.
        </p>
        <TrainButton notTrained={notTrained} />
      </div>
      {notTrained ? (
        <Muted>아직 학습된 모델이 없습니다. 첫 학습은 시세를 내려받느라 몇 분 걸립니다.</Muted>
      ) : forecast.error ? (
        <ErrorBox error={forecast.error} />
      ) : !forecast.data ? (
        <Muted>예측을 계산하는 중… (처음에는 수십 초 걸릴 수 있습니다)</Muted>
      ) : (
        <ForecastView data={forecast.data} symbol={symbol} fx={fx} />
      )}
    </div>
  )
}

function ForecastView({ data, symbol, fx }: { data: SymbolForecast; symbol: string; fx?: number }) {
  const { currency, format, compact } = useMoney()
  // Prices are USD; in KRW mode convert at today's rate (the best guess for future rates too).
  const conv = (usd: number) => (currency === 'KRW' && fx ? usd * fx : usd)

  const rows: Row[] = data.recent.map((p) => ({ t: day(p.date), actual: conv(p.close) }))
  const last = rows.at(-1)
  if (last?.actual !== undefined) {
    // Start the fan at the last close so it grows out of the price line.
    last.mid = last.actual
    last.band = [last.actual, last.actual]
  }
  for (const h of data.horizons) {
    rows.push({ t: day(h.target_date), mid: conv(h.p50), band: [conv(h.p10), conv(h.p90)] })
  }

  return (
    <div className="space-y-6">
      <div>
        <Legend />
        <FanChart rows={rows} format={format} compact={compact} />
      </div>
      <HorizonTable horizons={data.horizons} format={(v) => format(conv(v))} />
      <p className="text-xs text-muted">
        기준선: 오를 확률은 학습 기간에 오른 날의 비율, 범위는 EWMA 변동성 + 두꺼운 꼬리(t분포). 데이터 기준일{' '}
        {data.horizons[0]?.as_of} 미국 장 마감, 학습 {data.trained_at.slice(0, 16).replace('T', ' ')}.
      </p>
      <Validation />
      <Backtest symbol={symbol} />
      <TrackRecord symbol={symbol} />
    </div>
  )
}

function Badge({ ok, yes, no }: { ok: boolean; yes: string; no: string }) {
  return (
    <span
      className={`inline-block rounded px-1.5 py-0.5 text-[11px] font-medium ${
        ok ? 'bg-hover text-ink' : 'text-muted'
      }`}
    >
      {ok ? `✓ ${yes}` : no}
    </span>
  )
}

function HorizonTable({ horizons, format }: { horizons: HorizonForecast[]; format: (v: number) => string }) {
  return (
    <div className="-mx-5 overflow-x-auto">
      <table className="num w-full min-w-[640px] text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs text-muted">
            <th className="px-5 py-2 font-medium">기간</th>
            <th className="px-3 py-2 font-medium">목표일</th>
            <th className="px-3 py-2 text-right font-medium">10~90% 범위</th>
            <th className="px-3 py-2 text-right font-medium">중앙값</th>
            <th className="px-3 py-2 text-right font-medium">오를 확률 (기준선)</th>
            <th className="px-5 py-2 font-medium">검증 결과</th>
          </tr>
        </thead>
        <tbody>
          {horizons.map((h) => (
            <tr key={h.horizon} className="border-b border-line align-top last:border-0">
              <td className="px-5 py-2.5 font-medium">{HORIZON_LABEL[h.horizon]}</td>
              <td className="px-3 py-2.5 text-ink-2">{h.target_date}</td>
              <td className="px-3 py-2.5 text-right">
                {format(h.p10)} ~ {format(h.p90)}
                <div className="text-xs text-muted">
                  {pct(h.p10 / h.base_price - 1)} ~ {pct(h.p90 / h.base_price - 1)}
                </div>
              </td>
              <td className="px-3 py-2.5 text-right">{format(h.p50)}</td>
              <td className="px-3 py-2.5 text-right">
                {(h.p_up * 100).toFixed(0)}%{' '}
                <span className="text-xs text-muted">({(h.baseline_p_up * 100).toFixed(0)}%)</span>
              </td>
              <td className="space-x-1 px-5 py-2.5">
                <Badge ok={h.direction_edge} yes="방향 우위" no="방향 우위 없음" />
                <Badge ok={h.range_edge} yes="범위 우위" no="범위는 기준선 수준" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Legend({ items = [ACTUAL, FORECAST] }: { items?: { label: string; color: string }[] }) {
  return (
    <ul className="mb-3 flex flex-wrap gap-4 text-xs text-ink-2" aria-label="범례">
      {items.map((s) => (
        <li key={s.label} className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4 rounded" style={{ background: s.color }} />
          {s.label}
        </li>
      ))}
    </ul>
  )
}

const dateTick = (t: number) => {
  const d = new Date(t)
  return `${d.getMonth() + 1}.${d.getDate()}`
}

function FanChart({ rows, format, compact }: {
  rows: Row[]
  format: (v: number) => string
  compact: (v: number) => string
}) {
  return (
    <div className="h-72">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--grid)" />
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={['dataMin', 'dataMax']}
            tickLine={false}
            axisLine={{ stroke: 'var(--axis)' }}
            tick={{ fill: 'var(--muted)', fontSize: 11 }}
            tickFormatter={dateTick}
            minTickGap={40}
          />
          <YAxis
            width={64}
            tickLine={false}
            axisLine={false}
            tick={{ fill: 'var(--muted)', fontSize: 11 }}
            tickFormatter={compact}
            domain={['auto', 'auto']}
          />
          <Tooltip
            content={(props) => <FanTooltip {...props} format={format} />}
            cursor={{ stroke: 'var(--axis)', strokeWidth: 1 }}
          />
          <Area
            dataKey="band"
            stroke="none"
            fill={FORECAST.color}
            fillOpacity={0.18}
            connectNulls
            isAnimationActive={false}
          />
          <Line
            dataKey="actual"
            stroke={ACTUAL.color}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, stroke: 'var(--surface)', strokeWidth: 2 }}
            isAnimationActive={false}
          />
          <Line
            dataKey="mid"
            stroke={FORECAST.color}
            strokeWidth={2}
            strokeDasharray="4 3"
            dot={{ r: 4, stroke: 'var(--surface)', strokeWidth: 2, fill: FORECAST.color }}
            connectNulls
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

function FanTooltip({ active, payload, label, format }: TooltipContentProps & { format: (v: number) => string }) {
  if (!active || !payload?.length) return null
  const row = payload[0].payload as Row
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-sm">
      <div className="mb-1 text-muted">{new Date(Number(label)).toLocaleDateString('ko-KR')}</div>
      {row.actual !== undefined && (
        <div className="flex justify-between gap-4">
          <span className="text-ink-2">{ACTUAL.label}</span>
          <span className="num font-semibold text-ink">{format(row.actual)}</span>
        </div>
      )}
      {row.mid !== undefined && row.actual === undefined && (
        <>
          <div className="flex justify-between gap-4">
            <span className="text-ink-2">중앙값</span>
            <span className="num font-semibold text-ink">{format(row.mid)}</span>
          </div>
          {row.band && (
            <div className="flex justify-between gap-4">
              <span className="text-ink-2">10~90%</span>
              <span className="num text-ink">
                {format(row.band[0])} ~ {format(row.band[1])}
              </span>
            </div>
          )}
        </>
      )}
    </div>
  )
}

type BacktestRow = { t: number; actual: number; mid: number; band: [number, number] }

/** Out-of-sample history: the range the model gave at the time vs what then happened. */
function Backtest({ symbol }: { symbol: string }) {
  const [horizon, setHorizon] = useState('1w')
  const backtest = useForecastBacktest(symbol, horizon)
  const points = backtest.data ?? []
  // Log returns from the API, shown as ordinary percentage changes.
  const simple = (r: number) => Math.expm1(r) * 100
  const rows: BacktestRow[] = points.map((p) => ({
    t: day(p.date),
    actual: simple(p.actual),
    mid: simple(p.q50),
    band: [simple(p.q10), simple(p.q90)],
  }))
  const inside = points.filter((p) => p.actual >= p.q10 && p.actual <= p.q90).length
  const holdoutStart = points.find((p) => p.segment === 'holdout')?.date

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-ink-2">과거 검증: 당시 예측 범위 vs 실제 수익률</h3>
        <SegmentedControl label="기간" options={HORIZON_OPTIONS} value={horizon} onChange={setHorizon} />
      </div>
      {backtest.error ? (
        <ErrorBox error={backtest.error} />
      ) : rows.length === 0 ? (
        <Muted>이 종목은 검증 구간 데이터가 없습니다.</Muted>
      ) : (
        <>
          <Legend
            items={[
              { label: '실제 수익률', color: ACTUAL.color },
              { label: '예측 10~90% 범위', color: FORECAST.color },
            ]}
          />
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid vertical={false} stroke="var(--grid)" />
                <XAxis
                  dataKey="t"
                  type="number"
                  scale="time"
                  domain={['dataMin', 'dataMax']}
                  tickLine={false}
                  axisLine={{ stroke: 'var(--axis)' }}
                  tick={{ fill: 'var(--muted)', fontSize: 11 }}
                  tickFormatter={(t: number) => new Date(t).toISOString().slice(2, 7).replace('-', '.')}
                  minTickGap={40}
                />
                <YAxis
                  width={48}
                  tickLine={false}
                  axisLine={false}
                  tick={{ fill: 'var(--muted)', fontSize: 11 }}
                  tickFormatter={(v: number) => `${v.toFixed(0)}%`}
                />
                <Tooltip
                  content={(props) => <BacktestTooltip {...props} />}
                  cursor={{ stroke: 'var(--axis)', strokeWidth: 1 }}
                />
                <Area dataKey="band" stroke="none" fill={FORECAST.color} fillOpacity={0.18} isAnimationActive={false} />
                <Line dataKey="actual" stroke={ACTUAL.color} strokeWidth={1.5} dot={false} isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-2 text-xs text-muted">
            실제 수익률이 예측 범위 안에 든 비율 {((inside / points.length) * 100).toFixed(0)}% (목표 80%,{' '}
            {points.length}건). 각 시점의 예측은 그 이전 데이터로만 학습한 모델이 낸 것이며
            {holdoutStart && `, ${holdoutStart} 이후는 학습에 쓰지 않은 최종 확인 구간입니다`}.
          </p>
        </>
      )}
    </div>
  )
}

function BacktestTooltip({ active, payload, label }: TooltipContentProps) {
  if (!active || !payload?.length) return null
  const row = payload[0].payload as BacktestRow
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-sm">
      <div className="mb-1 text-muted">{new Date(Number(label)).toLocaleDateString('ko-KR')} 예측</div>
      <div className="flex justify-between gap-4">
        <span className="text-ink-2">실제</span>
        <span className="num font-semibold text-ink">{formatPct(row.actual)}</span>
      </div>
      <div className="flex justify-between gap-4">
        <span className="text-ink-2">예측 범위</span>
        <span className="num text-ink">
          {formatPct(row.band[0])} ~ {formatPct(row.band[1])}
        </span>
      </div>
    </div>
  )
}

type Score = { coverage: number; brier: number; hit_rate: number }

/** Out-of-sample scores of the model and its baselines, straight from the training report. */
function Validation() {
  const status = useForecastStatus()
  const report = status.data?.report as
    | {
        configs_tried?: number
        horizons: Record<string, { scores: Record<string, Record<string, Score>> }>
      }
    | undefined
  if (!report) return null
  const rows = Object.entries(report.horizons)
  const n = (v: number, digits = 3) => v.toFixed(digits)
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold text-ink-2">검증 성적 (표본 외 · 전체 학습 종목)</h3>
      <div className="-mx-5 overflow-x-auto">
        <table className="num w-full min-w-[560px] text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs text-muted">
              <th className="px-5 py-2 font-medium">기간</th>
              <th className="px-3 py-2 text-right font-medium">범위 적중 (목표 80%)</th>
              <th className="px-3 py-2 text-right font-medium">방향 적중률</th>
              <th className="px-5 py-2 text-right font-medium">Brier (낮을수록 좋음)</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([h, r]) => {
              const wf = r.scores.walk_forward
              if (!wf) return null
              const m = wf.gbdt
              const base = wf.climatology
              const vol = wf.ewma_t
              return (
                <tr key={h} className="border-b border-line last:border-0">
                  <td className="px-5 py-2 font-medium">{HORIZON_LABEL[h]}</td>
                  <td className="px-3 py-2 text-right">
                    {(m.coverage * 100).toFixed(0)}%{' '}
                    <span className="text-xs text-muted">(기준선 {(vol.coverage * 100).toFixed(0)}%)</span>
                  </td>
                  <td className="px-3 py-2 text-right">
                    {(m.hit_rate * 100).toFixed(1)}%{' '}
                    <span className="text-xs text-muted">(기준선 {(base.hit_rate * 100).toFixed(1)}%)</span>
                  </td>
                  <td className="px-5 py-2 text-right">
                    {n(m.brier)} <span className="text-xs text-muted">(기준선 {n(base.brier)})</span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-muted">
        각 분기를 그 이전 데이터로만 학습해 예측한 결과(purged walk-forward)입니다. 방향 기준선은 &lsquo;학습 기간에
        오른 날 비율&rsquo;, 범위 기준선은 EWMA 변동성 모델입니다. 우위 판정은 Diebold-Mariano 검정(다중검정 보정,
        설정 {report.configs_tried ?? 1}회 시도 반영), 연도별 일관성, 최종 확인 구간을 모두 통과해야 합니다.
      </p>
    </div>
  )
}

/** Live forecasts as they were served, scored once their target dates passed. */
function TrackRecord({ symbol }: { symbol: string }) {
  const record = useTrackRecord(symbol)
  if (!record.data) return null
  const { summary, pending } = record.data
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold text-ink-2">실전 기록</h3>
      {summary.length === 0 ? (
        <Muted>
          아직 채점된 예측이 없습니다. 예측은 처음 보여 준 그대로 저장되고 목표일이 지나면 채점됩니다(대기 {pending}건).
        </Muted>
      ) : (
        <ul className="space-y-1 text-sm">
          {summary.map((s) => (
            <li key={s.horizon} className="text-ink-2">
              <span className="font-medium text-ink">{HORIZON_LABEL[s.horizon]}</span> · {s.scored}건 · 범위 적중{' '}
              {(s.coverage * 100).toFixed(0)}% · 방향 {(s.hit_rate * 100).toFixed(0)}% (기준선{' '}
              {(s.baseline_hit_rate * 100).toFixed(0)}%)
            </li>
          ))}
          {pending > 0 && <li className="text-xs text-muted">채점 대기 {pending}건</li>}
        </ul>
      )}
    </div>
  )
}
