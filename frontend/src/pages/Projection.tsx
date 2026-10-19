import { useState, type FormEvent, type ReactNode } from 'react'
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

import type { Assumptions, Projection as ProjectionResult, ProjectionInput } from '../api/client'
import { useAssumptions, useProjection } from '../api/hooks'
import { Card, ErrorBox, Muted, SegmentedControl, StatTile } from '../components/ui'
import { useMoney } from '../lib/currency'

type Form = {
  years: string
  monthly: string // 만원
  inflation: string
  stockReturn: string
  cryptoReturn: string
  stockShare: string
  target: string // 억원
}

const toNumber = (v: string) => (v.trim() === '' ? null : Number(v))

function toInput(f: Form): ProjectionInput {
  const target = toNumber(f.target)
  return {
    years: Number(f.years) || 10,
    monthly_contribution_krw: (toNumber(f.monthly) ?? 0) * 10_000,
    inflation_pct: toNumber(f.inflation) ?? 2.5,
    simulations: 5000,
    seed: 42,
    stock_return_pct: toNumber(f.stockReturn),
    crypto_return_pct: toNumber(f.cryptoReturn),
    contribution_stock_pct: toNumber(f.stockShare),
    target_krw: target ? target * 1e8 : null,
  }
}

export function Projection() {
  const assumptions = useAssumptions()
  if (assumptions.error) return <ErrorBox error={assumptions.error} />
  if (!assumptions.data) return <Muted>보유 자산과 과거 시세를 분석하는 중…</Muted>
  return <ProjectionView a={assumptions.data} />
}

function ProjectionView({ a }: { a: Assumptions }) {
  const { stock, crypto } = a.classes
  const [form, setForm] = useState<Form>({
    years: '10',
    monthly: '100',
    inflation: '2.5',
    stockReturn: String(stock.default_return_pct),
    cryptoReturn: String(crypto.default_return_pct),
    stockShare: String(Math.round(stock.weight_pct)),
    target: '',
  })
  const [submitted, setSubmitted] = useState<ProjectionInput>(() => toInput(form))
  const result = useProjection(submitted)
  const set = (k: keyof Form) => (v: string) => setForm((f) => ({ ...f, [k]: v }))

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    setSubmitted(toInput(form))
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">미래 자산 시뮬레이션</h1>
        <p className="mt-1 text-sm text-ink-2">
          현재 보유 자산 {formatKrwShort(a.start_value_krw)}에서 시작해 매달 적립했을 때의 자산을 5,000번
          시뮬레이션합니다. 결과는 확률적 범위이며 투자 조언이 아닙니다.
        </p>
      </div>

      <Card title="가정">
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <NumberField label="기간 (년)" value={form.years} onChange={set('years')} min={1} max={40} />
            <NumberField label="월 적립액 (만원)" value={form.monthly} onChange={set('monthly')} min={0} />
            <NumberField label="물가상승률 (%/년)" value={form.inflation} onChange={set('inflation')} step="0.1" />
            <NumberField
              label="적립 중 주식 비중 (%)"
              value={form.stockShare}
              onChange={set('stockShare')}
              min={0}
              max={100}
              hint={`현재 ${stock.weight_pct.toFixed(0)}%`}
            />
            <NumberField
              label="주식 기대수익률 (%/년)"
              value={form.stockReturn}
              onChange={set('stockReturn')}
              step="0.5"
              hint={`과거 ${a.lookback_years}년 평균 ${stock.hist_return_pct.toFixed(1)}% · 변동성 ${stock.vol_pct.toFixed(0)}%`}
            />
            <NumberField
              label="코인 기대수익률 (%/년)"
              value={form.cryptoReturn}
              onChange={set('cryptoReturn')}
              step="0.5"
              hint={`과거 평균 ${crypto.hist_return_pct.toFixed(1)}% · 변동성 ${crypto.vol_pct.toFixed(0)}%${
                crypto.proxy ? ` (${crypto.proxy} 기준)` : ''
              }`}
            />
            <NumberField label="목표 금액 (억원, 선택)" value={form.target} onChange={set('target')} min={0} step="0.1" />
          </div>
          <p className="text-xs text-muted">
            기대수익률 기본값은 보수적인 장기 가정입니다(과거 평균은 기간에 따라 크게 달라 그대로 쓰지 않습니다).
            변동성과 주식·코인 상관관계({a.correlation.toFixed(2)})는 보유 종목의 과거 {a.lookback_years}년 월간
            데이터에서 계산했습니다. 환율은 현재 값으로 고정합니다.
          </p>
          <button
            type="submit"
            className="rounded-lg bg-ink px-4 py-2 text-sm font-medium text-surface disabled:opacity-50"
            disabled={result.isFetching}
          >
            {result.isFetching ? '계산 중…' : '시뮬레이션 실행'}
          </button>
        </form>
      </Card>

      {result.error ? (
        <ErrorBox error={result.error} />
      ) : result.data ? (
        <div className={result.isPlaceholderData ? 'opacity-50 transition-opacity' : ''}>
          <Results data={result.data} hasTarget={submitted.target_krw != null} usdKrw={a.usd_krw} />
        </div>
      ) : (
        <Muted>계산 중…</Muted>
      )}
    </div>
  )
}

