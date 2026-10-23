import { Link } from 'react-router-dom'

import type { HeldForecast, Holding, RuleCheck, Sparkline as SparklineData } from '../api/client'
import { useHeldForecasts, useRuleCheck } from '../api/hooks'
import { useMoney } from '../lib/currency'
import { weekRangeHint } from '../lib/forecast'
import { displaySymbol, formatQty } from '../lib/format'
import { isSuspiciousCost } from '../lib/holdings'
import { changeLabel } from '../lib/quoteTime'
import { RuleStatusChip } from './RuleStatusChip'
import { Sparkline } from './Sparkline'
import { ListRow, PnL } from './ui'

const AVATAR = { stock: 'var(--series-1)', crypto: 'var(--series-2)' } as const

/** Where the "단가 확인" badge sends the user: the check list on the transactions page. */
const CHECK_LINK = '/transactions?check=1'

/**
 * One row per holding, largest weight first (display order only). `sparklines` are the 30-day
 * closes from `/api/portfolio/sparklines`, joined by symbol; a holding without one gets an empty slot.
 * Forecasts and rule checks are each one request for the whole list, joined by symbol too.
 */
export function HoldingsList({ holdings, sparklines }: { holdings: Holding[]; sparklines?: SparklineData[] }) {
  const closes = new Map(sparklines?.map((s) => [s.symbol, s.closes]))
  // One request each for the whole list; a symbol without a model simply shows no hint.
  const forecasts = useHeldForecasts()
  const byHorizon = new Map(forecasts.data?.map((f) => [f.symbol, f]))
  const rules = useRuleCheck()
  const checks = new Map(rules.data?.checks.map((c) => [c.symbol, c]))
  const rows = [...holdings].sort((a, b) => b.weight - a.weight)
  return (
    <ul aria-label="보유 종목">
      {rows.map((h) => (
        <li key={h.symbol}>
          <HoldingRow
            holding={h}
            closes={closes.get(h.symbol) ?? []}
            forecast={byHorizon.get(h.symbol)}
            check={checks.get(h.symbol)}
          />
        </li>
      ))}
    </ul>
  )
}

function HoldingRow({
  holding: h,
  closes,
  forecast,
  check,
}: {
  holding: Holding
  closes: number[]
  forecast?: HeldForecast
  check?: RuleCheck
}) {
  const { pick, format } = useMoney()
  const ticker = displaySymbol(h.symbol)
  const coin = h.asset_type === 'crypto'
  const qty = coin ? `${formatQty(h.quantity)} ${ticker}` : `${formatQty(h.quantity)}주`
  // The backend names coins ("Bitcoin"); for stocks the name is still the ticker, so nothing is added.
  const name = h.name && h.name !== h.symbol && h.name !== ticker ? h.name : undefined
  const suspicious = isSuspiciousCost(h.avg_cost, h.price)
  const hint = weekRangeHint(forecast)

  return (
    <>
      <ListRow
        to={`/assets/${encodeURIComponent(h.symbol)}`}
        chevron
        avatar={
          // The ticker is repeated in the title, so the initial is decorative.
          <span
            aria-hidden="true"
            className="flex size-10 shrink-0 items-center justify-center rounded-full text-[15px] font-bold text-white"
            style={{ background: AVATAR[h.asset_type] }}
          >
            {ticker.charAt(0)}
          </span>
        }
        title={
          // The row's title column is `truncate` (nowrap, overflow hidden). Chips never shrink or get
          // clipped: when the column is narrow (phones, two chips) they wrap under the ticker instead.
          <span className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
            <span className="min-w-0 truncate">{ticker}</span>
            {suspicious && (
              <span
                className="shrink-0 rounded-md bg-danger/10 px-1.5 py-0.5 text-[11px] font-semibold text-danger"
                title="평균단가가 현재가와 20배 이상 차이 납니다. 거래 페이지에서 확인해 주세요."
              >
                단가 확인
              </span>
            )}
            {check && <RuleStatusChip status={check.status} label={check.chip_ko} className="shrink-0" />}
          </span>
        }
        subtitle={[name, qty, `비중 ${h.weight.toFixed(1)}%`].filter(Boolean).join(' · ')}
        middle={
          <>
            <Sparkline closes={closes} />
            <div className="num text-right sm:min-w-28">
              <div className="text-[15px] font-semibold text-ink">{format(pick(h.price, h.price_krw))}</div>
              <div className="mt-0.5 text-[13px]">
                <span className="mr-1 text-muted">{changeLabel(h.price_as_of, 'short')}</span>
                <PnL pctOnly digits={1} value={pick(h.day_change, h.day_change_krw)} pct={h.day_change_pct} />
              </div>
            </div>
          </>
        }
        value={format(pick(h.market_value, h.market_value_krw))}
        subValue={
          <PnL
            pctOnly
            digits={1}
            value={pick(h.unrealized_pnl, h.unrealized_pnl_krw)}
            pct={pick(h.unrealized_pct, h.unrealized_pct_krw)}
          />
        }
        footer={hint && <p className="text-xs text-muted">{hint}</p>}
      />
      {suspicious && (
        // Outside the row link (a link inside a link is invalid), aligned with the title text.
        <p className="-mt-1 pb-2 pl-[52px] text-xs">
          <Link to={CHECK_LINK} className="text-danger hover:underline">
            단가 확인 필요 · 거래에서 수정
          </Link>
        </p>
      )}
    </>
  )
}
