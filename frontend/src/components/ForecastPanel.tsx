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
import {
  COVERAGE_PHRASE,
  edgeLabels,
  HORIZON_LABEL,
  horizonPhrase,
  isPastTarget,
  midPhrase,
  pctRange,
  pendingPhrase,
  rangePhrase,
  reasonLabel,
  worstHorizonVerdict,
  type EdgeTone,
  type Horizon,
} from '../lib/forecast'
import { formatDate, formatPct, isoDate } from '../lib/format'
import { DAY_MS, tickLabel } from '../lib/priceChart'
import { Disclosure, ErrorBox, Muted, SegmentedControl } from './ui'

const HORIZON_OPTIONS = Object.entries(HORIZON_LABEL).map(([value, label]) => ({ value, label }))

const ACTUAL = { label: '실제 수익률', color: 'var(--series-1)' }
const FORECAST = { label: `당시 예측 범위 (${COVERAGE_PHRASE})`, color: 'var(--series-2)' }

const day = (d: string) => new Date(`${d}T00:00:00`).getTime()

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

/**
 * Plain-language forecast summary for one held symbol: a direction chip and a range chip
 * (the most conservative verdict across the three horizons), three horizon lines, and the
 * full validation record folded under "이 예측, 믿을 만한가요?".
 * The fan chart itself lives on the main price chart (PriceForecastChart).
 */
export function ForecastPanel({ symbol, fx }: { symbol: string; fx?: number }) {
  const forecast = useForecast(symbol)
  const notTrained = forecast.error instanceof ApiError && forecast.error.code === 'not_trained'

  if (notTrained) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-ink-2">아직 학습된 모델이 없습니다. 첫 학습은 시세를 내려받느라 몇 분 걸립니다.</p>
        <TrainButton notTrained />
      </div>
    )
  }
  if (forecast.error) return <ErrorBox error={forecast.error} />
  if (!forecast.data) return <Muted>예측을 계산하는 중… (처음에는 수십 초 걸릴 수 있습니다)</Muted>
  return <ForecastSummary data={forecast.data} symbol={symbol} fx={fx} />
}

const CHIP_CLASS: Record<EdgeTone, string> = {
  good: 'bg-accent-soft text-accent',
  pending: 'bg-hover text-ink-2',
  none: 'border border-line text-muted',
}

