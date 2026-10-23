import type { Holding, Transaction } from '../api/client'
import { isSuspiciousCost, SUSPICIOUS_COST_RATIO } from './holdings'

type Trade = Pick<Transaction, 'symbol' | 'currency' | 'price'>
type Position = Pick<Holding, 'symbol' | 'quantity' | 'price' | 'price_krw'>

/** Today's price in the trade's own currency, or undefined once the symbol is no longer held. */
export function livePrice(t: Pick<Trade, 'symbol' | 'currency'>, holdings: Position[]): number | undefined {
  const h = holdings.find((x) => x.symbol === t.symbol && x.quantity > 0)
  if (!h) return undefined
  return t.currency === 'KRW' ? h.price_krw : h.price
}

/**
 * A trade price 20x away from today's price was almost surely misread from a screenshot
 * (a won amount or a total taken as the unit price). Closed positions are not checked:
 * there is no live price to compare against and nothing on the books to distort.
 */
export function needsPriceCheck(t: Trade, holdings: Position[]): boolean {
  const price = livePrice(t, holdings)
  return price !== undefined && isSuspiciousCost(t.price, price)
}

export const PRICE_CHECK_REASON = `현재가와 ${SUSPICIOUS_COST_RATIO}배 이상 차이`

/**
 * The trades to put in the "단가 확인" list above the ledger table: every flagged trade,
 * grouped by symbol and oldest first, so one position's misread buys sit together.
 */
export function priceCheckRows<T extends Trade & { trade_date: string }>(rows: T[], holdings: Position[]): T[] {
  return rows
    .filter((t) => needsPriceCheck(t, holdings))
    .sort((a, b) => a.symbol.localeCompare(b.symbol) || a.trade_date.localeCompare(b.trade_date))
}
