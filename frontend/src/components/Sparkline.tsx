import { sparklinePoints, sparklineTone } from '../lib/sparkline'

/**
 * 30-day price shape for a list row. Decorative: the row's numbers carry the information, so it is
 * hidden from assistive tech. With fewer than two closes it renders an empty box of the same size
 * so the columns stay aligned.
 */
export function Sparkline({ closes, width = 96, height = 32, className = '' }: {
  closes: number[]
  width?: number
  height?: number
  className?: string
}) {
  const values = closes.filter(Number.isFinite)
  if (values.length < 2) {
    return <span aria-hidden="true" className={`inline-block shrink-0 ${className}`} style={{ width, height }} />
  }
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={`shrink-0 overflow-visible ${className}`}
    >
      <polyline
        points={sparklinePoints(values, width, height)}
        fill="none"
        stroke={sparklineTone(values)}
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  )
}
