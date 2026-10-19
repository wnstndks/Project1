import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { useAssetInfo, useHistory, useHoldings, useUsdKrw } from '../api/hooks'
import { CandleChart } from '../components/CandleChart'
import { Card, ErrorBox, Muted, PnL, SegmentedControl, StatTile } from '../components/ui'
import { useMoney } from '../lib/currency'
import { displaySymbol, formatQty, formatUsd } from '../lib/format'
import { RANGE_OPTIONS, rangeStart, type RangeKey } from '../lib/ranges'

const CHART_RANGES = RANGE_OPTIONS.filter((o) => o.value !== 'ALL')

export function AssetDetail() {
  const { symbol = '' } = useParams()
  const info = useAssetInfo(symbol)
  const [range, setRange] = useState<RangeKey>('6M')
  const history = useHistory(info.data?.symbol ?? symbol, rangeStart(range))
  const holdings = useHoldings()
  const fx = useUsdKrw().data?.price
  const { currency, pick, format, formatOther } = useMoney()

  if (info.error) return <ErrorBox error={info.error} />
  if (!info.data) return <Muted>불러오는 중…</Muted>

  // Market prices are quoted in USD; KRW figures use today's rate.
  const krw = currency === 'KRW' && fx !== undefined
  const toDisplay = (usd: number) => format(krw ? usd * fx : usd)

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
            {krw && <span className="text-sm text-ink-2">{formatUsd(last.close)}</span>}
            <span className="text-sm">
              <PnL value={krw ? change * fx : change} pct={changePct} />
              <span className="ml-1 text-muted">
                ({CHART_RANGES.find((r) => r.value === range)?.label})
              </span>
            </span>
          </div>
        )}
      </div>

      <Card
        title="가격 (USD)"
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
            value={
              <PnL
                value={pick(position.unrealized_pnl, position.unrealized_pnl_krw)}
                pct={pick(position.unrealized_pct, position.unrealized_pct_krw)}
              />
            }
            sub={`실현손익 ${format(pick(position.realized_pnl, position.realized_pnl_krw))}`}
          />
        </div>
      ) : (
        <Card>
          <Muted>보유하고 있지 않은 종목입니다.</Muted>
        </Card>
      )}

      <Card title="주가 예측">
        <Muted>LSTM 예측 기능은 준비 중입니다.</Muted>
      </Card>
    </div>
  )
}
