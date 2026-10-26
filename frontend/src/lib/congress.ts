/**
 * Pure helpers for the US House trade-disclosure screens (Compare card, asset-detail line).
 * The backend filters and dates the trades; this file only words, groups and counts them.
 * Nothing here is a signal: these are public filings shown as they are.
 */
import type { CongressTrade } from '../api/client'

const SIDE_KO: Record<string, string> = {
  buy: '매수',
  sell: '매도',
  sell_partial: '일부 매도',
  exchange: '교환',
}

/** Clerk owner codes: SELF, SP (spouse), DC (dependent child), JT (joint). */
const OWNER_KO: Record<string, string> = {
  SELF: '본인',
  SP: '배우자',
  DC: '자녀',
  JT: '공동',
}

/** "매수" / "매도" / "일부 매도" / "교환"; an unknown code is shown as-is rather than hidden. */
export const sideLabel = (side: string): string => SIDE_KO[side] ?? side

export const ownerLabel = (owner: string): string => OWNER_KO[owner.toUpperCase()] ?? owner

const usd = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })

/** "$1,001~$15,000", or "$50,000,000 이상" when the filing only says "Over $X". */
export function amountRange(low: number, high: number | null): string {
  if (high === null) return `$${usd.format(low)} 이상`
  return `$${usd.format(low)}~$${usd.format(high)}`
}

/** "Jane Doe (MD06) · 배우자 계좌". The district already carries the state; fall back to it. */
export function memberLine(trade: Pick<CongressTrade, 'member' | 'district' | 'state' | 'owner'>): string {
  const where = trade.district || trade.state
  const place = where ? ` (${where})` : ''
  return `${trade.member}${place} · ${ownerLabel(trade.owner)} 계좌`
}

/** Most recent trade first; same trade date → the later filing first. Does not mutate. */
export function sortRecent(trades: CongressTrade[]): CongressTrade[] {
  return [...trades].sort(
    (a, b) =>
      b.transaction_date.localeCompare(a.transaction_date) || b.filing_date.localeCompare(a.filing_date),
  )
}

export type SymbolGroup = { symbol: string; name: string; trades: CongressTrade[] }

/**
 * One group per ticker, groups ordered by their most recent trade, trades inside most recent first.
 * A trade without a ticker (should not happen for a symbol query) is grouped under its asset name.
 */
export function groupBySymbol(trades: CongressTrade[]): SymbolGroup[] {
  const groups = new Map<string, SymbolGroup>()
  for (const t of sortRecent(trades)) {
    const key = (t.symbol ?? t.asset_name).toUpperCase()
    const group = groups.get(key)
    if (group) group.trades.push(t)
    else groups.set(key, { symbol: t.symbol ?? t.asset_name, name: t.asset_name, trades: [t] })
  }
  // Map keeps insertion order and the input is sorted, so the first-seen group is the most recent.
  return Array.from(groups.values())
}

/** How many different members appear (one member with several trades counts once). */
export const distinctMembers = (trades: Pick<CongressTrade, 'member'>[]): number =>
  new Set(trades.map((t) => t.member)).size
