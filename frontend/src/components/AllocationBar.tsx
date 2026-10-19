import type { Summary } from '../api/client'
import { useMoney } from '../lib/currency'

const LABEL = { stock: '주식', crypto: '코인' } as const
const COLOR = { stock: 'var(--series-1)', crypto: 'var(--series-2)' } as const

/** Two asset classes: a single 100% bar reads better than a two-slice pie. */
export function AllocationBar({ allocation }: { allocation: Summary['allocation'] }) {
  const { pick, format } = useMoney()
  const parts = allocation.filter((a) => a.market_value > 0)
  return (
    <div>
      <div className="flex h-3 gap-0.5 overflow-hidden rounded" role="img" aria-label="자산군 비중">
        {parts.map((a) => (
          <div
            key={a.asset_type}
            title={`${LABEL[a.asset_type]} ${a.weight.toFixed(1)}%`}
            style={{ width: `${a.weight}%`, background: COLOR[a.asset_type] }}
          />
        ))}
      </div>
      <ul className="mt-3 space-y-1.5 text-sm">
        {allocation.map((a) => (
          <li key={a.asset_type} className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-2 text-ink-2">
              <span className="inline-block size-2.5 rounded-sm" style={{ background: COLOR[a.asset_type] }} />
              {LABEL[a.asset_type]}
            </span>
            <span className="num">
              <span className="font-semibold">{a.weight.toFixed(1)}%</span>
              <span className="ml-2 text-muted">{format(pick(a.market_value, a.market_value_krw))}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
