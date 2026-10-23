import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'

import type { HistoryPoint, Holding, Summary } from '../api/client'
import { useCorporateActions, useHoldings, usePortfolioHistory, useSparklines, useSummary } from '../api/hooks'
import { AllocationBar } from '../components/AllocationBar'
import { CompareCard } from '../components/CompareCard'
import { HoldingsList } from '../components/HoldingsList'
import { KimchiPremium } from '../components/KimchiPremium'
import { PortfolioForecastCard } from '../components/PortfolioForecastCard'
import { RulesBanner } from '../components/RulesBanner'
import { Card, Disclosure, ErrorBox, InfoRow, Muted, PnL, SegmentedControl, Skeleton } from '../components/ui'
import { HistoryEmpty, ValueHistoryChart } from '../components/ValueHistoryChart'
import { useMoney } from '../lib/currency'
import { formatKrwShort } from '../lib/format'
import { MIN_HISTORY_DAYS, historySpanDays, shortestCoveringRange } from '../lib/history'
import { isSuspiciousCost } from '../lib/holdings'
import { changeLabel, latestAsOf } from '../lib/quoteTime'
import { RANGE_OPTIONS, rangeStart, type RangeKey } from '../lib/ranges'

/** Won totals from one 억 up get a short reading beside the full number. */
const SHORT_FROM_KRW = 1e8

/**
 * Home: total value and today's move, holdings with 30-day sparklines, the one-month portfolio
 * forecast, then the value history. Side cards (asset mix, kimchi premium) appear only when they say
 * something: two asset classes, or a coin position.
 */
