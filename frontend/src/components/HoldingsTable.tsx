import { Link } from 'react-router-dom'

import type { Holding } from '../api/client'
import { useMoney } from '../lib/currency'
import { displaySymbol, formatQty } from '../lib/format'
import { PnL } from './ui'

export function HoldingsTable({ holdings }: { holdings: Holding[] }) {
  const { pick, format } = useMoney()
  return (
    <div className="-mx-5 overflow-x-auto">
      <table className="w-full min-w-[720px] text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs text-muted">
            <th className="px-5 py-2 font-medium">종목</th>
            <th className="px-3 py-2 text-right font-medium">수량</th>
            <th className="px-3 py-2 text-right font-medium">평균 단가</th>
            <th className="px-3 py-2 text-right font-medium">현재가</th>
            <th className="px-3 py-2 text-right font-medium">평가금액</th>
            <th className="px-3 py-2 text-right font-medium">평가손익</th>
            <th className="px-5 py-2 text-right font-medium">비중</th>
          </tr>
        </thead>
        <tbody className="num">
          {holdings.map((h) => (
            <tr key={h.symbol} className="border-b border-line last:border-0 hover:bg-hover">
              <td className="px-5 py-2.5">
                <Link to={`/assets/${h.symbol}`} className="font-semibold hover:underline">
                  {displaySymbol(h.symbol)}
                </Link>
                <span className="ml-2 text-xs text-muted">
                  {h.asset_type === 'crypto' ? h.name : '주식'}
                </span>
              </td>
              <td className="px-3 py-2.5 text-right">{formatQty(h.quantity)}</td>
              <td className="px-3 py-2.5 text-right">{format(pick(h.avg_cost, h.avg_cost_krw))}</td>
              <td className="px-3 py-2.5 text-right">{format(pick(h.price, h.price_krw))}</td>
              <td className="px-3 py-2.5 text-right font-medium">
                {format(pick(h.market_value, h.market_value_krw))}
              </td>
              <td className="px-3 py-2.5 text-right">
                <PnL
                  value={pick(h.unrealized_pnl, h.unrealized_pnl_krw)}
                  pct={pick(h.unrealized_pct, h.unrealized_pct_krw)}
                />
              </td>
              <td className="px-5 py-2.5 text-right text-ink-2">{h.weight.toFixed(1)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
