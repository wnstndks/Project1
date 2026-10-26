import { describe, expect, it } from 'vitest'

import type { CongressTrade } from '../api/client'
import { amountRange, distinctMembers, groupBySymbol, memberLine, ownerLabel, sideLabel, sortRecent } from './congress'

// Fictional members and tickers only (public repo): nothing from a real filing or a real account.
function trade(over: Partial<CongressTrade> = {}): CongressTrade {
  return {
    symbol: 'AAA',
    asset_name: 'Fake A Inc',
    asset_type: 'ST',
    member: 'Jane Doe',
    chamber: 'house',
    state: 'MD',
    district: 'MD06',
    party: null,
    owner: 'SP',
    side: 'buy',
    transaction_date: '2026-09-30',
    notification_date: '2026-10-01',
    filing_date: '2026-10-12',
    amount_low: 1001,
    amount_high: 15000,
    amount_label: '$1,001 - $15,000',
    cap_gains_over_200: null,
    doc_id: '20000001',
    doc_url: 'https://example.test/ptr/20000001.pdf',
    ...over,
  }
}

describe('labels', () => {
  it('words the Clerk side and owner codes in Korean and leaves unknown codes visible', () => {
    expect(sideLabel('buy')).toBe('매수')
    expect(sideLabel('sell')).toBe('매도')
    expect(sideLabel('sell_partial')).toBe('일부 매도')
    expect(sideLabel('exchange')).toBe('교환')
    expect(sideLabel('other')).toBe('other')
    expect(ownerLabel('SELF')).toBe('본인')
    expect(ownerLabel('SP')).toBe('배우자')
    expect(ownerLabel('DC')).toBe('자녀')
    expect(ownerLabel('JT')).toBe('공동')
    expect(ownerLabel('jt')).toBe('공동')
    expect(ownerLabel('XX')).toBe('XX')
  })

  it('writes the amount band with a tilde and "이상" for an open upper bound', () => {
    expect(amountRange(1001, 15000)).toBe('$1,001~$15,000')
    expect(amountRange(100001, 250000)).toBe('$100,001~$250,000')
    expect(amountRange(50_000_000, null)).toBe('$50,000,000 이상')
  })

  it('puts the district and the account owner on the member line', () => {
    expect(memberLine(trade())).toBe('Jane Doe (MD06) · 배우자 계좌')
    expect(memberLine(trade({ owner: 'SELF', district: '', state: 'TX' }))).toBe('Jane Doe (TX) · 본인 계좌')
    expect(memberLine(trade({ owner: 'JT', district: '', state: '' }))).toBe('Jane Doe · 공동 계좌')
  })
})

describe('grouping', () => {
  const trades = [
    trade({ symbol: 'AAA', member: 'Jane Doe', transaction_date: '2026-09-01', filing_date: '2026-09-20' }),
    trade({ symbol: 'BBB', asset_name: 'Fake B', member: 'John Roe', transaction_date: '2026-09-15' }),
    trade({ symbol: 'AAA', member: 'John Roe', transaction_date: '2026-09-30', filing_date: '2026-10-02' }),
    trade({ symbol: 'AAA', member: 'Jane Doe', transaction_date: '2026-09-30', filing_date: '2026-10-05' }),
  ]

  it('sorts most recent first, later filing first on the same day, without mutating', () => {
    const sorted = sortRecent(trades)
    expect(sorted.map((t) => `${t.member}:${t.transaction_date}:${t.filing_date}`)).toEqual([
      'Jane Doe:2026-09-30:2026-10-05',
      'John Roe:2026-09-30:2026-10-02',
      'John Roe:2026-09-15:2026-10-12',
      'Jane Doe:2026-09-01:2026-09-20',
    ])
    expect(trades[0].transaction_date).toBe('2026-09-01')
  })

  it('groups by ticker, most recently traded ticker first, trades newest first inside', () => {
    const groups = groupBySymbol(trades)
    expect(groups.map((g) => [g.symbol, g.name, g.trades.length])).toEqual([
      ['AAA', 'Fake A Inc', 3],
      ['BBB', 'Fake B', 1],
    ])
    expect(groups[0].trades.map((t) => t.filing_date)).toEqual(['2026-10-05', '2026-10-02', '2026-09-20'])
  })

  it('falls back to the asset name for a trade without a ticker and ignores ticker case', () => {
    const groups = groupBySymbol([
      trade({ symbol: null, asset_name: 'Private Fund' }),
      trade({ symbol: 'aaa' }),
      trade({ symbol: 'AAA' }),
    ])
    expect(groups.map((g) => [g.symbol, g.trades.length])).toEqual([
      ['Private Fund', 1],
      ['aaa', 2],
    ])
    expect(groupBySymbol([])).toEqual([])
  })

  it('counts members once each', () => {
    expect(distinctMembers(trades)).toBe(2)
    expect(distinctMembers([])).toBe(0)
  })
})
