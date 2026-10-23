import { describe, expect, it } from 'vitest'

import { dayChange, fiftyTwoWeek, sma } from './indicators'

describe('sma', () => {
  it('averages the trailing window and leaves the first n−1 entries null', () => {
    expect(sma([1, 2, 3, 4, 5], 3)).toEqual([null, null, 2, 3, 4])
  })

  it('is the identity for a window of one and all-null when the series is too short', () => {
    expect(sma([7, 8], 1)).toEqual([7, 8])
    expect(sma([1, 2, 3], 5)).toEqual([null, null, null])
    expect(sma([], 3)).toEqual([])
  })

  it('returns nulls only for a non-positive window', () => {
    expect(sma([1, 2], 0)).toEqual([null, null])
  })

  it('matches a direct average without drift over a long series', () => {
    const values = Array.from({ length: 500 }, (_, i) => 100 + Math.sin(i / 7) * 10 + (i % 3) * 0.01)
    const out = sma(values, 20)
    const direct = values.slice(480).reduce((a, b) => a + b, 0) / 20
    expect(out[499]).toBeCloseTo(direct, 8)
    expect(out[18]).toBeNull()
    expect(out[19]).not.toBeNull()
  })
})

describe('fiftyTwoWeek', () => {
  const bar = (date: string, high: number, low: number) => ({ date, high, low })

  it('returns null without bars', () => {
    expect(fiftyTwoWeek([])).toBeNull()
  })

  it('picks the highest high and lowest low with their dates', () => {
    const bars = [
      bar('2026-01-05', 10, 9),
      bar('2026-02-10', 15, 12),
      bar('2026-03-20', 13, 8),
      bar('2026-04-01', 14, 11),
    ]
    expect(fiftyTwoWeek(bars)).toEqual({ high: 15, highDate: '2026-02-10', low: 8, lowDate: '2026-03-20' })
  })

  it('ignores bars older than 365 days before the last bar', () => {
    const bars = [bar('2024-10-01', 99, 1), bar('2025-10-20', 5, 2), bar('2025-10-25', 20, 18), bar('2026-10-21', 22, 19)]
    expect(fiftyTwoWeek(bars)).toEqual({ high: 22, highDate: '2026-10-21', low: 18, lowDate: '2025-10-25' })
  })
})

describe('dayChange', () => {
  it('compares the last two closes', () => {
    const r = dayChange([{ close: 100 }, { close: 102 }])
    expect(r?.change).toBe(2)
    expect(r?.pct).toBeCloseTo(2)
  })

  it('needs two bars with a positive previous close', () => {
    expect(dayChange([{ close: 100 }])).toBeNull()
    expect(dayChange([{ close: 0 }, { close: 5 }])).toBeNull()
  })
})
