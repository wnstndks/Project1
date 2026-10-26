import type { ReactNode } from 'react'

import type { Bar } from '../api/client'
import { formatDate, formatKrwCompact } from '../lib/format'
import { closeChange, MA_STYLE } from '../lib/priceChart'
import { PnL } from './ui'

type Props = {
  /** The bar under the crosshair (or the last one), already in the display currency. */
  bar: Pick<Bar, 'date' | 'open' | 'high' | 'low' | 'close' | 'volume'>
  /** Close of the bar before `bar`; undefined (no earlier bar at all) hides the day-change figure. */
  prevClose?: number
  /** Enabled averages with their value on this bar (null while the window is still filling). */
  ma: { n: number; value: number | null }[]
  format: (v: number) => string
}

/**
 * One bar's figures in a row, for the candle view's corner readout: date, open/high/low/close,
 * the move against the previous close (`PnL`: sign, ▲▼ and colour together, the same helper as
 * the line tooltip and the home list), volume and the enabled averages. HTML on top of the
 * canvas so it follows the theme's CSS variables like the rest of the page.
 */
export function BarReadout({ bar, prevClose, ma, format }: Props) {
  const move = closeChange(bar.close, prevClose)
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-[11px] leading-4 text-ink">
      <span className="text-ink-2">{formatDate(bar.date, 'long')}</span>
      <Field label="시가" value={format(bar.open)} />
      <Field label="고가" value={format(bar.high)} />
      <Field label="저가" value={format(bar.low)} />
      <Field label="종가" value={format(bar.close)} strong />
      {move && <Field label="전일 대비" value={<PnL value={move.change} pct={move.changePct} format={format} />} />}
      <Field label="거래량" value={formatKrwCompact(bar.volume)} />
      {ma.map((m) =>
        m.value === null ? null : (
          <Field key={m.n} label={MA_STYLE[m.n]?.label ?? `${m.n}일 평균`} value={format(m.value)} />
        ),
      )}
    </div>
  )
}

function Field({ label, value, strong = false }: { label: string; value: ReactNode; strong?: boolean }) {
  return (
    <span className="whitespace-nowrap">
      <span className="mr-1 text-muted">{label}</span>
      <span className={`num ${strong ? 'font-semibold' : ''}`}>{value}</span>
    </span>
  )
}
