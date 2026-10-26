import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { useAssetInfo, useConvertCurrency, useForecast, useHistory, useHoldings, useUsdKrw } from '../api/hooks'
import { CandleChart, type CandleMa } from '../components/CandleChart'
import { CongressMention } from '../components/CongressTrades'
import { ForecastPanel } from '../components/ForecastPanel'
import { GuruHolders } from '../components/GuruHolders'
import { NewsCard } from '../components/NewsCard'
import { PriceForecastChart } from '../components/PriceForecastChart'
import { RuleCard } from '../components/RuleCard'
import { Card, ErrorBox, InfoRow, Muted, PnL, SegmentedControl, Skeleton } from '../components/ui'
import { useMoney } from '../lib/currency'
import { daysAgo, displaySymbol, formatQty, formatUsd } from '../lib/format'
import { isSuspiciousCost } from '../lib/holdings'
import { DEFAULT_MA_PERIODS, dayChange, fiftyTwoWeek, MA_PERIODS, sma } from '../lib/indicators'
import { MA_STYLE, type MaLine } from '../lib/priceChart'
import { changeLabel, quoteTimeLabel } from '../lib/quoteTime'
import { RANGE_OPTIONS, rangeStart, type RangeKey } from '../lib/ranges'
import { PRICE_CHECK_REASON } from '../lib/transactionChecks'

const CHART_RANGES = RANGE_OPTIONS.filter((o) => o.value === '1M' || o.value === '3M' || o.value === '6M' || o.value === '1Y')
type View = 'line' | 'candle'
const VIEW_OPTIONS: { value: View; label: string }[] = [
  { value: 'line', label: '선' },
  { value: 'candle', label: '캔들' },
]
/** Extra calendar days fetched before the range so the 120-day average exists from the first visible bar. */
const WARMUP_DAYS = 200
/** The 52-week high/low needs a full year of bars whatever range is shown. */
const YEAR_DAYS = 370

