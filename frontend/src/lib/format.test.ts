import { describe, expect, it } from 'vitest'

import {
  daysAgo,
  displaySymbol,
  formatDate,
  formatKrwCompact,
  formatKrwShort,
  formatPct,
  formatQty,
  formatSignedUsd,
  formatUsd,
} from './format'

describe('format', () => {
  it('formats USD with extra precision below a dollar', () => {
    expect(formatUsd(1234.5)).toBe('$1,234.50')
    expect(formatUsd(0.61234)).toBe('$0.6123')
  })

  it('signs P&L with a real minus sign', () => {
    expect(formatSignedUsd(12.3)).toBe('+$12.30')
    expect(formatSignedUsd(-12.3)).toBe('−$12.30')
    expect(formatPct(-0.8454)).toBe('−0.85%')
    expect(formatPct(3)).toBe('+3.00%')
  })

  it('keeps coin quantities up to 8 decimals', () => {
    expect(formatQty(0.12345678)).toBe('0.12345678')
    expect(formatQty(1500)).toBe('1,500')
  })

  it('uses Korean units for compact KRW', () => {
    expect(formatKrwCompact(44_884_150)).toBe('4,488만')
    expect(formatKrwCompact(123_000_000)).toBe('1.2억')
    expect(formatKrwCompact(5_000)).toBe('5,000')
  })

  it('rounds won for sentences with the unit attached', () => {
    expect(formatKrwShort(15_372_000)).toBe('1,537만원')
    expect(formatKrwShort(210_000_000)).toBe('2.10억원')
    expect(formatKrwShort(-15_372_000)).toBe('−1,537만원')
    expect(formatKrwShort(5_000)).toBe('5,000원')
  })

  it('formats percentages to a chosen number of decimals', () => {
    expect(formatPct(-3.567, true, 1)).toBe('−3.6%')
    expect(formatPct(4.5, true, 1)).toBe('+4.5%')
  })

  it('writes dates for people, adding the year only when it is not this year', () => {
    const today = new Date(2026, 9, 23)
    expect(formatDate('2026-10-23', 'short', today)).toBe('10.23')
    expect(formatDate('2026-10-23', 'long', today)).toBe('10월 23일 (금)')
    expect(formatDate('2026-01-05', 'short', today)).toBe('1.5')
    expect(formatDate('2025-12-31', 'short', today)).toBe('25.12.31')
    expect(formatDate('2025-12-31', 'long', today)).toBe('2025년 12월 31일 (수)')
    // Datetimes are read by their date part; garbage is passed through rather than thrown.
    expect(formatDate('2026-10-23T14:05:00', 'long', today)).toBe('10월 23일 (금)')
    expect(formatDate('n/a', 'short', today)).toBe('n/a')
  })

  it('computes local dates and display symbols', () => {
    expect(daysAgo(1, new Date(2026, 0, 1))).toBe('2025-12-31')
    expect(displaySymbol('BTC-USD')).toBe('BTC')
    expect(displaySymbol('AAPL')).toBe('AAPL')
  })
})
