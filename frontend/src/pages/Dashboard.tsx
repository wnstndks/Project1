import { useState } from 'react'
import { Link } from 'react-router-dom'

import { useCorporateActions, useHoldings, usePortfolioHistory, useSummary } from '../api/hooks'
import { AllocationBar } from '../components/AllocationBar'
import { KimchiPremium } from '../components/KimchiPremium'
import { PortfolioForecastCard } from '../components/PortfolioForecastCard'
import { HoldingsTable } from '../components/HoldingsTable'
import { Card, ErrorBox, Muted, PnL, SegmentedControl, StatTile } from '../components/ui'
import { ValueHistoryChart } from '../components/ValueHistoryChart'
import { useMoney } from '../lib/currency'
import { formatKrw, formatPct, signed } from '../lib/format'
import { RANGE_OPTIONS, rangeStart, type RangeKey } from '../lib/ranges'

export function Dashboard() {
  const summary = useSummary()
  const holdings = useHoldings()
  const [range, setRange] = useState<RangeKey>('1Y')
  const history = usePortfolioHistory(rangeStart(range))
  const { currency, pick, format, formatOther } = useMoney()
  const actions = useCorporateActions()
  const pendingActions = actions.data?.filter((a) => a.status === 'detected').length ?? 0

  if (summary.error) return <ErrorBox error={summary.error} />
  if (!summary.data) return <Muted>불러오는 중…</Muted>
  const s = summary.data

  if (s.holdings_count === 0 && s.realized_pnl === 0) {
    return (
      <Card>
        <Muted>
          아직 거래 내역이 없습니다.{' '}
          <Link to="/transactions" className="text-accent underline">
            첫 거래를 입력
          </Link>
          해 보세요.
        </Muted>
      </Card>
    )
  }

  const unrealizedPct = pick(s.unrealized_pct, s.unrealized_pct_krw)

  return (
    <div className="space-y-6">
      {pendingActions > 0 && (
        <Link
          to="/transactions"
          className="block rounded-lg border border-line bg-surface px-4 py-3 text-sm hover:bg-hover"
        >
          <span className="font-medium">확인이 필요한 배당·액면분할 {pendingActions}건</span>
          <span className="ml-2 text-ink-2">반영하기 전까지 보유 수량이나 손익이 실제와 다를 수 있습니다 →</span>
        </Link>
      )}
      <section>
        <div className="text-sm text-muted">총 자산</div>
        <div className="mt-1 text-5xl font-semibold tracking-tight">
          {format(pick(s.market_value, s.market_value_krw))}
        </div>
        <div className="mt-2 text-sm text-ink-2">
          {formatOther(s.market_value, s.market_value_krw)} · 원/달러 {s.usd_krw.toFixed(2)}
        </div>
      </section>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile
          label="평가손익"
          value={<PnL value={pick(s.unrealized_pnl, s.unrealized_pnl_krw)} />}
          sub={
            currency === 'KRW'
              ? `${formatPct(unrealizedPct)} · 환차손익 ${signed(s.fx_pnl_krw, formatKrw)}`
              : formatPct(unrealizedPct)
          }
        />
        <StatTile
          label="실현손익"
          value={<PnL value={pick(s.realized_pnl, s.realized_pnl_krw)} />}
          sub={
            s.dividends > 0 ? `배당(세후) ${format(pick(s.dividends, s.dividends_krw))} 별도` : undefined
          }
        />
        <StatTile
          label="총 손익"
          value={<PnL value={pick(s.total_pnl, s.total_pnl_krw)} />}
          sub="평가 + 실현 + 배당"
        />
        <StatTile
          label="투자원금"
          value={format(pick(s.cost_basis, s.cost_basis_krw))}
          sub={
            currency === 'KRW'
              ? `매수일 환율 기준 · ${s.holdings_count}개 종목`
              : `${s.holdings_count}개 종목 보유`
          }
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card
          title="자산 추이"
          className="lg:col-span-2"
          actions={<SegmentedControl label="기간" options={RANGE_OPTIONS} value={range} onChange={setRange} />}
        >
          {history.error ? (
            <ErrorBox error={history.error} />
          ) : history.data ? (
            <div className={history.isPlaceholderData ? 'opacity-50 transition-opacity' : ''}>
              <ValueHistoryChart points={history.data} />
              <p className="mt-2 text-xs text-muted">시세 × 보유 수량 기준이며, 받은 배당은 포함하지 않습니다.</p>
            </div>
          ) : (
            <div className="h-80" />
          )}
        </Card>
        <div className="space-y-6">
          <Card title="자산군 비중">
            <AllocationBar allocation={s.allocation} />
          </Card>
          <Card title="김치 프리미엄">
            <KimchiPremium />
          </Card>
        </div>
      </div>

      <Card title="앞으로의 예상 자산">
        <PortfolioForecastCard usdKrw={s.usd_krw} />
      </Card>

      <Card title="보유 종목">
        {holdings.error ? (
          <ErrorBox error={holdings.error} />
        ) : holdings.data?.length ? (
          <HoldingsTable holdings={holdings.data} />
        ) : (
          <Muted>보유 중인 종목이 없습니다.</Muted>
        )}
      </Card>
    </div>
  )
}
