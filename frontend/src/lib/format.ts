const krw = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 0 })
const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })
const usdSmall = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 4,
})

/** 1,234,567원: Korean apps write the unit after the number rather than a ₩ prefix. */
export const formatKrw = (v: number) => `${krw.format(v)}원`

/** Sub-dollar prices (e.g. XRP) keep 4 decimals so they don't round to $0.60. */
export const formatUsd = (v: number) => (Math.abs(v) > 0 && Math.abs(v) < 1 ? usdSmall : usd).format(v)

/** Prefix a sign with a real minus (−) and format the absolute value. */
export function signed(v: number, format: (abs: number) => string): string {
  const sign = v > 0 ? '+' : v < 0 ? '−' : ''
  return `${sign}${format(Math.abs(v))}`
}

export const formatSignedUsd = (v: number) => signed(v, formatUsd)

export function formatUsdCompact(v: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(v)
}

export function formatPct(v: number, signed = true, digits = 2): string {
  const sign = signed && v > 0 ? '+' : v < 0 ? '−' : ''
  return `${sign}${Math.abs(v).toFixed(digits)}%`
}

/** Rounded won for sentences: 1,537만원 / 2.10억원. Below 1만 falls back to 1,234원. */
export function formatKrwShort(v: number): string {
  const abs = Math.abs(v)
  const sign = v < 0 ? '−' : ''
  if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(2)}억원`
  if (abs >= 1e4) return `${sign}${Math.round(abs / 1e4).toLocaleString('ko-KR')}만원`
  return formatKrw(v)
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

const WEEKDAY = ['일', '월', '화', '수', '목', '금', '토']

/**
 * Dates for people: `10.23` (short) or `10월 23일 (목)` (long). The year is added only when it
 * differs from `today`'s (`25.10.23`, `2025년 10월 23일 (목)`), so a ledger from last year stays
 * unambiguous while this year's dates stay short. Accepts an ISO date or datetime string.
 */
export function formatDate(iso: string, style: 'short' | 'long' = 'short', today = new Date()): string {
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`)
  if (Number.isNaN(d.getTime())) return iso
  const sameYear = d.getFullYear() === today.getFullYear()
  const month = d.getMonth() + 1
  const day = d.getDate()
  if (style === 'short') return `${sameYear ? '' : `${String(d.getFullYear()).slice(2)}.`}${month}.${day}`
  return `${sameYear ? '' : `${d.getFullYear()}년 `}${month}월 ${day}일 (${WEEKDAY[d.getDay()]})`
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
