import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, type TransactionInput } from './client'

export const keys = {
  summary: ['portfolio', 'summary'] as const,
  holdings: ['portfolio', 'holdings'] as const,
  portfolioHistory: (start?: string) => ['portfolio', 'history', start] as const,
  transactions: ['transactions'] as const,
  crypto: ['market', 'crypto'] as const,
  usdKrw: ['market', 'fx', 'usdkrw'] as const,
  assetInfo: (symbol: string) => ['market', symbol, 'info'] as const,
  quote: (symbol: string) => ['market', symbol, 'quote'] as const,
  history: (symbol: string, start?: string) => ['market', symbol, 'history', start] as const,
}

export const useSummary = () => useQuery({ queryKey: keys.summary, queryFn: api.summary })
export const useHoldings = () => useQuery({ queryKey: keys.holdings, queryFn: api.holdings })

// keepPreviousData: on a range change the chart keeps its frame instead of flashing empty.
export const usePortfolioHistory = (start?: string) =>
  useQuery({
    queryKey: keys.portfolioHistory(start),
    queryFn: () => api.portfolioHistory(start),
    placeholderData: keepPreviousData,
  })

export const useTransactions = () =>
  useQuery({ queryKey: keys.transactions, queryFn: api.transactions })

export const useSupportedCrypto = () =>
  useQuery({ queryKey: keys.crypto, queryFn: api.supportedCrypto, staleTime: Infinity })

export const useUsdKrw = () => useQuery({ queryKey: keys.usdKrw, queryFn: api.usdKrw })

export const useAssetInfo = (symbol: string) =>
  useQuery({ queryKey: keys.assetInfo(symbol), queryFn: () => api.assetInfo(symbol), retry: false })

export const useQuote = (symbol: string) =>
  useQuery({ queryKey: keys.quote(symbol), queryFn: () => api.quote(symbol) })

export const useHistory = (symbol: string, start?: string) =>
  useQuery({
    queryKey: keys.history(symbol, start),
    queryFn: () => api.history(symbol, start),
    placeholderData: keepPreviousData,
  })

/** Any ledger change invalidates every portfolio view derived from it. */
function useLedgerMutation<TArgs>(fn: (args: TArgs) => Promise<unknown>) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.transactions })
      void client.invalidateQueries({ queryKey: ['portfolio'] })
    },
  })
}

export const useCreateTransaction = () =>
  useLedgerMutation((data: TransactionInput) => api.createTransaction(data))

export const useUpdateTransaction = () =>
  useLedgerMutation(({ id, data }: { id: number; data: TransactionInput }) =>
    api.updateTransaction(id, data),
  )

export const useDeleteTransaction = () => useLedgerMutation((id: number) => api.deleteTransaction(id))
