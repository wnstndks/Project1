import { describe, expect, it } from 'vitest'

import type { Guru, GuruCompare } from '../api/client'
import { holdersOf, holdersSentence, isLoaded, needsSecUserAgent, overlapCounts, overlapSentence, shortName } from './gurus'

function guru(over: Partial<Guru>): Guru {
  return {
    id: 'cathie-wood',
    name_ko: '캐시 우드',
    name_en: 'Cathie Wood',
    source: 'ark',
    note: '',
    synced_at: '2026-10-22T01:00:00Z',
    as_of: '2026-10-21',
    stale: false,
    error: null,
    sync_note: null,
    holdings_count: 200,
    ...over,
  }
}

const gurus: GuruCompare[] = [
  {
    guru: guru({}),
    overlaps: [
      { symbol: 'AAA', name: 'Fake A', my_weight_pct: 60, guru_weight_pct: 2.14 },
      { symbol: 'BBB', name: 'Fake B', my_weight_pct: 40, guru_weight_pct: 0.5 },
    ],
    top_missing: [],
  },
  {
    guru: guru({ id: 'warren-buffett', name_ko: '워런 버핏', name_en: 'Warren Buffett', source: '13f' }),
    overlaps: [{ symbol: 'AAA', name: 'Fake A', my_weight_pct: 60, guru_weight_pct: 0.42 }],
    top_missing: [],
  },
  {
    guru: guru({ id: 'ray-dalio', name_ko: '레이 달리오', name_en: 'Ray Dalio', source: '13f' }),
    overlaps: [],
    top_missing: [],
  },
]

describe('overlap summary', () => {
  it('counts only investors with overlaps, most first, and words them in one line', () => {
    const counts = overlapCounts(gurus)
    expect(counts).toEqual([
      { id: 'cathie-wood', name: '캐시 우드(ARK)', count: 2 },
      { id: 'warren-buffett', name: '버핏', count: 1 },
    ])
    expect(overlapSentence(counts)).toBe('캐시 우드(ARK)와 겹치는 종목 2개 · 버핏 1개')
    expect(overlapSentence([])).toBe('')
    expect(overlapCounts(gurus, 1)).toHaveLength(1)
  })

  it('falls back to the Korean name for an unknown investor', () => {
    expect(shortName({ id: 'someone', name_ko: '아무개' })).toBe('아무개')
  })
})

describe('holdersOf', () => {
  it('lists who holds a symbol, largest weight first, and words it with the source', () => {
    const holders = holdersOf(gurus, 'aaa')
    expect(holders.map((h) => h.id)).toEqual(['cathie-wood', 'warren-buffett'])
    expect(holdersSentence(holders)).toBe('캐시 우드(ARK 2.1%) · 버핏(0.4%)')
    expect(holdersOf(gurus, 'ZZZ')).toEqual([])
  })
})

describe('status helpers', () => {
  it('detects the missing SEC user agent and usable snapshots', () => {
    expect(needsSecUserAgent({ error: 'AM_SEC_USER_AGENT 미설정' })).toBe(true)
    expect(needsSecUserAgent({ error: 'timeout' })).toBe(false)
    expect(needsSecUserAgent({ error: null })).toBe(false)
    expect(isLoaded(guru({}))).toBe(true)
    expect(isLoaded(guru({ synced_at: null }))).toBe(false)
    expect(isLoaded(guru({ error: 'boom' }))).toBe(false)
    expect(isLoaded(guru({ holdings_count: 0 }))).toBe(false)
  })
})
