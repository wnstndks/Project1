import { Link } from 'react-router-dom'

import type { MissingHolding, Overlap } from '../api/client'
import { displaySymbol } from '../lib/format'
import { pct } from '../lib/gurus'

const MINE = 'var(--series-1)'
const THEIRS = 'var(--series-2)'

/**
 * One investor's overlap with my holdings: for each shared ticker, my weight and theirs as two
 * horizontal bars with the numbers beside them (bars share one scale within the card), then the
 * top positions of theirs that I do not hold as chips linking to the asset page.
 */
export function GuruOverlap({ name, overlaps, missing }: { name: string; overlaps: Overlap[]; missing: MissingHolding[] }) {
  const max = Math.max(0.01, ...overlaps.flatMap((o) => [o.my_weight_pct, o.guru_weight_pct]))
  return (
    <div className="space-y-4">
      <div>
        <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-2" aria-label="범례">
          <span className="flex items-center gap-1.5">
            <span aria-hidden="true" className="inline-block h-2.5 w-4 rounded-sm" style={{ background: MINE }} />
            내 비중
          </span>
          <span className="flex items-center gap-1.5">
            <span aria-hidden="true" className="inline-block h-2.5 w-4 rounded-sm" style={{ background: THEIRS }} />
            {name} 비중
          </span>
        </div>
        {overlaps.length === 0 ? (
          <p className="text-sm text-muted">내 보유 종목 중 {name}이(가) 들고 있는 종목이 없습니다.</p>
        ) : (
          <ul aria-label={`${name}과(와) 겹치는 종목`} className="divide-y divide-line">
            {overlaps.map((o) => (
              <li key={o.symbol} className="py-2.5">
                <div className="flex items-baseline justify-between gap-3">
                  <Link to={`/assets/${encodeURIComponent(o.symbol)}`} className="font-semibold text-ink hover:underline">
                    {displaySymbol(o.symbol)}
                  </Link>
                  <span className="truncate text-xs text-muted">{o.name}</span>
                </div>
                <WeightBar label="내 비중" value={o.my_weight_pct} max={max} color={MINE} />
                <WeightBar label={`${name} 비중`} value={o.guru_weight_pct} max={max} color={THEIRS} />
              </li>
            ))}
          </ul>
        )}
      </div>
      {missing.length > 0 && (
        <div>
          <div className="mb-1.5 text-xs text-ink-2">
            {name}의 상위 10종목 중 내게 없는 것 <span className="text-muted">(비중 순)</span>
          </div>
          <ul className="flex flex-wrap gap-1.5" aria-label={`${name}의 상위 종목 중 내게 없는 것`}>
            {missing.map((m) => (
              <li key={`${m.symbol ?? ''}:${m.name}`}>
                {m.symbol ? (
                  <Link
                    to={`/assets/${encodeURIComponent(m.symbol)}`}
                    className="inline-flex items-center gap-1 rounded-full bg-fill px-2.5 py-1 text-xs font-medium text-ink hover:bg-hover"
                    title={m.name}
                  >
                    {displaySymbol(m.symbol)}
                    <span className="num font-normal text-muted">{pct(m.weight_pct)}</span>
                  </Link>
                ) : (
                  <span
                    className="inline-flex items-center gap-1 rounded-full bg-fill px-2.5 py-1 text-xs text-ink-2"
                    title="티커가 없는 종목 (사모·현금 등)"
                  >
                    {m.name}
                    <span className="num text-muted">{pct(m.weight_pct)}</span>
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

/** Bar plus number: the number is the value, the bar is a visual aid scaled to the card's maximum. */
function WeightBar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  const width = `${Math.max(1, Math.min(100, (value / max) * 100))}%`
  return (
    <div className="mt-1 flex items-center gap-2 text-xs">
      <div className="h-2 flex-1 overflow-hidden rounded-sm bg-fill" role="img" aria-label={`${label} ${pct(value)}`}>
        <div className="h-full rounded-sm" style={{ width, background: color }} />
      </div>
      <span className="num w-14 text-right text-ink-2">{pct(value)}</span>
    </div>
  )
}
