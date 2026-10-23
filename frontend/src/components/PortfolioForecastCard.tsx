import {
  Area,
  ComposedChart,
  Line,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from 'recharts'

import { ApiError, type PortfolioForecast } from '../api/client'
import { useForecastStatus, usePortfolioForecast } from '../api/hooks'
import { useMoney } from '../lib/currency'
import {
  bandLabel,
  bandLegend,
  coverageNote,
  esPhrase,
  horizonPhrase,
  midLegend,
  midPhrase,
  modelStatusSentence,
  type Horizon as HorizonKey,
} from '../lib/forecast'
import { formatKrwShort, formatPct } from '../lib/format'
import { TrainButton } from './ForecastPanel'
import { Disclosure, ErrorBox, InfoRow, Muted, PnL, Swatch } from './ui'

type Horizon = PortfolioForecast['horizons'][number]
type Row = { label: string; p10: number; p50: number; p90: number; band: [number, number]; today: boolean }
type Money = (krw: number) => string

// Equal steps on the x axis: with real day spacing "오늘" and "내일" would sit on top of each other.
const STEP_LABEL: Record<string, string> = { '1d': '내일', '1w': '1주', '1m': '1개월' }
const COLOR = 'var(--series-2)'

const movePct = (h: Horizon) => (h.p50 / h.value_krw - 1) * 100

/** Where the whole portfolio could be in a day, a week and a month, in won. */
export function PortfolioForecastCard({ usdKrw }: { usdKrw: number }) {
  const forecast = usePortfolioForecast()
  const status = useForecastStatus()
  const { currency, format } = useMoney()
  // The simulation is in won; in dollar mode show it at today's rate.
  const display = (krw: number) => (currency === 'USD' ? krw / usdKrw : krw)
  const money: Money = (krw) => format(display(krw))
  const short: Money = (krw) => (currency === 'USD' ? format(krw / usdKrw) : formatKrwShort(krw))
  const notTrained = forecast.error instanceof ApiError && forecast.error.code === 'not_trained'

  if (notTrained)
    return (
      <div className="space-y-3">
        <Muted>예측 모델을 학습하면 보유 자산 전체의 예상 범위를 보여 줍니다.</Muted>
        <TrainButton notTrained />
      </div>
    )
  if (forecast.error) return <ErrorBox error={forecast.error} />
  if (!forecast.data) return <Muted>예측을 계산하는 중… (처음에는 수십 초 걸릴 수 있습니다)</Muted>
  const data = forecast.data
  if (data.horizons.length === 0 || data.horizons[0].value_krw <= 0)
    return <Muted>예측할 보유 종목이 없습니다.</Muted>

  const today = data.horizons[0].value_krw
  const month = data.horizons.find((h) => h.horizon === '1m') ?? data.horizons[data.horizons.length - 1]
  const rows: Row[] = [
    { label: '오늘', p10: today, p50: today, p90: today, band: [today, today], today: true },
    ...data.horizons.map((h) => ({
      label: STEP_LABEL[h.horizon] ?? h.horizon,
      p10: h.p10,
      p50: h.p50,
      p90: h.p90,
      band: [h.p10, h.p90] as [number, number],
      today: false,
    })),
  ]
  const end = rows[rows.length - 1]
  const premia = Object.entries(data.kimchi_premium ?? {})
  // The month's p10 is written without its unit so the band reads as one range: 1,381만~1,720만원.
  const low = short(month.p10).replace(/원$/, '')

  return (
    <div className="space-y-4">
      {/* The median is a forecast, not a realized gain: plain text, no P&L color or arrow. */}
      <p className="text-[17px] leading-snug text-ink">
        <span className="font-semibold">
          {month.horizon === '1m' ? '한 달 뒤' : horizonPhrase(month.horizon as HorizonKey, false)} 약{' '}
          <span className="num">{midPhrase(short(month.p50))}</span>
        </span>
        <span className="text-[15px] text-ink-2">(절반은 이보다 많고 절반은 적어요)</span>, 10번 중 8번은{' '}
        <span className="num">
          {low}~{short(month.p90)}
        </span>{' '}
        사이 <span className="num text-[15px] text-ink-2">· 지금보다 {formatPct(movePct(month), true, 1)}</span>
      </p>

      <div>
        <ul className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2" aria-label="범례">
          <li className="flex items-center gap-1.5">
            <Swatch color={COLOR} dashed />
            {midLegend()}
          </li>
          <li className="flex items-center gap-1.5">
            <Swatch color={COLOR} fill />
            {bandLegend()}
          </li>
        </ul>
        <div className="h-48" role="img" aria-label="앞으로의 예상 자산 띠 차트">
          <ResponsiveContainer width="100%" height="100%">
            {/* Straight segments: the x axis is three uneven steps, so a smooth curve would read as a growth path. */}
            <ComposedChart data={rows} margin={{ top: 8, right: 64, bottom: 0, left: 16 }}>
              <XAxis
                dataKey="label"
                tickLine={false}
                axisLine={false}
                interval={0}
                tick={{ fill: 'var(--muted)', fontSize: 11 }}
              />
              {/* Hidden, but keeps the auto domain so the band is not squashed against zero. */}
              <YAxis hide domain={['auto', 'auto']} />
              <Tooltip
                content={(props) => <ForecastTooltip {...props} money={money} />}
                cursor={{ stroke: 'var(--axis)', strokeWidth: 1 }}
              />
              <Area
                dataKey="band"
                type="linear"
                stroke="none"
                fill={COLOR}
                fillOpacity={0.18}
                activeDot={false}
                isAnimationActive={false}
              />
              <Line
                dataKey="p50"
                type="linear"
                stroke={COLOR}
                strokeWidth={2}
                strokeDasharray="4 4"
                dot={false}
                activeDot={{ r: 4, stroke: 'var(--surface)', strokeWidth: 2 }}
                isAnimationActive={false}
              />
              <ReferenceDot x="오늘" y={today} r={4} fill={COLOR} stroke="var(--surface)" strokeWidth={2} />
              {/* End values at the last step so the chart is readable without hovering (phones). */}
              <ReferenceDot
                x={end.label}
                y={end.p90}
                r={0}
                label={{ value: short(end.p90), position: 'right', fill: 'var(--ink-2)', fontSize: 11 }}
              />
              <ReferenceDot
                x={end.label}
                y={end.p50}
                r={3}
                fill={COLOR}
                stroke="var(--surface)"
                strokeWidth={2}
                label={{ value: short(end.p50), position: 'right', fill: 'var(--ink)', fontSize: 11, fontWeight: 600 }}
              />
              <ReferenceDot
                x={end.label}
                y={end.p10}
                r={0}
                label={{ value: short(end.p10), position: 'right', fill: 'var(--ink-2)', fontSize: 11 }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Always visible, not only inside the fold: the model's standing and the disclaimer. */}
      <p className="text-xs text-muted">
        {status.data && `${modelStatusSentence(status.data.live ?? null)} `}
        투자 조언이 아닙니다.
      </p>

      <Disclosure summary="기간별 예상 자세히">
        <div className="space-y-3">
          {data.horizons.map((h) => (
            <div key={h.horizon}>
              <div className="text-[13px] font-semibold text-ink">
                {horizonPhrase(h.horizon as HorizonKey, false)}
              </div>
              <dl className="divide-y divide-line">
                <InfoRow
                  label="예상 중간값"
                  value={
                    <>
                      {midPhrase(money(h.p50))}
                      <span className="ml-1.5 text-[13px] font-normal text-ink-2">
                        ({formatPct(movePct(h), true, 1)})
                      </span>
                    </>
                  }
                />
                <InfoRow label={bandLabel()} value={`${money(h.p10)}~${money(h.p90)}`} />
                <InfoRow
                  label={
                    <>
                      운 나쁜 경우
                      <span className="mt-0.5 block text-xs text-muted">{esPhrase()}</span>
                    </>
                  }
                  value={<PnL value={-display(h.es95)} pct={(-h.es95 / h.value_krw) * 100} digits={1} />}
                />
              </dl>
            </div>
          ))}
          <p className="text-xs text-muted">
            종목별 예측 범위를 종목 간·환율 상관관계(최근 2년)로 묶어 1만 번 시뮬레이션한 결과입니다. 범위가 맞는
            비율은 {coverageNote()}입니다. 열 번 중 두 번(위로 한 번, 아래로 한 번꼴)은 범위를 벗어나고, 급락장에서는
            종목들이 함께 떨어져 범위를 더 자주 벗어납니다.
            {premia.length > 0 &&
              ` 업비트 코인은 김치 프리미엄(현재 ${premia
                .map(([s, p]) => `${s.replace('-USD', '')} ${formatPct(p * 100)}`)
                .join(', ')})이 평균으로 돌아가는 움직임까지 반영했습니다.`}
            {data.excluded.length > 0 && ` 시세가 부족해 제외: ${data.excluded.join(', ')}.`} 참고용이며 투자
            조언이 아닙니다.
          </p>
        </div>
      </Disclosure>
    </div>
  )
}

function ForecastTooltip({ active, payload, money }: TooltipContentProps & { money: Money }) {
  if (!active || !payload?.length) return null
  const row = payload[0].payload as Row
  return (
    <div className="rounded-xl border border-line bg-surface px-3 py-2 text-xs shadow-lg">
      <div className="mb-1 text-muted">{row.label}</div>
      {row.today ? (
        <div className="num font-semibold text-ink">{money(row.p50)}</div>
      ) : (
        <>
          <div className="flex items-center justify-between gap-4">
            <span className="flex items-center gap-1.5 text-ink-2">
              <Swatch color={COLOR} dashed />
              예상 중간값
            </span>
            <span className="num font-semibold text-ink">{money(row.p50)}</span>
          </div>
          <div className="flex items-center justify-between gap-4">
            <span className="flex items-center gap-1.5 text-ink-2">
              <Swatch color={COLOR} fill />
              {bandLegend()}
            </span>
            <span className="num font-semibold text-ink">
              {money(row.p10)}~{money(row.p90)}
            </span>
          </div>
        </>
      )}
    </div>
  )
}