function Results({ data, hasTarget, usdKrw }: { data: ProjectionResult; hasTarget: boolean; usdKrw: number }) {
  const [real, setReal] = useState<'nominal' | 'real'>('nominal')
  const { currency, format, compact } = useMoney()
  // The simulation runs in KRW; USD view divides by today's rate.
  const conv = (krw: number) => (currency === 'USD' ? krw / usdKrw : krw)
  const final = data.years.at(-1)!
  const pick = (p: typeof final, k: 'p10' | 'p50' | 'p90') => conv(real === 'real' ? p[`${k}_real`] : p[k])

  const rows = data.years.map((y) => ({
    year: y.year,
    band: [pick(y, 'p10'), pick(y, 'p90')] as [number, number],
    p50: pick(y, 'p50'),
    contributed: conv(y.contributed_krw),
  }))

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label={`${final.year}년 후 중간값`} value={format(pick(final, 'p50'))} sub="50%는 이보다 많음" />
        <StatTile label="비관 (하위 10%)" value={format(pick(final, 'p10'))} sub="10%는 이보다 적음" />
        <StatTile label="낙관 (상위 10%)" value={format(pick(final, 'p90'))} sub="10%는 이보다 많음" />
        <StatTile
          label={hasTarget ? '목표 달성 확률' : '원금 손실 확률'}
          value={`${(hasTarget ? data.prob_target! : data.prob_loss).toFixed(1)}%`}
          sub={`총 납입 ${format(conv(final.contributed_krw))}`}
        />
      </div>

      <Card
        title="자산 범위"
        actions={
          <SegmentedControl
            label="금액 기준"
            value={real}
            onChange={setReal}
            options={[
              { value: 'nominal', label: '명목' },
              { value: 'real', label: '물가 반영' },
            ]}
          />
        }
      >
        <ul className="mb-3 flex flex-wrap gap-4 text-xs text-ink-2" aria-label="범례">
          <LegendItem swatch={<span className="inline-block h-2.5 w-4 rounded-sm bg-[var(--series-1)] opacity-20" />}>
            10~90% 범위
          </LegendItem>
          <LegendItem swatch={<span className="inline-block h-0.5 w-4 rounded bg-[var(--series-1)]" />}>중간값</LegendItem>
          <LegendItem swatch={<span className="inline-block h-0.5 w-4 rounded bg-[var(--series-2)]" />}>총 납입액</LegendItem>
        </ul>
        <div className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--grid)" />
              <XAxis
                dataKey="year"
                tickLine={false}
                axisLine={{ stroke: 'var(--axis)' }}
                tick={{ fill: 'var(--muted)', fontSize: 11 }}
                tickFormatter={(y: number) => `${y}년`}
              />
              <YAxis
                width={60}
                tickLine={false}
                axisLine={false}
                tick={{ fill: 'var(--muted)', fontSize: 11 }}
                tickFormatter={compact}
              />
              <Tooltip
                content={(props) => <BandTooltip {...props} format={format} />}
                cursor={{ stroke: 'var(--axis)', strokeWidth: 1 }}
              />
              <Area dataKey="band" stroke="none" fill="var(--series-1)" fillOpacity={0.12} isAnimationActive={false} />
              <Line
                dataKey="p50"
                stroke="var(--series-1)"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, stroke: 'var(--surface)', strokeWidth: 2 }}
                isAnimationActive={false}
              />
              <Line
                dataKey="contributed"
                stroke="var(--series-2)"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, stroke: 'var(--surface)', strokeWidth: 2 }}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <details className="mt-4 text-sm">
          <summary className="cursor-pointer text-xs text-muted">연도별 표 보기</summary>
          <div className="-mx-5 mt-2 overflow-x-auto">
            <table className="num w-full min-w-[560px]">
              <thead>
                <tr className="border-b border-line text-right text-xs text-muted">
                  <th className="px-5 py-2 text-left font-medium">연도</th>
                  <th className="px-3 py-2 font-medium">총 납입</th>
                  <th className="px-3 py-2 font-medium">하위 10%</th>
                  <th className="px-3 py-2 font-medium">중간값</th>
                  <th className="px-5 py-2 font-medium">상위 10%</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.year} className="border-b border-line text-right last:border-0">
                    <td className="px-5 py-1.5 text-left text-ink-2">{r.year}년</td>
                    <td className="px-3 py-1.5">{format(r.contributed)}</td>
                    <td className="px-3 py-1.5">{format(r.band[0])}</td>
                    <td className="px-3 py-1.5 font-medium">{format(r.p50)}</td>
                    <td className="px-5 py-1.5">{format(r.band[1])}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </Card>
    </div>
  )
}

