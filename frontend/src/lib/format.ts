const krw = new Intl.NumberFormat('ko-KR', { style: 'currency', currency: 'KRW', maximumFractionDigits: 0 })
const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })
const usdSmall = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 4,
})

export const formatKrw = (v: number) => krw.format(v)

/** Sub-dollar prices (e.g. XRP) keep 4 decimals so they don't round to $0.60. */
export const formatUsd = (v: number) => (Math.abs(v) > 0 && Math.abs(v) < 1 ? usdSmall : usd).format(v)

export function formatSignedUsd(v: number): string {
  const sign = v > 0 ? '+' : v < 0 ? '−' : ''
  return `${sign}${formatUsd(Math.abs(v))}`
}

export function formatPct(v: number, signed = true): string {
  const sign = signed && v > 0 ? '+' : v < 0 ? '−' : ''
  return `${sign}${Math.abs(v).toFixed(2)}%`
}

/** Up to 8 decimals for coins, trailing zeros trimmed. */
export function formatQty(v: number): string {
  return v.toLocaleString('en-US', { maximumFractionDigits: 8 })
}

/** Korean compact units for axis ticks: 4,500만 / 1.2억. */
export function formatKrwCompact(v: number): string {
  const abs = Math.abs(v)
  if (abs >= 1e8) return `${trim(v / 1e8)}억`
  if (abs >= 1e4) return `${trim(v / 1e4)}만`
  return v.toLocaleString('ko-KR')
}

function trim(v: number): string {
  return Number(v.toFixed(Math.abs(v) >= 100 ? 0 : 1)).toLocaleString('ko-KR')
}

/** YYYY-MM-DD in local time (toISOString would shift to UTC). */
export function isoDate(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function daysAgo(days: number, from = new Date()): string {
  const d = new Date(from)
  d.setDate(d.getDate() - days)
  return isoDate(d)
}

/** Display ticker: BTC-USD -> BTC. */
export const displaySymbol = (symbol: string) => symbol.replace(/-USD$/, '')
