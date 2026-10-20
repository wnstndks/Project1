import { ApiError } from '../api/client'
import { usePortfolioForecast } from '../api/hooks'
import { useMoney } from '../lib/currency'
import { HORIZON_LABEL } from '../lib/forecast'
import { formatPct } from '../lib/format'
import { TrainButton } from './ForecastPanel'
import { ErrorBox, Muted } from './ui'

/** Where the whole portfolio could be in a day, a week and a month, in won. */
export function PortfolioForecastCard({ usdKrw }: { usdKrw: number }) {
  const forecast = usePortfolioForecast()
  const { currency, format } = useMoney()
  // The simulation is in won; in dollar mode show it at today's rate.
  const money = (krw: number) => format(currency === 'USD' ? krw / usdKrw : krw)
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
  const premia = Object.entries(data.kimchi_premium ?? {})

  return (
    <div className="space-y-3">
      <div className="-mx-5 overflow-x-auto">
        <table className="num w-full min-w-[560px] text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs text-muted">
              <th className="px-5 py-2 font-medium">기간</th>
              <th className="px-3 py-2 text-right font-medium">중앙값</th>
              <th className="px-3 py-2 text-right font-medium">10~90% 범위</th>
              <th className="px-5 py-2 text-right font-medium">나쁜 경우 (하위 5% 평균 손실)</th>
            </tr>
          </thead>
          <tbody>
            {data.horizons.map((h) => (
              <tr key={h.horizon} className="border-b border-line last:border-0">
                <td className="px-5 py-2.5 font-medium">
                  {h.horizon === '1d' ? '다음 거래일' : `${HORIZON_LABEL[h.horizon]} 뒤`}
                </td>
                <td className="px-3 py-2.5 text-right">
                  {money(h.p50)}
                  <div className="text-xs text-muted">{formatPct((h.p50 / h.value_krw - 1) * 100)}</div>
                </td>
                <td className="px-3 py-2.5 text-right">
                  {money(h.p10)} ~ {money(h.p90)}
                </td>
                <td className="px-5 py-2.5 text-right">
                  −{money(h.es95)}
                  <div className="text-xs text-muted">{formatPct((-h.es95 / h.value_krw) * 100)}</div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted">
        종목별 예측 범위를 종목 간·환율 상관관계(최근 2년)로 묶어 1만 번 시뮬레이션한 결과입니다. 열 번 중 한 번은 범위
        밖으로 벗어나고, 급락장에서는 상관관계가 더 커질 수 있습니다.
        {premia.length > 0 &&
          ` 업비트 코인은 김치 프리미엄(현재 ${premia
            .map(([s, p]) => `${s.replace('-USD', '')} ${formatPct(p * 100)}`)
            .join(', ')})이 평균으로 돌아가는 움직임까지 반영했습니다.`}
        {data.excluded.length > 0 && ` 시세가 부족해 제외: ${data.excluded.join(', ')}.`} 참고용이며 투자 조언이
        아닙니다.
      </p>
    </div>
  )
}
