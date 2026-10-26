import { describe, expect, it } from 'vitest'

import { buildRows, closeChange, isNear, labelSide, priceDomain, tickLabel } from './priceChart'

const bar = (
  date: string,
  close: number,
  volume = 1000,
  open = close,
  high = Math.max(open, close),
  low = Math.min(open, close),
) => ({ date, open, high, low, close, volume })
const t = (d: string) => new Date(`${d}T00:00:00`).getTime()

describe('buildRows', () => {
  const bars = [bar('2026-10-19', 100), bar('2026-10-20', 102), bar('2026-10-21', 101)]

  it('keeps one row per bar with the enabled averages and the up/down flag', () => {
    const rows = buildRows(bars, [{ n: 2, values: [null, 101, 101.5] }])
    expect(rows).toHaveLength(3)
    expect(rows[0]).toMatchObject({ t: t('2026-10-19'), close: 100, volume: 1000, up: true, ma2: undefined })
    expect(rows[1]).toMatchObject({ up: true, ma2: 101 })
    expect(rows[2]).toMatchObject({ up: false, ma2: 101.5 })
    // No horizons: no fan, and no anchor dot on the last close either.
    expect(rows[2].mid).toBeUndefined()
    expect(rows[2].band).toBeUndefined()
  })

  it('starts the forecast band at the last close and re-anchors the quantiles on it', () => {
    const horizons = [
      { target_date: '2026-10-22', base_price: 100, p10: 98, p50: 100.5, p90: 103 },
      { target_date: '2026-10-28', base_price: 100, p10: 95, p50: 101, p90: 107 },
    ]
    const rows = buildRows(bars, [], horizons)
    expect(rows).toHaveLength(5)
    expect(rows[2]).toMatchObject({ close: 101, mid: 101, band: [101, 101] })
    // The last close (101) is 1% above the model's base, so every quantile scales by 1.01.
    expect(rows[3].t).toBe(t('2026-10-22'))
    expect(rows[3].mid).toBeCloseTo(101.505)
    expect(rows[3].band?.[0]).toBeCloseTo(98.98)
    expect(rows[3].band?.[1]).toBeCloseTo(104.03)
    expect(rows[3].close).toBeUndefined()
    expect(rows[3].volume).toBeUndefined()
  })

  it('skips horizons that are not after the last bar and sorts the rest by date', () => {
    const horizons = [
      { target_date: '2026-11-20', base_price: 100, p10: 90, p50: 100, p90: 110 },
      { target_date: '2026-10-21', base_price: 100, p10: 99, p50: 100, p90: 101 },
      { target_date: '2026-10-22', base_price: 100, p10: 98, p50: 100, p90: 102 },
    ]
    const rows = buildRows(bars, [], horizons)
    expect(rows.slice(3).map((r) => r.t)).toEqual([t('2026-10-22'), t('2026-11-20')])
  })

  it('returns no forecast rows without bars', () => {
    expect(buildRows([], [], [{ target_date: '2026-10-22', base_price: 100, p10: 1, p50: 2, p90: 3 }])).toEqual([])
  })

  it('puts the forecast median and band edges as percents from the last close', () => {
    const rows = buildRows(bars, [], [{ target_date: '2026-10-28', base_price: 100, p10: 95, p50: 101, p90: 107 }])
    // Anchored on 101: mid 102.01 (+1%), band 95.95~108.07 (−5%~+7%).
    expect(rows[3].midPct).toBeCloseTo(1)
    expect(rows[3].bandPct?.[0]).toBeCloseTo(-5)
    expect(rows[3].bandPct?.[1]).toBeCloseTo(7)
    // Past rows carry no forecast percents; forecast rows carry no day figures.
    expect(rows[2].midPct).toBeUndefined()
    expect(rows[3].change).toBeUndefined()
    expect(rows[3].high).toBeUndefined()
  })
})

