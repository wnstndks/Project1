import { useState } from 'react'
import { Link } from 'react-router-dom'

import { useHoldings, usePortfolioHistory, useSummary } from '../api/hooks'
import { AllocationBar } from '../components/AllocationBar'
import { HoldingsTable } from '../components/HoldingsTable'
import { Card, ErrorBox, Muted, PnL, SegmentedControl, StatTile } from '../components/ui'
import { ValueHistoryChart } from '../components/ValueHistoryChart'
import { formatKrw, formatPct, formatUsd } from '../lib/format'
import { RANGE_OPTIONS, rangeStart, type RangeKey } from '../lib/ranges'

export function Dashboard() {
  const summary = useSummary()
  const holdings = useHoldings()
  const [range, setRange] = useState<RangeKey>('1Y')
  const history = usePortfolioHistory(rangeStart(range))

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

  return (
    <div className="space-y-6">
      <section>
        <div className="text-sm text-muted">총 자산</div>
        <div className="mt-1 text-5xl font-semibold tracking-tight">{formatKrw(s.market_value_krw)}</div>
        <div className="mt-2 text-sm text-ink-2">
          {formatUsd(s.market_value)} · 원/달러 {s.usd_krw.toFixed(2)}
        </div>
      </section>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="평가손익" value={<PnL value={s.unrealized_pnl} />} sub={formatPct(s.unrealized_pct)} />
        <StatTile label="실현손익" value={<PnL value={s.realized_pnl} />} />
        <StatTile label="총 손익" value={<PnL value={s.total_pnl} />} sub="평가손익 + 실현손익" />
        <StatTile label="투자원금" value={formatUsd(s.cost_basis)} sub={`${s.holdings_count}개 종목 보유`} />
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
            </div>
          ) : (
            <div className="h-80" />
          )}
        </Card>
        <Card title="자산군 비중">
          <AllocationBar allocation={s.allocation} />
        </Card>
      </div>

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
