import { describe, expect, it } from 'vitest'

import {
  daysAgo,
  displaySymbol,
  formatKrwCompact,
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

  it('computes local dates and display symbols', () => {
    expect(daysAgo(1, new Date(2026, 0, 1))).toBe('2025-12-31')
    expect(displaySymbol('BTC-USD')).toBe('BTC')
    expect(displaySymbol('AAPL')).toBe('AAPL')
  })
})