describe('buildRows day change', () => {
  const bars = [bar('2026-10-19', 100), bar('2026-10-20', 102), bar('2026-10-21', 101)]

  it('carries open, high and low, and the change against the previous bar', () => {
    const rows = buildRows([bar('2026-10-19', 100, 1000, 99, 104, 98), bar('2026-10-20', 102)], [])
    expect(rows[0]).toMatchObject({ open: 99, high: 104, low: 98, close: 100 })
    expect(rows[1].change).toBe(2)
    expect(rows[1].changePct).toBeCloseTo(2)
    expect(rows[1].up).toBe(true)
  })

  it('leaves the first bar without a change unless prevClose is given', () => {
    const [first] = buildRows(bars, [])
    expect(first.change).toBeUndefined()
    expect(first.changePct).toBeUndefined()
    // With the close before the window the first bar gets its move, and its up/down flag follows it.
    const [withPrev] = buildRows(bars, [], [], 104)
    expect(withPrev.change).toBe(-4)
    expect(withPrev.changePct).toBeCloseTo((-4 / 104) * 100)
    expect(withPrev.up).toBe(false)
  })

  it('is negative on a down day', () => {
    const rows = buildRows(bars, [])
    expect(rows[2].change).toBeCloseTo(-1)
    expect(rows[2].changePct).toBeCloseTo((-1 / 102) * 100)
    expect(rows[2].up).toBe(false)
  })

  it('closeChange ignores a missing, zero or invalid previous close', () => {
    expect(closeChange(100, undefined)).toBeUndefined()
    expect(closeChange(100, 0)).toBeUndefined()
    expect(closeChange(100, Number.NaN)).toBeUndefined()
    const move = closeChange(103, 100)
    expect(move?.change).toBe(3)
    expect(move?.changePct).toBeCloseTo(3)
  })
})

describe('priceDomain', () => {
  it('pads below for the volume strip and above for labels', () => {
    const rows = buildRows([bar('2026-10-19', 100), bar('2026-10-20', 110)], [])
    const [lo, hi] = priceDomain(rows)
    expect(lo).toBeCloseTo(100 - 10 * 0.33)
    expect(hi).toBeCloseTo(110 + 10 * 0.08)
  })

  it('keeps highs, lows and day changes off the price axis', () => {
    // A wild wick (1~500) and a +100% change against prevClose 50 must not stretch the axis.
    const rows = buildRows([bar('2026-10-19', 100, 1000, 100, 500, 1), bar('2026-10-20', 110)], [], [], 50)
    const [lo, hi] = priceDomain(rows)
    expect(lo).toBeCloseTo(100 - 10 * 0.33)
    expect(hi).toBeCloseTo(110 + 10 * 0.08)
  })

  it('includes nearby extras but ignores far-away ones', () => {
    const rows = buildRows([bar('2026-10-19', 100), bar('2026-10-20', 110)], [])
    const [near] = priceDomain(rows, [97])
    expect(near).toBeCloseTo(97 - 13 * 0.33)
    const [far] = priceDomain(rows, [4])
    expect(far).toBeCloseTo(100 - 10 * 0.33)
  })

  it('counts band edges and averages, and falls back to [0, 1] with no data', () => {
    const rows = buildRows([bar('2026-10-19', 100)], [{ n: 5, values: [120] }], [
      { target_date: '2026-10-22', base_price: 100, p10: 80, p50: 100, p90: 130 },
    ])
    const [lo, hi] = priceDomain(rows)
    expect(lo).toBeLessThan(80)
    expect(hi).toBeGreaterThan(130)
    expect(priceDomain([])).toEqual([0, 1])
  })

  it('isNear accepts values within half the span of either end', () => {
    expect(isNear(95, 100, 110)).toBe(true)
    expect(isNear(94, 100, 110)).toBe(false)
    expect(isNear(115, 100, 110)).toBe(true)
    expect(isNear(Number.NaN, 100, 110)).toBe(false)
  })
})

describe('tickLabel', () => {
  const today = new Date(2026, 9, 23)

  it('switches from month.day to yy.month on long windows', () => {
    expect(tickLabel(t('2026-10-05'), 90, today)).toBe('10.5')
    expect(tickLabel(t('2026-10-05'), 365, today)).toBe('26.10')
  })

  it('prefixes the year on short windows that reach into last year', () => {
    expect(tickLabel(t('2025-12-15'), 90, today)).toBe('25.12.15')
  })
})

describe('labelSide', () => {
  it('labels to the right except in the last fifth of the window', () => {
    expect(labelSide(10, 0, 100)).toBe('right')
    expect(labelSide(80, 0, 100)).toBe('right')
    expect(labelSide(81, 0, 100)).toBe('left')
    expect(labelSide(5, 5, 5)).toBe('right')
  })
})
