import { displaySymbol } from '../lib/format'

const METHOD_KO: Record<string, string> = {
  ledoit_wolf: '축소 추정(Ledoit-Wolf)',
  identity: '겹치는 날이 적어 상관을 0으로 둠',
  single: '종목 1개',
  none: '계산 없음',
}

/**
 * Pairwise correlation of daily won returns as a table of tinted cells with the number in every
 * cell: the table is the data view, colour only underlines it. Diverging scale, two hues and a
 * neutral middle: blue (`--series-1`) for moving opposite, orange (`--series-2`) for moving
 * together, the page's fill at 0, mixed in OKLab so the ink stays readable in both themes.
 * A past-window figure, never a forecast; the caption says so.
 */
export function CorrelationHeatmap({ symbols, matrix, method, rows }: {
  symbols: string[]
  matrix: number[][]
  method: string
  rows: number
}) {
  if (symbols.length < 2) {
    return <p className="text-sm text-muted">상관을 계산할 종목이 2개 미만이에요.</p>
  }
  return (
    <div>
      <div className="-mx-6 overflow-x-auto px-6">
        <table className="num border-collapse text-sm" aria-label="종목 간 상관">
          <thead>
            <tr>
              <th scope="col" className="sr-only">종목</th>
              {symbols.map((s) => (
                <th key={s} scope="col" className="px-2 pb-1 text-xs font-medium text-muted">
                  {displaySymbol(s)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.map((row, i) => (
              <tr key={symbols[i]}>
                <th scope="row" className="pr-2 text-left text-xs font-medium text-ink-2">
                  {displaySymbol(symbols[i])}
                </th>
                {row.map((r, j) => (
                  <td
                    key={symbols[j]}
                    className="h-10 min-w-14 border-2 border-surface text-center text-ink"
                    style={{ background: cellBackground(r, i === j) }}
                    title={`${displaySymbol(symbols[i])} · ${displaySymbol(symbols[j])}: ${r.toFixed(2)}`}
                  >
                    {i === j ? <span className="text-muted">1</span> : r.toFixed(2)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-muted">
        −1 반대로 움직임 ← 0 → +1 같이 움직임 · {METHOD_KO[method] ?? method} · 겹치는 {rows}일 · 과거 값이며 미래를
        보장하지 않습니다.
      </p>
    </div>
  )
}

/** Tint by sign and strength, capped at 70% so the number stays legible on every step. */
function cellBackground(r: number, diagonal: boolean): string {
  if (diagonal || !Number.isFinite(r)) return 'var(--fill)'
  const strength = Math.min(Math.abs(r), 1) * 70
  const hue = r >= 0 ? 'var(--series-2)' : 'var(--series-1)'
  return `color-mix(in oklab, ${hue} ${strength.toFixed(0)}%, var(--fill))`
}