export function AssetDetail() {
  const { symbol = '' } = useParams()
  const info = useAssetInfo(symbol)
  const [range, setRange] = useState<RangeKey>('3M')
  const [view, setView] = useState<View>('line')
  const [periods, setPeriods] = useState<number[]>(DEFAULT_MA_PERIODS)
  const holdings = useHoldings()
  const fx = useUsdKrw().data?.price
  const { currency, pick, format, formatOther, compact } = useMoney()
  const convert = useConvertCurrency()
  const [confirmConvert, setConfirmConvert] = useState(false)

  // Coins in the won view show the Upbit KRW market, the price KRW holdings are valued at.
  const base = info.data?.symbol ?? symbol
  const upbit = info.data?.asset_type === 'crypto' && currency === 'KRW'
  const chartSymbol = upbit ? `KRW-${displaySymbol(base)}` : base
  const start = rangeStart(range) ?? daysAgo(365)
  const fetchStart = [daysAgo(WARMUP_DAYS, new Date(`${start}T00:00:00`)), daysAgo(YEAR_DAYS)].sort()[0]
  const history = useHistory(chartSymbol, fetchStart)

  const resolved = info.data?.symbol ?? ''
  const position = holdings.data?.find((h) => h.symbol === resolved)
  // Only held symbols are forecast; the same query feeds the ForecastPanel below.
  const forecast = useForecast(resolved, position !== undefined)

  // Upbit bars are already in KRW; other market prices are USD and use today's rate.
  const krw = currency === 'KRW' && fx !== undefined
  const scale = upbit || !krw ? 1 : fx
  const allBars = history.data
  const chart = useMemo(() => {
    const bars = (allBars ?? []).map((b) => ({
      ...b,
      open: b.open * scale,
      high: b.high * scale,
      low: b.low * scale,
      close: b.close * scale,
    }))
    const found = bars.findIndex((b) => b.date >= start)
    const from = found < 0 ? 0 : found
    const closes = bars.map((b) => b.close)
    const ma: MaLine[] = periods.map((n) => ({ n, values: sma(closes, n).slice(from) }))
    return { all: bars, visible: bars.slice(from), ma, extremes: fiftyTwoWeek(bars) }
  }, [allBars, scale, start, periods])

  if (info.error) return <ErrorBox error={info.error} />
  if (!info.data) return <Muted>불러오는 중…</Muted>

  const coin = info.data.asset_type === 'crypto'
  const ticker = displaySymbol(resolved)
  const bars = chart.visible
  const last = chart.all.at(-1)
  const livePrice = position ? pick(position.price, position.price_krw) : last?.close
  const liveUsd = position ? position.price : last?.close
  const today = position ? { pct: position.day_change_pct } : dayChange(chart.all)
  // When the price is from: the holding's quote time, or for an unheld symbol its last bar's date.
  const asOf = position?.price_as_of ?? last?.date
  const quoteTime = asOf ? quoteTimeLabel(asOf) : undefined
  // Compare in the position's own currency so the verdict does not depend on the display toggle.
  const suspicious =
    position !== undefined &&
    isSuspiciousCost(
      position.currency === 'KRW' ? position.avg_cost_krw : position.avg_cost,
      position.currency === 'KRW' ? position.price_krw : position.price,
    )
  const avgCost = position ? pick(position.avg_cost, position.avg_cost_krw) : undefined
  const qty = position ? (coin ? `${formatQty(position.quantity)} ${ticker}` : `${formatQty(position.quantity)}주`) : ''
  const candleMa: CandleMa[] = chart.ma.map((m) => ({ ...m, ...(MA_STYLE[m.n] ?? { cssVar: '--muted' }) }))

  const togglePeriod = (n: number) =>
    setPeriods((prev) => (prev.includes(n) ? prev.filter((p) => p !== n) : [...prev, n].sort((a, b) => a - b)))

  return (
    <div className="space-y-6">
      <div>
        <Link to="/" className="text-xs text-muted hover:underline">← 홈</Link>
        <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h1 className="text-2xl font-bold">{ticker}</h1>
          <span className="text-sm text-muted">{coin ? `${info.data.name} · 코인` : `${info.data.name} · 미국 주식`}</span>
        </div>
        {livePrice !== undefined && (
          <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="num text-3xl font-bold">{format(livePrice)}</span>
            {krw && !upbit && liveUsd !== undefined && <span className="num text-sm text-ink-2">{formatUsd(liveUsd)}</span>}
            {quoteTime && <span className="text-sm text-muted">{quoteTime}</span>}
            {today && (
              <span className="text-sm">
                <span className="mr-1 text-muted">{changeLabel(asOf, 'short')}</span>
                <PnL pctOnly value={0} pct={today.pct} />
              </span>
            )}
          </div>
        )}
        {position && (
          <div className="num mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-ink-2">
            <span>
              {qty} · 평균 {format(avgCost ?? 0)} · 수익{' '}
              <PnL
                pctOnly
                value={pick(position.unrealized_pnl, position.unrealized_pnl_krw)}
                pct={pick(position.unrealized_pct, position.unrealized_pct_krw)}
              />
            </span>
            {suspicious && (
              <Link
                to="/transactions?check=1"
                title={`${PRICE_CHECK_REASON}. 스크린샷에서 평균단가를 잘못 읽었을 수 있어요. 거래 페이지에서 수정하세요.`}
                className="rounded-md bg-danger/10 px-1.5 py-0.5 text-[11px] font-semibold text-danger hover:underline"
              >
                단가 확인
              </Link>
            )}
          </div>
        )}
        {position && <GuruHolders symbol={resolved} />}
        {/* House filings name stock tickers only; coins never match, so skip the request for them. */}
        {position?.asset_type === 'stock' && <CongressMention symbol={resolved} />}
      </div>

      <Card
        title="가격과 예측"
        actions={<SegmentedControl label="기간" options={CHART_RANGES} value={range} onChange={setRange} />}
      >
        <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2">
          <SegmentedControl label="보기" options={VIEW_OPTIONS} value={view} onChange={setView} />
          <div role="group" aria-label="이동평균" className="flex flex-wrap gap-1.5">
            {MA_PERIODS.map((n) => {
              const on = periods.includes(n)
              return (
                <button
                  key={n}
                  type="button"
                  aria-pressed={on}
                  onClick={() => togglePeriod(n)}
                  className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px] font-medium transition-colors focus-visible:outline-2 focus-visible:outline-accent ${
                    on ? 'bg-accent-soft text-accent' : 'bg-fill text-ink-2 hover:text-ink'
                  }`}
                >
                  <span
                    aria-hidden="true"
                    className="inline-block h-0.5 w-3 rounded"
                    style={{ background: on ? `var(${MA_STYLE[n].cssVar})` : 'var(--axis)' }}
                  />
                  {n}일
                </button>
              )
            })}
          </div>
        </div>
        {history.error ? (
          <ErrorBox error={history.error} />
        ) : !history.data ? (
          <Skeleton className="h-80" />
        ) : bars.length === 0 ? (
          <Muted>이 기간의 시세가 없습니다.</Muted>
        ) : (
          <div className={history.isPlaceholderData ? 'opacity-50 transition-opacity' : ''}>
            {view === 'line' ? (
              <PriceForecastChart
                bars={bars}
                ma={chart.ma}
                horizons={forecast.data?.horizons}
                avgCost={avgCost}
                extremes={chart.extremes}
                format={format}
                compact={compact}
              />
            ) : (
              <CandleChart bars={bars} ma={candleMa} avgCost={avgCost} />
            )}
          </div>
        )}
        {/* The band itself is explained by the chart's legend and footnote; this only says when it is absent. */}
        <p className="mt-3 text-xs text-muted">
          {view === 'line' && !position
            ? '예측 띠는 보유 종목에만 그려집니다. '
            : view === 'candle'
              ? '캔들 보기에는 예측 띠가 없습니다. 선 보기로 바꾸면 보입니다. '
              : ''}
          {upbit ? '업비트 원화 시세. ' : krw ? '달러 시세를 오늘 환율로 환산했습니다. ' : '달러 시세. '}
          참고용이며 투자 조언이 아닙니다.
        </p>
      </Card>

      <Card title="앞으로 예상">
        {!holdings.data ? (
          <Muted>불러오는 중…</Muted>
        ) : position ? (
          <ForecastPanel symbol={resolved} fx={fx} />
        ) : (
          <p className="text-sm text-ink-2">
            예측은 보유 종목만 계산합니다. 이 종목을 보유하면 다음 거래일·1주·1개월 뒤 가격 범위를 보여 줍니다.
          </p>
        )}
      </Card>

      <Card title="내 보유">
        {!holdings.data ? (
          <Muted>불러오는 중…</Muted>
        ) : position ? (
          <dl className="divide-y divide-line">
            <InfoRow label="수량" value={qty} />
            <InfoRow
              label="평균 단가"
              value={
                <>
                  {format(pick(position.avg_cost, position.avg_cost_krw))}
                  <span className="ml-1.5 text-xs font-normal text-muted">
                    {formatOther(position.avg_cost, position.avg_cost_krw)}
                  </span>
                </>
              }
            />
            <InfoRow
              label="평가금액"
              value={
                <>
                  {format(pick(position.market_value, position.market_value_krw))}
                  <span className="ml-1.5 text-xs font-normal text-muted">
                    {formatOther(position.market_value, position.market_value_krw)}
                  </span>
                </>
              }
            />
            <InfoRow
              label="평가손익"
              value={
                <PnL
                  value={pick(position.unrealized_pnl, position.unrealized_pnl_krw)}
                  pct={pick(position.unrealized_pct, position.unrealized_pct_krw)}
                />
              }
            />
            <InfoRow label="실현손익" value={<PnL value={pick(position.realized_pnl, position.realized_pnl_krw)} />} />
            <InfoRow label="비중" value={`${position.weight.toFixed(1)}%`} />
          </dl>
        ) : (
          <Muted>보유하고 있지 않은 종목입니다.</Muted>
        )}
      </Card>

      {position && <RuleCard symbol={resolved} fx={fx} />}

      {position?.asset_type === 'crypto' && position.currency === 'USD' && (
        <Card>
          <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
            <p className="text-ink-2">
              이 코인은 달러로 기록되어 있습니다. 업비트·빗썸에서 산 코인이라면 원화로 전환하세요. 각 거래를
              거래일 환율로 원화로 바꿔 다시 기록합니다.
            </p>
            {confirmConvert ? (
              <span className="flex gap-2">
                <button
                  type="button"
                  className="rounded-lg bg-ink px-3 py-1.5 text-xs font-medium text-surface disabled:opacity-50"
                  disabled={convert.isPending}
                  onClick={() =>
                    convert.mutate({ symbol: resolved, currency: 'KRW' }, { onSettled: () => setConfirmConvert(false) })
                  }
                >
                  원화로 전환 확인
                </button>
                <button type="button" className="text-xs text-ink-2 hover:underline" onClick={() => setConfirmConvert(false)}>
                  취소
                </button>
              </span>
            ) : (
              <button
                type="button"
                className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium hover:bg-hover"
                onClick={() => setConfirmConvert(true)}
              >
                원화(업비트)로 전환
              </button>
            )}
          </div>
          {convert.error && (
            <div className="mt-3">
              <ErrorBox error={convert.error} />
            </div>
          )}
        </Card>
      )}

      <Card title="최근 해외 뉴스">
        <NewsCard symbol={resolved} />
      </Card>
    </div>
  )
}
