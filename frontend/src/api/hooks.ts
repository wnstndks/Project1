import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  api,
  type ActionStatus,
  type Currency,
  type ImportCommit,
  type ProjectionInput,
  type TransactionInput,
} from './client'

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
  forecast: (symbol: string) => ['predictions', symbol] as const,
  backtest: (symbol: string) => ['predictions', symbol, 'backtest'] as const,
  training: (symbol: string) => ['predictions', symbol, 'training'] as const,
  assumptions: ['portfolio', 'projection', 'assumptions'] as const,
  projection: (input: ProjectionInput) => ['portfolio', 'projection', input] as const,
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
function useLedgerMutation<TArgs, TResult>(fn: (args: TArgs) => Promise<TResult>) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.transactions })
      void client.invalidateQueries({ queryKey: ['portfolio'] })
      // Held shares (and so which events apply, and their effect) depend on the trades.
      void client.invalidateQueries({ queryKey: ['corporate-actions'] })
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

export const useConvertCurrency = () =>
  useLedgerMutation(({ symbol, currency }: { symbol: string; currency: Currency }) =>
    api.convertCurrency(symbol, currency),
  )

export const useImportStatus = () =>
  useQuery({ queryKey: ['imports', 'status'], queryFn: api.importStatus, staleTime: 0 })

export const usePreviewScreenshots = () =>
  useMutation({ mutationFn: (files: File[]) => api.previewScreenshots(files) })

export const useCommitImport = () => useLedgerMutation((data: ImportCommit) => api.commitImport(data))

export const useForecast = (symbol: string) =>
  useQuery({ queryKey: keys.forecast(symbol), queryFn: () => api.forecast(symbol), retry: false })

export const useBacktest = (symbol: string, enabled: boolean) =>
  useQuery({ queryKey: keys.backtest(symbol), queryFn: () => api.backtest(symbol), enabled })

/** Polls every 2s while a job runs; refreshes the forecast once it finishes. */
export function useTraining(symbol: string) {
  const client = useQueryClient()
  const status = useQuery({
    queryKey: keys.training(symbol),
    queryFn: async () => {
      const job = await api.trainingStatus(symbol).catch(() => null)
      if (job?.state === 'done') {
        void client.invalidateQueries({ queryKey: keys.forecast(symbol) })
        void client.invalidateQueries({ queryKey: keys.backtest(symbol) })
      }
      return job
    },
    refetchInterval: (q) => (q.state.data?.state === 'running' ? 2000 : false),
    staleTime: 0,
  })
  const start = useMutation({
    mutationFn: () => api.startTraining(symbol),
    onSuccess: (job) => client.setQueryData(keys.training(symbol), job),
  })
  return { job: status.data, start }
}

export const useAssumptions = () =>
  useQuery({ queryKey: keys.assumptions, queryFn: api.assumptions, staleTime: 5 * 60_000 })

/** Identical inputs (fixed seed) give identical results, so they are served from cache. */
export const useProjection = (input: ProjectionInput) =>
  useQuery({
    queryKey: keys.projection(input),
    queryFn: () => api.simulate(input),
    placeholderData: keepPreviousData,
    staleTime: Infinity,
  })

// News fetches are slow the first time (GDELT throttling, FinBERT model load).
export const useNews = (symbol: string) =>
  useQuery({
    queryKey: ['news', symbol],
    queryFn: () => api.news(symbol),
    staleTime: 10 * 60_000,
    retry: false,
  })

export const useKimchi = () =>
  useQuery({ queryKey: ['market', 'kimchi'], queryFn: api.kimchi, staleTime: 5 * 60_000 })

export const useCorporateActions = () =>
  useQuery({ queryKey: ['corporate-actions'], queryFn: api.corporateActions, staleTime: 10 * 60_000 })

/** Confirming or ignoring an action changes the ledger, so every portfolio view refreshes. */
export function useSetActionStatus() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, status }: { id: number; status: ActionStatus }) =>
      api.setActionStatus(id, status),
    onSuccess: (data) => {
      client.setQueryData(['corporate-actions'], data)
      void client.invalidateQueries({ queryKey: ['portfolio'] })
    },
  })
}

export function useSetWithholding() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ symbol, rate }: { symbol: string; rate: string }) => api.setWithholding(symbol, rate),
    onSuccess: (data) => {
      client.setQueryData(['corporate-actions'], data)
      void client.invalidateQueries({ queryKey: ['portfolio'] })
    },
  })
}

export function useConfirmAllDividends() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: api.confirmAllDividends,
    onSuccess: (data) => {
      client.setQueryData(['corporate-actions'], data)
      void client.invalidateQueries({ queryKey: ['portfolio'] })
    },
  })
}
