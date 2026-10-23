import { describe, expect, it } from 'vitest'

import type { HistoryPoint } from '../api/client'
import { daysAgo } from './format'
import { historySpanDays, MIN_HISTORY_DAYS, shortestCoveringRange } from './history'

const point = (date: string): HistoryPoint => ({
  date,
  market_value: 1,
  market_value_krw: 1400,
  cost_basis: 1,
  cost_basis_krw: 1400,
})

describe('historySpanDays', () => {
  it('counts calendar days from the first point to today, inclusive', () => {
    const today = new Date(2026, 9, 22)
    expect(historySpanDays([point('2026-10-22')], today)).toBe(1)
    expect(historySpanDays([point('2026-10-21'), point('2026-10-22')], today)).toBe(2)
    expect(historySpanDays([point('2026-10-16')], today)).toBe(MIN_HISTORY_DAYS)
    expect(historySpanDays([point('2026-10-17')], today)).toBeLessThan(MIN_HISTORY_DAYS)
  })

  it('uses the earliest date whatever the order and is 0 without points', () => {
    const today = new Date(2026, 9, 22)
    expect(historySpanDays([point('2026-10-20'), point('2026-09-22')], today)).toBe(31)
    expect(historySpanDays([], today)).toBe(0)
  })
})

describe('shortestCoveringRange', () => {
  it('picks the shortest preset that still starts before the first point', () => {
    expect(shortestCoveringRange([point(daysAgo(10))])).toBe('1M')
    expect(shortestCoveringRange([point(daysAgo(40))])).toBe('3M')
    expect(shortestCoveringRange([point(daysAgo(200))])).toBe('1Y')
    expect(shortestCoveringRange([point(daysAgo(400))])).toBe('3Y')
    expect(shortestCoveringRange([point(daysAgo(2000))])).toBe('ALL')
    expect(shortestCoveringRange([])).toBe('ALL')
  })
})
