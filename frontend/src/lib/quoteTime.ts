import { formatDate, isoDate } from './format'

/**
 * Wording for *when* a price is from. US stocks trade while Korea sleeps, so during the Korean
 * day the latest quote is the previous session's close and "오늘 ▲1.2%" would be wrong: that move
 * happened yesterday (US time). The backend sends `price_as_of` as a naive ISO timestamp: a bar
 * date at midnight for a daily close (yfinance), or a UTC clock time for a live trade (Upbit).
 */

const datePart = (iso: string) => iso.slice(0, 10)

/** Whether the quote's date is today's local date. */
export function isQuoteToday(asOf: string, today = new Date()): boolean {
  return datePart(asOf) === isoDate(today)
}

/** The most recent quote time among holdings (ISO strings compare lexically). */
export function latestAsOf(items: { price_as_of: string }[]): string | undefined {
  return items.reduce<string | undefined>(
    (latest, h) => (latest === undefined || h.price_as_of > latest ? h.price_as_of : latest),
    undefined,
  )
}

/**
 * Label for the day's change. `date` names the session ("10.22 종가 기준") for the home header;
 * `short` says "전일 대비" where there is no room (list rows, beside the quote time). Without a
 * quote time (still loading) it stays with the always-true "전일 대비".
 */
export function changeLabel(asOf: string | undefined, style: 'date' | 'short', today = new Date()): string {
  if (asOf === undefined) return '전일 대비'
  if (isQuoteToday(asOf, today)) return '오늘'
  return style === 'short' ? '전일 대비' : `${formatDate(asOf, 'short', today)} 종가 기준`
}

const HAS_ZONE = /(?:[Zz]|[+-]\d\d:?\d\d)$/

/**
 * When the price is from, beside the price itself: "10.22 종가 기준" for a past bar, "14:05 기준"
 * for a live quote today ("10.22 14:05 기준" if it is older). A bar dated today is the session in
 * progress; the change label already says "오늘" then, so this returns undefined to avoid "오늘 기준 · 오늘".
 */
export function quoteTimeLabel(asOf: string, today = new Date()): string | undefined {
  const [date, time] = asOf.split('T')
  if (!time || time.startsWith('00:00:00')) {
    return isQuoteToday(date, today) ? undefined : `${formatDate(date, 'short', today)} 종가 기준`
  }
  // Naive timestamps are UTC (see module note); a zone, if present, is honoured.
  const d = new Date(HAS_ZONE.test(asOf) ? asOf : `${asOf}Z`)
  if (Number.isNaN(d.getTime())) return `${formatDate(date, 'short', today)} 기준`
  const pad = (n: number) => String(n).padStart(2, '0')
  const clock = `${pad(d.getHours())}:${pad(d.getMinutes())}`
  const local = isoDate(d)
  return local === isoDate(today) ? `${clock} 기준` : `${formatDate(local, 'short', today)} ${clock} 기준`
}
