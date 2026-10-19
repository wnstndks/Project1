import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { useAssetInfo, useConvertCurrency, useHistory, useHoldings, useUsdKrw } from '../api/hooks'
import { CandleChart } from '../components/CandleChart'
import { NewsCard } from '../components/NewsCard'
import { PredictionPanel } from '../components/PredictionPanel'
import { Card, ErrorBox, Muted, PnL, SegmentedControl, StatTile } from '../components/ui'
import { useMoney } from '../lib/currency'
import { displaySymbol, formatPct, formatQty, formatUsd } from '../lib/format'
import { RANGE_OPTIONS, rangeStart, type RangeKey } from '../lib/ranges'

const CHART_RANGES = RANGE_OPTIONS.filter((o) => o.value !== 'ALL')

export function AssetDetail() {
  const { symbol = '' } = useParams()
  const info = useAssetInfo(symbol)
  const [range, setRange] = useState<RangeKey>('6M')
  const holdings = useHoldings()
  const fx = useUsdKrw().data?.price
  const { currency, pick, format, formatOther } = useMoney()
  const convert = useConvertCurrency()
  const [confirmConvert, setConfirmConvert] = useState(false)
  // Coins in the won view show the Upbit KRW market, the price KRW holdings are valued at.
  const base = info.data?.symbol ?? symbol
  const upbit = info.data?.asset_type === 'crypto' && currency === 'KRW'
  const chartSymbol = upbit ? `KRW-${displaySymbol(base)}` : base
  const history = useHistory(chartSymbol, rangeStart(range))

  if (info.error) return <ErrorBox error={info.error} />
  if (!info.data) return <Muted>불러오는 중…</Muted>

  // Upbit bars are already in KRW; other market prices are USD and use today's rate.
  const krw = currency === 'KRW' && fx !== undefined
  const toDisplay = (price: number) => format(upbit || !krw ? price : price * fx)

  const resolved = info.data.symbol
  const position = holdings.data?.find((h) => h.symbol === resolved)
  const bars = history.data ?? []
  const last = bars.at(-1)
  const first = bars[0]
  const change = last && first ? last.close - first.close : 0
  const changePct = first ? (change / first.close) * 100 : 0

  return (
    <div className="space-y-6">
      <div>
        <Link to="/" className="text-xs text-muted hover:underline">← 대시보드</Link>
        <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h1 className="text-2xl font-semibold">{displaySymbol(resolved)}</h1>
          <span className="text-sm text-muted">
            {info.data.asset_type === 'crypto' ? `${info.data.name} · 코인` : '미국 주식'}
          </span>
        </div>
        {last && (
          <div className="mt-2 flex flex-wrap items-baseline gap-3">
            <span className="text-3xl font-semibold">{toDisplay(last.close)}</span>
            {krw && !upbit && <span className="text-sm text-ink-2">{formatUsd(last.close)}</span>}
            <span className="text-sm">
              <PnL value={upbit || !krw ? change : change * fx} pct={changePct} />
              <span className="ml-1 text-muted">
                ({CHART_RANGES.find((r) => r.value === range)?.label})
              </span>
            </span>
          </div>
        )}
      </div>

      <Card
        title={upbit ? '가격 (KRW · 업비트)' : '가격 (USD)'}
        actions={<SegmentedControl label="기간" options={CHART_RANGES} value={range} onChange={setRange} />}
      >
        {history.error ? (
          <ErrorBox error={history.error} />
        ) : (
          <div className={history.isPlaceholderData ? 'opacity-50 transition-opacity' : ''}>
            <CandleChart bars={bars} />
          </div>
        )}
      </Card>

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

      {position ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatTile label="보유 수량" value={formatQty(position.quantity)} sub={`비중 ${position.weight.toFixed(1)}%`} />
          <StatTile
            label="평균 단가"
            value={format(pick(position.avg_cost, position.avg_cost_krw))}
            sub={formatOther(position.avg_cost, position.avg_cost_krw)}
          />
          <StatTile
            label="평가금액"
            value={format(pick(position.market_value, position.market_value_krw))}
            sub={formatOther(position.market_value, position.market_value_krw)}
          />
          <StatTile
            label="평가손익"
            value={<PnL value={pick(position.unrealized_pnl, position.unrealized_pnl_krw)} />}
            sub={`${formatPct(pick(position.unrealized_pct, position.unrealized_pct_krw))} · 실현손익 ${format(
              pick(position.realized_pnl, position.realized_pnl_krw),
            )}`}
          />
        </div>
      ) : (
        <Card>
          <Muted>보유하고 있지 않은 종목입니다.</Muted>
        </Card>
      )}

      <Card title="최근 해외 뉴스">
        <NewsCard symbol={resolved} />
      </Card>

      <Card title="주가 예측">
        <PredictionPanel symbol={resolved} fx={fx} />
      </Card>
    </div>
  )
}
