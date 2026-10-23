import { describe, expect, it } from 'vitest'

import { livePrice, needsPriceCheck, priceCheckRows } from './transactionChecks'

const holdings = [
  { symbol: 'AAPL', quantity: 10, price: 200, price_krw: 280_000 },
  { symbol: 'BTC-USD', quantity: 0.5, price: 70_000, price_krw: 100_000_000 },
  { symbol: 'MSFT', quantity: 0, price: 400, price_krw: 560_000 },
]

describe('livePrice', () => {
  it('returns the holding price in the trade currency', () => {
    expect(livePrice({ symbol: 'AAPL', currency: 'USD' }, holdings)).toBe(200)
    expect(livePrice({ symbol: 'BTC-USD', currency: 'KRW' }, holdings)).toBe(100_000_000)
  })

  it('is undefined for symbols that are not held any more', () => {
    expect(livePrice({ symbol: 'MSFT', currency: 'USD' }, holdings)).toBeUndefined()
    expect(livePrice({ symbol: 'TSLA', currency: 'USD' }, holdings)).toBeUndefined()
  })
})

describe('needsPriceCheck', () => {
  it('flags a price 20x below or above today', () => {
    expect(needsPriceCheck({ symbol: 'AAPL', currency: 'USD', price: 7 }, holdings)).toBe(true)
    expect(needsPriceCheck({ symbol: 'AAPL', currency: 'USD', price: 5_000 }, holdings)).toBe(true)
  })

  it('accepts ordinary prices and compares won trades against the won price', () => {
    expect(needsPriceCheck({ symbol: 'AAPL', currency: 'USD', price: 150 }, holdings)).toBe(false)
    expect(needsPriceCheck({ symbol: 'BTC-USD', currency: 'KRW', price: 95_000_000 }, holdings)).toBe(false)
    // A won amount recorded as a dollar price is caught the other way round.
    expect(needsPriceCheck({ symbol: 'BTC-USD', currency: 'USD', price: 95_000_000 }, holdings)).toBe(true)
  })

  it('skips closed and unknown positions', () => {
    expect(needsPriceCheck({ symbol: 'MSFT', currency: 'USD', price: 1 }, holdings)).toBe(false)
    expect(needsPriceCheck({ symbol: 'TSLA', currency: 'USD', price: 1 }, holdings)).toBe(false)
  })
})

describe('priceCheckRows', () => {
  it('keeps only flagged trades, grouped by symbol and oldest first', () => {
    const rows = [
      { id: 1, symbol: 'BTC-USD', currency: 'KRW' as const, price: 95_000_000, trade_date: '2026-10-01' },
      { id: 2, symbol: 'AAPL', currency: 'USD' as const, price: 7, trade_date: '2026-10-20' },
      { id: 3, symbol: 'AAPL', currency: 'USD' as const, price: 180, trade_date: '2026-09-01' },
      { id: 4, symbol: 'AAPL', currency: 'USD' as const, price: 5, trade_date: '2026-10-02' },
      { id: 5, symbol: 'BTC-USD', currency: 'USD' as const, price: 95_000_000, trade_date: '2026-10-03' },
      { id: 6, symbol: 'MSFT', currency: 'USD' as const, price: 1, trade_date: '2026-10-03' }, // closed
    ]
    expect(priceCheckRows(rows, holdings).map((t) => t.id)).toEqual([4, 2, 5])
    expect(priceCheckRows([], holdings)).toEqual([])
  })
})
