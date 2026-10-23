/**
 * Pure helpers for the well-known-investor screens (Compare page, CompareCard, GuruHolders).
 * The backend does the overlap join; this file only words and filters its result.
 */
import type { Guru, GuruCompare } from '../api/client'

/** Short names for one-line summaries ("버핏 3개"); ARK is named as a fund, not a person. */
const SHORT_NAME: Record<string, string> = {
  'cathie-wood': '캐시 우드(ARK)',
  'warren-buffett': '버핏',
  'michael-burry': '버리',
  'bill-ackman': '애크먼',
  'stanley-druckenmiller': '드러켄밀러',
  'ray-dalio': '달리오',
  'david-tepper': '테퍼',
}

export const shortName = (g: Pick<Guru, 'id' | 'name_ko'>) => SHORT_NAME[g.id] ?? g.name_ko

export const sourceLabel = (source: Guru['source']) =>
  source === 'ark' ? 'ARK 일일 공개' : 'SEC 13F 분기 보고'

/** The backend's marker for 13F investors it cannot fetch without a SEC User-Agent. */
export const needsSecUserAgent = (g: Pick<Guru, 'error'>) => g.error?.includes('AM_SEC_USER_AGENT') === true

/** Investors whose snapshot is usable: loaded without an error (stale data still counts). */
export const isLoaded = (g: Pick<Guru, 'synced_at' | 'error' | 'holdings_count'>) =>
  g.synced_at !== null && g.error === null && g.holdings_count > 0

export type OverlapCount = { id: string; name: string; count: number }

/** Investors who hold at least one of my tickers, most overlaps first, at most `limit`. */
export function overlapCounts(gurus: GuruCompare[], limit = 3): OverlapCount[] {
  return gurus
    .filter((g) => g.overlaps.length > 0)
    .map((g) => ({ id: g.guru.id, name: shortName(g.guru), count: g.overlaps.length }))
    .sort((a, b) => b.count - a.count)
    .slice(0, limit)
}

/** "캐시 우드(ARK)와 겹치는 종목 2개 · 버핏 1개" */
export function overlapSentence(counts: OverlapCount[]): string {
  if (counts.length === 0) return ''
  const [first, ...rest] = counts
  return [`${first.name}와 겹치는 종목 ${first.count}개`, ...rest.map((c) => `${c.name} ${c.count}개`)].join(' · ')
}

export type Holder = { id: string; name: string; weightPct: number; source: Guru['source'] }

/** Investors holding `symbol`, their weight in it, largest first. Compare rows are my holdings only. */
export function holdersOf(gurus: GuruCompare[], symbol: string): Holder[] {
  const key = symbol.toUpperCase()
  const out: Holder[] = []
  for (const g of gurus) {
    const row = g.overlaps.find((o) => o.symbol.toUpperCase() === key)
    if (row) out.push({ id: g.guru.id, name: shortName(g.guru), weightPct: row.guru_weight_pct, source: g.guru.source })
  }
  return out.sort((a, b) => b.weightPct - a.weightPct)
}

/** "캐시 우드(ARK 2.1%) · 버핏(0.4%)" */
export function holdersSentence(holders: Holder[]): string {
  return holders
    .map((h) => `${h.name.replace(/\(ARK\)$/, '')}(${h.source === 'ark' ? 'ARK ' : ''}${h.weightPct.toFixed(1)}%)`)
    .join(' · ')
}

/** Percent for the overlap bars: one decimal, no sign. */
export const pct = (v: number) => `${v.toFixed(1)}%`
