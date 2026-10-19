/* oxlint-disable react/only-export-components -- context provider and its hooks live together */
import { createContext, useContext, useState, type ReactNode } from 'react'

import { formatKrw, formatKrwCompact, formatUsd, formatUsdCompact } from './format'

export type Currency = 'KRW' | 'USD'

const STORAGE_KEY = 'asset-manager.currency'

function readStored(): Currency {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'USD' ? 'USD' : 'KRW'
  } catch {
    return 'KRW'
  }
}

const CurrencyContext = createContext<{ currency: Currency; setCurrency: (c: Currency) => void }>({
  currency: 'KRW',
  setCurrency: () => {},
})

export function CurrencyProvider({ children }: { children: ReactNode }) {
  const [currency, setState] = useState<Currency>(readStored)
  const setCurrency = (c: Currency) => {
    setState(c)
    try {
      localStorage.setItem(STORAGE_KEY, c)
    } catch {
      // Private mode or blocked storage: the choice just won't persist.
    }
  }
  return <CurrencyContext.Provider value={{ currency, setCurrency }}>{children}</CurrencyContext.Provider>
}

export function useCurrency() {
  return useContext(CurrencyContext)
}

/**
 * Display helpers for the selected currency. Callers pass both amounts because KRW values
 * from the API are not simply USD x today's rate: KRW cost uses each trade date's rate.
 */
export function useMoney() {
  const { currency } = useCurrency()
  const krw = currency === 'KRW'
  return {
    currency,
    pick: (usd: number, krwValue: number) => (krw ? krwValue : usd),
    format: (v: number) => (krw ? formatKrw(v) : formatUsd(v)),
    compact: (v: number) => (krw ? formatKrwCompact(v) : formatUsdCompact(v)),
    /** The other currency, for secondary lines. */
    formatOther: (usd: number, krwValue: number) => (krw ? formatUsd(usd) : formatKrw(krwValue)),
  }
}
