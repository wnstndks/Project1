/** Line color from the move over the whole window: up red, down blue (Korean convention), flat gray. */
export function sparklineTone(closes: number[]): string {
  const first = closes[0]
  const last = closes[closes.length - 1]
  return last > first ? 'var(--gain-mark)' : last < first ? 'var(--loss-mark)' : 'var(--muted)'
}

/** SVG polyline points, one per close, scaled to the box with `pad` so a 2px stroke stays inside. */
export function sparklinePoints(closes: number[], width: number, height: number, pad = 1.5): string {
  const min = Math.min(...closes)
  const max = Math.max(...closes)
  const span = max - min
  const n = closes.length
  return closes
    .map((v, i) => {
      const x = pad + (i / (n - 1)) * (width - pad * 2)
      const y = span === 0 ? height / 2 : pad + ((max - v) / span) * (height - pad * 2)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
}
