import { describe, expect, it } from 'vitest'

import { changeLabel, isQuoteToday, latestAsOf, quoteTimeLabel } from './quoteTime'

// A Korean afternoon: the US session of the 22nd has closed, the 23rd's has not opened.
const today = new Date(2026, 9, 23, 14, 5)

describe('quote time wording', () => {
  it('compares the quote date with the local date', () => {
    expect(isQuoteToday('2026-10-23T00:00:00', today)).toBe(true)
    expect(isQuoteToday('2026-10-22T00:00:00', today)).toBe(false)
    expect(isQuoteToday('2026-10-23', today)).toBe(true)
  })

  it('picks the latest quote time across holdings', () => {
    expect(latestAsOf([])).toBeUndefined()
    expect(
      latestAsOf([{ price_as_of: '2026-10-22T00:00:00' }, { price_as_of: '2026-10-23T03:15:00' }]),
    ).toBe('2026-10-23T03:15:00')
  })

  it("says 오늘 only when the quote is from today, otherwise names the session's close", () => {
    expect(changeLabel('2026-10-23T03:15:00', 'date', today)).toBe('오늘')
    expect(changeLabel('2026-10-22T00:00:00', 'date', today)).toBe('10.22 종가 기준')
    expect(changeLabel('2025-12-31T00:00:00', 'date', today)).toBe('25.12.31 종가 기준')
    // Rows have no room for a date and say the always-true "전일 대비".
    expect(changeLabel('2026-10-22T00:00:00', 'short', today)).toBe('전일 대비')
    expect(changeLabel('2026-10-23T00:00:00', 'short', today)).toBe('오늘')
    // Still loading: never claim "오늘".
    expect(changeLabel(undefined, 'date', today)).toBe('전일 대비')
  })

  it('names a past bar by its date and a live quote by its clock time', () => {
    expect(quoteTimeLabel('2026-10-22T00:00:00', today)).toBe('10.22 종가 기준')
    expect(quoteTimeLabel('2026-10-22', today)).toBe('10.22 종가 기준')
    // A bar dated today is the session in progress; the change label covers it.
    expect(quoteTimeLabel('2026-10-23T00:00:00', today)).toBeUndefined()
    // Naive live timestamps are UTC: 03:15Z is 12:15 in Seoul (the test runs in the local zone).
    const live = new Date('2026-10-23T03:15:00Z')
    const pad = (n: number) => String(n).padStart(2, '0')
    const clock = `${pad(live.getHours())}:${pad(live.getMinutes())}`
    const sameDay = live.getDate() === today.getDate()
    expect(quoteTimeLabel('2026-10-23T03:15:00', today)).toBe(sameDay ? `${clock} 기준` : `10.22 ${clock} 기준`)
    // An explicit zone is honoured as is.
    expect(quoteTimeLabel('2026-10-23T03:15:00Z', today)).toBe(sameDay ? `${clock} 기준` : `10.22 ${clock} 기준`)
    // An older live quote keeps its date.
    expect(quoteTimeLabel('2026-10-20T15:30:00Z', today)).toMatch(/^10\.2[01] \d\d:\d\d 기준$/)
  })
})