function ForecastSummary({ data, symbol, fx }: { data: SymbolForecast; symbol: string; fx?: number }) {
  const { currency, format } = useMoney()
  // Prices are USD; in KRW mode convert at today's rate (the best guess for future rates
  // too). Coins held on Upbit use their Upbit rate, which includes the kimchi premium.
  const rate = data.krw_rate ?? fx
  const conv = (usd: number) => (currency === 'KRW' && rate ? usd * rate : usd)
  const money = (v: number) => format(conv(v))
  const coin = symbol.endsWith('-USD')
  // One verdict for the card: the most conservative of the three horizons, per axis.
  const worst = worstHorizonVerdict(data.horizons)
  const chips = worst ? edgeLabels(worst) : []
  const asOf = data.horizons[0]?.as_of

  return (
    <div className="space-y-4">
      {chips.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <ul className="flex flex-wrap gap-1.5" aria-label="검증 판정">
            {chips.map((c) => (
              <li
                key={c.axis}
                className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-semibold ${CHIP_CLASS[c.tone]}`}
              >
                <span className="font-medium opacity-80">{c.axis}</span>
                {c.label}
              </li>
            ))}
          </ul>
          <span className="text-xs text-muted">1일·1주·1개월 공통 (세 기간 중 가장 보수적인 판정)</span>
        </div>
      )}
      <ul className="divide-y divide-line">
        {data.horizons.map((h) => (
          <HorizonLine key={h.horizon} h={h} coin={coin} format={money} />
        ))}
      </ul>
      <p className="text-xs text-muted">
        {asOf && `데이터 기준일 ${formatDate(asOf, 'long')} `}
        {coin ? '일봉 마감(한국 시간 다음 날 오전 9시, 달러 시세 기준)' : '미국 장 마감'}.
        {coin &&
          currency === 'KRW' &&
          (data.krw_rate
            ? ' 원화는 현재 업비트 가격 비율(김치 프리미엄 포함)로 환산했습니다.'
            : ' 원화는 달러 시세를 오늘 환율로 환산한 값입니다.')}{' '}
        기준선은 시장 지수가 아니라 단순 통계(방향: 과거에 오른 날 비율, 범위: EWMA 변동성)입니다. 참고용이며 투자
        조언이 아닙니다.
      </p>
      <Disclosure summary="이 예측, 믿을 만한가요?">
        <div className="space-y-6">
          <p className="text-sm text-ink-2">
            아래는 모델을 과거 데이터로 시험한 성적입니다. 기준선과 차이가 없으면 &lsquo;우위 없음&rsquo;입니다.
          </p>
          <Verdicts horizons={data.horizons} format={money} />
          <p className="text-xs text-muted">
            보유 종목과 참조 종목 약 60개를 함께 학습한 LightGBM 분위수 모델이 1일·1주·1개월 뒤 가격의 범위(
            {COVERAGE_PHRASE})와 오를 확률을 추정합니다. 기준선: 오를 확률은 학습 기간에 오른 날의 비율, 범위는 EWMA
            변동성 + 두꺼운 꼬리(t분포). 학습 {data.trained_at.slice(0, 16).replace('T', ' ')}.
          </p>
          <Validation />
          <Backtest symbol={symbol} />
          <TrackRecord symbol={symbol} />
          <TrainButton notTrained={false} />
        </div>
      </Disclosure>
    </div>
  )
}

/** A coin's daily bar for date D closes at 00:00 UTC on D+1, which is 09:00 the next day in Korea. */
function closeLabel(date: string, coin: boolean): string {
  if (!coin) return formatDate(date, 'long')
  const next = new Date(`${date}T00:00:00Z`)
  next.setUTCDate(next.getUTCDate() + 1)
  return `${formatDate(next.toISOString().slice(0, 10), 'long')} 09:00`
}

function HorizonLine({ h, coin, format }: { h: HorizonForecast; coin: boolean; format: (v: number) => string }) {
  const move = h.base_price > 0 ? (h.p50 / h.base_price - 1) * 100 : 0
  const pct = (v: number) => `${(v * 100).toFixed(0)}%`
  const direction = reasonLabel(h.direction_reason)
  // A target date already behind today (the latest bar has not arrived yet, ISSUE-039) is not a
  // forecast of the future any more: it is dimmed and labelled as waiting to be scored.
  const past = isPastTarget(h.target_date)
  return (
    <li className={`flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-3 ${past ? 'opacity-60' : ''}`}>
      <div>
        <div className="text-[15px] font-semibold text-ink">
          {past ? pendingPhrase(h.target_date) : horizonPhrase(h.horizon as Horizon, coin)}
        </div>
        <div className="text-xs text-muted">
          {past && `${HORIZON_LABEL[h.horizon] ?? h.horizon} 예측 · `}
          {closeLabel(h.target_date, coin)} 기준
        </div>
      </div>
      <div className="num text-right">
        {/* The median is an estimate, not a gain: no P&L color or arrow. */}
        <div className="text-[15px] font-semibold text-ink">
          {midPhrase(format(h.p50))} <span className="font-normal text-ink-2">({formatPct(move, true, 1)})</span>
        </div>
        <div className="text-[13px] text-ink-2">
          {rangePhrase(format(h.p10), format(h.p90))}{' '}
          <span className="text-muted">({pctRange(h.p10, h.p90, h.base_price)})</span>
        </div>
        {h.direction_reason === 'edge' ? (
          <div className="text-[13px] text-ink-2">
            오를 확률 {pct(h.p_up)} <span className="text-muted">(기준선 {pct(h.baseline_p_up)})</span>
          </div>
        ) : (
          // Without a direction edge the probability is not a headline: it stays, dimmed, with the verdict.
          <div className="text-xs text-muted">
            방향: {direction.label} (모델 {pct(h.p_up)} · 과거 평균 {pct(h.baseline_p_up)}
            {h.direction_reason === 'not_significant' && ', 검증에서 차이 없음'})
          </div>
        )}
      </div>
    </li>
  )
}

/**
 * The live verdict per horizon, direction and range separately, with the baseline's range
 * beside the model's so the "우위 없음" has something to be compared with.
 */
function Verdicts({ horizons, format }: { horizons: HorizonForecast[]; format: (v: number) => string }) {
  return (
    <ul className="space-y-2 text-sm text-ink-2">
      {horizons.map((h) => {
        const [direction, range] = edgeLabels(h)
        return (
          <li key={h.horizon}>
            <div>
              <span className="font-medium text-ink">{HORIZON_LABEL[h.horizon]}</span> · 방향 {direction.label} · 범위{' '}
              {range.label}
            </div>
            <div className="num text-xs text-muted">
              현재 예측 범위 {format(h.p10)}~{format(h.p90)} · 기준선 범위 {format(h.baseline_p10)}~
              {format(h.baseline_p90)}
            </div>
          </li>
        )
      })}
    </ul>
  )
}

function Legend({ items }: { items: { label: string; color: string }[] }) {
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
  const spanDays = rows.length > 1 ? (rows[rows.length - 1].t - rows[0].t) / DAY_MS : 0

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
          <Legend items={[ACTUAL, FORECAST]} />
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
                  tickFormatter={(t: number) => tickLabel(t, spanDays)}
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
            실제 수익률이 당시 예측 범위 안에 든 비율 {((inside / points.length) * 100).toFixed(0)}% (목표 80%,{' '}
            {points.length}건). 기준선 범위의 적중률은 위 &lsquo;검증 성적&rsquo; 표의 기준선 값을 참고하세요. 각
            시점의 예측은 그 이전 데이터로만 학습한 모델이 낸 것이며
            {holdoutStart && `, ${formatDate(holdoutStart, 'long')} 이후는 학습에 쓰지 않은 최종 확인 구간입니다`}.
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
      <div className="mb-1 text-muted">{formatDate(isoDate(new Date(Number(label))), 'long')} 예측</div>
      <div className="flex justify-between gap-4">
        <span className="text-ink-2">실제</span>
        <span className="num font-semibold text-ink">{formatPct(row.actual)}</span>
      </div>
      <div className="flex justify-between gap-4">
        <span className="text-ink-2">당시 예측 범위</span>
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
        <>
          <ul className="space-y-1 text-sm">
            {summary.map((s) => (
              <li key={s.horizon} className="text-ink-2">
                <span className="font-medium text-ink">{HORIZON_LABEL[s.horizon]}</span> · {s.scored}건 · 범위 적중{' '}
                {(s.coverage * 100).toFixed(0)}% · 방향 {(s.hit_rate * 100).toFixed(0)}% (기준선{' '}
                {(s.baseline_hit_rate * 100).toFixed(0)}%) · Brier {s.brier.toFixed(3)} (기준선{' '}
                {s.baseline_brier.toFixed(3)})
              </li>
            ))}
            {pending > 0 && <li className="text-xs text-muted">채점 대기 {pending}건</li>}
          </ul>
          <p className="mt-2 text-xs text-muted">
            범위 적중의 기준선은 실전 기록에 없어 위 &lsquo;검증 성적&rsquo; 표의 기준선 값을 참고하세요.
          </p>
        </>
      )}
    </div>
  )
}