function LegendItem({ swatch, children }: { swatch: ReactNode; children: ReactNode }) {
  return (
    <li className="flex items-center gap-1.5">
      {swatch}
      {children}
    </li>
  )
}

type BandRow = { year: number; band: [number, number]; p50: number; contributed: number }

function BandTooltip({ active, payload, format }: TooltipContentProps & { format: (v: number) => string }) {
  if (!active || !payload?.length) return null
  const r = payload[0].payload as BandRow
  const line = (label: string, v: number, strong = false) => (
    <div className="flex justify-between gap-4">
      <span className="text-ink-2">{label}</span>
      <span className={`num ${strong ? 'font-semibold text-ink' : 'text-ink'}`}>{format(v)}</span>
    </div>
  )
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-sm">
      <div className="mb-1 text-muted">{r.year}년 후</div>
      {line('상위 10%', r.band[1])}
      {line('중간값', r.p50, true)}
      {line('하위 10%', r.band[0])}
      {line('총 납입', r.contributed)}
    </div>
  )
}

function NumberField({ label, value, onChange, hint, ...rest }: {
  label: string
  value: string
  onChange: (v: string) => void
  hint?: string
  min?: number
  max?: number
  step?: string
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-muted">{label}</span>
      <input
        type="number"
        inputMode="decimal"
        className="num w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-accent"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        {...rest}
      />
      {hint && <span className="mt-1 block text-[11px] text-muted">{hint}</span>}
    </label>
  )
}

function formatKrwShort(v: number): string {
  if (v >= 1e8) return `${(v / 1e8).toFixed(2)}억 원`
  return `${Math.round(v / 1e4).toLocaleString('ko-KR')}만 원`
}