export function Dashboard() {
  const summary = useSummary()
  const holdings = useHoldings()
  const sparklines = useSparklines()
  const actions = useCorporateActions()

  if (summary.error) return <ErrorBox error={summary.error} />
  if (!summary.data) return <DashboardSkeleton />
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

  const pendingActions = actions.data?.filter((a) => a.status === 'detected').length ?? 0
  const suspicious = holdings.data?.filter((h) => isSuspiciousCost(h.avg_cost, h.price)).length ?? 0
  const classes = s.allocation.filter((a) => a.market_value > 0)
  const showAllocation = classes.length >= 2
  const showKimchi = classes.some((a) => a.asset_type === 'crypto')
  const sideCards = Number(showAllocation) + Number(showKimchi)

  return (
    <div className="space-y-6">
      <SummaryHeader s={s} holdings={holdings.data} />

      {pendingActions > 0 && (
        <Banner
          to="/transactions"
          title={`확인이 필요한 배당·액면분할 ${pendingActions}건`}
          body="반영하기 전까지 보유 수량이나 손익이 실제와 다를 수 있습니다 →"
        />
      )}
      {suspicious > 0 && (
        <Banner
          to="/transactions?check=1"
          title={`평균단가 확인 필요 ${suspicious}종목`}
          body="스크린샷에서 단가를 잘못 읽었을 수 있어요. 거래 페이지에서 고쳐 주세요 →"
        />
      )}
      <RulesBanner />

      <Card title="보유 종목">
        {holdings.error ? (
          <ErrorBox error={holdings.error} />
        ) : !holdings.data ? (
          <HoldingsSkeleton />
        ) : holdings.data.length ? (
          <HoldingsList holdings={holdings.data} sparklines={sparklines.data} />
        ) : (
          <Muted>보유 중인 종목이 없습니다.</Muted>
        )}
      </Card>

      <Card title="앞으로의 예상 자산">
        <PortfolioForecastCard usdKrw={s.usd_krw} />
      </Card>

      <HistorySection />

      <CompareCard />

      {sideCards > 0 && (
        <div className={`grid gap-6 ${sideCards === 2 ? 'lg:grid-cols-2' : ''}`}>
          {showAllocation && (
            <Card title="자산군 비중">
              <AllocationBar allocation={s.allocation} />
            </Card>
          )}
          {showKimchi && (
            <Card title="김치 프리미엄">
              <KimchiPremium />
            </Card>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * Hero number (the page title), the latest session's move and the total return as sentences;
 * the breakdown folds under "손익 구성 자세히". `holdings` only dates the quotes: during the
 * Korean day the US close is yesterday's, so the move is labelled by that date, not "오늘".
 */
function SummaryHeader({ s, holdings }: { s: Summary; holdings?: Holding[] }) {
  const { currency, pick, format, formatOther } = useMoney()
  const unrealizedPct = pick(s.unrealized_pct, s.unrealized_pct_krw)
  // Realized gains and dividends are in the total amount but not in the (unrealized) return rate.
  const hasOtherPnl = s.realized_pnl !== 0 || s.dividends !== 0
  const moveLabel = changeLabel(holdings && latestAsOf(holdings), 'date')
  const hasStock = s.allocation.some((a) => a.asset_type === 'stock' && a.market_value > 0)
  // Display only: the coins' combined weight, to read them as one position (they move together).
  const coinCount = holdings?.filter((h) => h.asset_type === 'crypto').length ?? 0
  const coinWeight = s.allocation.find((a) => a.asset_type === 'crypto')?.weight ?? 0
  const krwShort = currency === 'KRW' && s.market_value_krw >= SHORT_FROM_KRW
  return (
    <section>
      <h1 className="text-sm font-normal text-muted">총 자산</h1>
      <div className="mt-1 flex flex-wrap items-baseline gap-x-3">
        <div className="text-4xl font-semibold tracking-tight sm:text-5xl">
          {format(pick(s.market_value, s.market_value_krw))}
        </div>
        {krwShort && <div className="num text-lg font-medium text-ink-2">{formatKrwShort(s.market_value_krw)}</div>}
      </div>
      <dl className="mt-3 space-y-1 text-[15px]">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <dt className="text-ink-2">{moveLabel}</dt>
          <dd className="num font-semibold">
            <PnL value={pick(s.day_change, s.day_change_krw)} pct={s.day_change_pct} />
          </dd>
        </div>
        <div className="flex flex-wrap items-baseline gap-x-2">
          <dt className="text-ink-2">총 수익</dt>
          {hasOtherPnl ? (
            // The amount includes realized gains and dividends, the rate only the open positions:
            // two different bases, so they are not written as one "+X원 (+Y%)" pair.
            <>
              <dd className="num font-semibold">
                <PnL value={pick(s.total_pnl, s.total_pnl_krw)} />
              </dd>
              <dd className="num font-semibold">
                <span className="mr-2 font-normal text-ink-2">· 평가 수익률</span>
                <PnL pctOnly value={0} pct={unrealizedPct} />
              </dd>
            </>
          ) : (
            <dd className="num font-semibold">
              <PnL value={pick(s.total_pnl, s.total_pnl_krw)} pct={unrealizedPct} />
            </dd>
          )}
          <dd className="num text-muted">· 투자원금 {format(pick(s.cost_basis, s.cost_basis_krw))}</dd>
        </div>
      </dl>
      <div className="mt-2 text-sm text-muted">
        {formatOther(s.market_value, s.market_value_krw)} · 원/달러 {s.usd_krw.toFixed(2)}
      </div>
      <div className="mt-3 max-w-md">
        <Disclosure summary="손익 구성 자세히">
          <dl className="divide-y divide-line">
            <InfoRow
              label="평가손익"
              value={<PnL value={pick(s.unrealized_pnl, s.unrealized_pnl_krw)} pct={unrealizedPct} />}
            />
            <InfoRow label="실현손익" value={<PnL value={pick(s.realized_pnl, s.realized_pnl_krw)} />} />
            <InfoRow label="배당 (세후)" value={format(pick(s.dividends, s.dividends_krw))} />
            {currency === 'KRW' && <InfoRow label="환차손익" value={<PnL value={s.fx_pnl_krw} />} />}
            <InfoRow label="종목 수" value={`${s.holdings_count}개`} />
          </dl>
          <p className="mt-2 text-xs text-muted">
            총 수익은 평가손익 + 실현손익 + 배당입니다.
            {hasOtherPnl && ' 수익률은 지금 보유 중인 종목의 평가손익 기준이라, 실현손익과 배당은 금액에만 들어 있습니다.'}
            {currency === 'KRW' && ' 원화 투자원금은 매수일 환율로 계산해 환차손익이 포함됩니다.'}
            {hasStock &&
              ' 미국 주식은 한국 시간 밤에 거래되어 낮에는 전날 종가가 최신 시세이고, 변동은 그 종가와 그 전 거래일 종가의 차이입니다.'}
            {coinCount >= 2 &&
              ` 코인 ${coinCount}종은 함께 움직이는 편이라 사실상 한 포지션으로 보세요 (비중 합 ${coinWeight.toFixed(1)}%).`}
          </p>
        </Disclosure>
      </div>
    </section>
  )
}

/** Attention strip above the cards; the whole strip is one link. */
function Banner({ to, title, body }: { to: string; title: string; body: ReactNode }) {
  return (
    <Link
      to={to}
      className="block rounded-lg border border-line bg-surface px-4 py-3 text-sm hover:bg-hover"
    >
      <span className="font-medium">{title}</span>
      <span className="ml-2 text-ink-2">{body}</span>
    </Link>
  )
}

/**
 * Loads the full history first: under a week of data it shows a hint instead of a flat line,
 * otherwise the chart opens on the shortest preset range that covers every point.
 */
function HistorySection() {
  const full = usePortfolioHistory(undefined)
  if (full.error)
    return (
      <Card title="자산 추이">
        <ErrorBox error={full.error} />
      </Card>
    )
  if (!full.data)
    return (
      <Card title="자산 추이">
        <Skeleton className="h-56" />
      </Card>
    )
  const days = historySpanDays(full.data)
  if (days < MIN_HISTORY_DAYS)
    return (
      <Card title="자산 추이">
        <HistoryEmpty days={days} />
      </Card>
    )
  return <HistoryChartCard points={full.data} />
}

function HistoryChartCard({ points }: { points: HistoryPoint[] }) {
  const [range, setRange] = useState<RangeKey>(() => shortestCoveringRange(points))
  // For 'ALL' this is the same query as the full history, so it is served from cache.
  const history = usePortfolioHistory(rangeStart(range))
  return (
    <Card
      title="자산 추이"
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
        <Skeleton className="h-56" />
      )}
    </Card>
  )
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true">
      <p role="status" className="sr-only">
        불러오는 중
      </p>
      <section>
        <Skeleton className="h-4 w-14" />
        <Skeleton className="mt-2 h-12 w-64" />
        <Skeleton className="mt-3 h-4 w-48" />
        <Skeleton className="mt-1.5 h-4 w-60" />
      </section>
      <Card title="보유 종목">
        <HoldingsSkeleton />
      </Card>
    </div>
  )
}

function HoldingsSkeleton() {
  return (
    <div className="space-y-2">
      {[0, 1, 2].map((i) => (
        <div key={i} className="flex items-center gap-3 py-2">
          <Skeleton className="size-10" />
          <div className="flex-1 space-y-1.5">
            <Skeleton className="h-4 w-20" />
            <Skeleton className="h-3 w-32" />
          </div>
          <Skeleton className="hidden h-8 w-24 sm:block" />
          <div className="space-y-1.5">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="ml-auto h-3 w-12" />
          </div>
        </div>
      ))}
    </div>
  )
}
