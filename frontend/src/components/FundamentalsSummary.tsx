import { useHeldFundamentals } from '../api/hooks'
import {
  HELD_TITLE_KO,
  HELD_UNSUPPORTED_LABEL_KO,
  heldRows,
  heldSourceLine,
  heldUnsupported,
  NO_FIGURES_KO,
} from '../lib/fundamentals'
import { Disclosure, ListRow } from './ui'

/**
 * Home: the held stocks' published figures at a glance (D-036), folded by default. One row per
 * stock with PER, PBR, operating margin and revenue growth, linking to the asset page; the cells
 * wrap into two columns on a phone instead of a sideways table. Held ETFs are named in a footnote
 * (no statements). Hidden while loading, on an error and when no stock is held. Facts only: no
 * verdict, no gain/loss colour, no arrow.
 */
export function FundamentalsSummary() {
  const held = useHeldFundamentals()
  if (held.error || !held.data || held.data.items.length === 0) return null
  const rows = heldRows(held.data.items)
  const unsupported = heldUnsupported(held.data.items)
  return (
    <Disclosure card summary={HELD_TITLE_KO}>
      {rows.length > 0 && (
        <ul aria-label={HELD_TITLE_KO}>
          {rows.map((row) => (
            <li key={row.symbol}>
              <ListRow
                to={`/assets/${encodeURIComponent(row.symbol)}`}
                chevron
                title={row.ticker}
                subtitle={row.name}
                footer={
                  row.missing ? (
                    <p className="text-xs text-muted">{NO_FIGURES_KO}</p>
                  ) : (
                    <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 sm:grid-cols-4">
                      {row.cells.map((cell) => (
                        <div key={cell.label}>
                          <dt className="text-xs text-muted">{cell.label}</dt>
                          <dd className="num text-sm font-semibold text-ink">{cell.value}</dd>
                        </div>
                      ))}
                    </dl>
                  )
                }
              />
            </li>
          ))}
        </ul>
      )}
      {unsupported.length > 0 && (
        <p className="mt-2 text-xs text-muted">
          {HELD_UNSUPPORTED_LABEL_KO}: {unsupported.join(', ')}
        </p>
      )}
      <p className="mt-3 text-xs text-muted">
        {heldSourceLine(held.data)}. {held.data.disclaimer_ko}
      </p>
    </Disclosure>
  )
}
