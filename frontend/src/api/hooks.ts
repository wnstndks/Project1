import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'

import {
  api,
  compareApi,
  type ActionStatus,
  type Currency,
  type ImportCommit,
  type ProjectionInput,
  type RuleSettingsInput,
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
  forecastStatus: ['forecasts', 'status'] as const,
  forecast: (symbol: string) => ['forecasts', symbol] as const,
  forecastBacktest: (symbol: string, horizon: string) => ['forecasts', symbol, 'backtest', horizon] as const,
  portfolioForecast: ['portfolio', 'forecast'] as const,
  assumptions: ['portfolio', 'projection', 'assumptions'] as const,
  projection: (input: ProjectionInput) => ['portfolio', 'projection', input] as const,
}

export const useSummary = () => useQuery({ queryKey: keys.summary, queryFn: api.summary })
export const useHoldings = () => useQuery({ queryKey: keys.holdings, queryFn: api.holdings })

/** Under ['portfolio'] so that ledger changes (new holdings) refresh it. */
export const useSparklines = (days = 30) =>
  useQuery({
    queryKey: ['portfolio', 'sparklines', days] as const,
    queryFn: () => api.sparklines(days),
    staleTime: 5 * 60_000,
  })

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
      // Rule checks read the positions (average cost, steps done, weights).
      void client.invalidateQueries({ queryKey: ['rules'] })
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

export const useDeleteAllTransactions = () =>
  useLedgerMutation((scope: 'all' | 'imports') => api.deleteAllTransactions(scope))

export const useConvertCurrency = () =>
  useLedgerMutation(({ symbol, currency }: { symbol: string; currency: Currency }) =>
    api.convertCurrency(symbol, currency),
  )

export const useImportStatus = () =>
  useQuery({ queryKey: ['imports', 'status'], queryFn: api.importStatus, staleTime: 0 })

export const usePreviewScreenshots = () =>
  useMutation({ mutationFn: (files: File[]) => api.previewScreenshots(files) })

export const useCommitImport = () => useLedgerMutation((data: ImportCommit) => api.commitImport(data))

export const useForecastStatus = () =>
  useQuery({ queryKey: keys.forecastStatus, queryFn: api.forecastStatus })

export const useForecast = (symbol: string, enabled = true) =>
  useQuery({ queryKey: keys.forecast(symbol), queryFn: () => api.forecast(symbol), retry: false, enabled })

/** Under ['portfolio'] so that ledger changes (new holdings) refresh it. */
export const usePortfolioForecast = (enabled = true) =>
  useQuery({ queryKey: keys.portfolioForecast, queryFn: api.portfolioForecast, retry: false, enabled })

export const useTrackRecord = (symbol?: string) =>
  useQuery({ queryKey: ['forecasts', 'track-record', symbol], queryFn: () => api.trackRecord(symbol) })

export const useForecastBacktest = (symbol: string, horizon: string) =>
  useQuery({ queryKey: keys.forecastBacktest(symbol, horizon), queryFn: () => api.forecastBacktest(symbol, horizon) })

/** Starts the one global training job and polls every 3s while it runs. When it finishes,
 *  every forecast is refetched from the new model. */
export function useForecastTraining() {
  const client = useQueryClient()
  const status = useForecastStatus()
  const running = status.data?.job?.state === 'running'
  useQuery({
    queryKey: [...keys.forecastStatus, 'poll'],
    queryFn: async () => {
      const next = await api.forecastStatus()
      client.setQueryData(keys.forecastStatus, next)
      if (next.job?.state !== 'running') {
        void client.invalidateQueries({ queryKey: ['forecasts'] })
        void client.invalidateQueries({ queryKey: keys.portfolioForecast })
      }
      return next
    },
    enabled: running,
    refetchInterval: running ? 3000 : false,
  })
  const start = useMutation({
    mutationFn: api.startForecastTraining,
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.forecastStatus }),
  })
  return { status, running: running || start.isPending, start }
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

/** All held symbols' forecasts in one request, instead of one `useForecast` per holding.
 *  Under the `['forecasts']` prefix, so a finished training run refetches it too. */
export const useHeldForecasts = (enabled = true) =>
  useQuery({
    queryKey: ['forecasts', 'held'] as const,
    queryFn: api.forecastsHeld,
    retry: false,
    staleTime: 5 * 60_000,
    enabled,
  })

// --- rule checks (plan G): the user's own rules against their holdings, not signals ---------

/** One request for the whole holdings list, the home banner and the detail card (same key). */
export const useRuleCheck = () =>
  useQuery({ queryKey: ['rules', 'check'] as const, queryFn: api.rulesCheck, staleTime: 5 * 60_000 })

export const useRuleSettings = () =>
  useQuery({ queryKey: ['rules', 'settings'] as const, queryFn: api.rulesSettings })

/** Saving rules changes every check, so both rule queries refetch. */
export function useUpdateRuleSettings() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (data: RuleSettingsInput) => api.updateRulesSettings(data),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['rules'] }),
  })
}

// --- Well-known investors and "same money" benchmarks (Compare page) ---
const compareKeys = {
  gurus: ['gurus'] as const,
  // Under ['portfolio']: the overlap uses my weights, so ledger changes must refresh it.
  guruCompare: ['portfolio', 'gurus', 'compare'] as const,
  guruHoldings: (id: string, top: number) => ['gurus', id, 'holdings', top] as const,
  benchmark: (symbols: string[], start?: string) => ['portfolio', 'benchmark', symbols.join(','), start] as const,
}

export const useGurus = () =>
  useQuery({ queryKey: compareKeys.gurus, queryFn: compareApi.gurus, staleTime: 5 * 60_000 })

/**
 * Overlap with each investor. A first visit starts a background sync on the server and answers
 * `syncing: true`; the hook polls every 5s until it is done, then refreshes the investor lists
 * (holdings tables) that were empty meanwhile.
 */
export function useGuruCompare() {
  const client = useQueryClient()
  const result = useQuery({
    queryKey: compareKeys.guruCompare,
    queryFn: compareApi.guruCompare,
    staleTime: 5 * 60_000,
    refetchInterval: (q) => (q.state.data?.syncing ? 5000 : false),
  })
  const syncing = result.data?.syncing
  const wasSyncing = useRef(false)
  useEffect(() => {
    if (wasSyncing.current && syncing === false) void client.invalidateQueries({ queryKey: compareKeys.gurus })
    wasSyncing.current = syncing === true
  }, [syncing, client])
  return result
}

export const useGuruHoldings = (id: string | undefined, top = 20) =>
  useQuery({
    queryKey: compareKeys.guruHoldings(id ?? '', top),
    queryFn: () => compareApi.guruHoldings(id ?? '', top),
    enabled: id !== undefined,
    staleTime: 5 * 60_000,
    placeholderData: keepPreviousData,
  })

/** Asks the server to refresh every investor (202); the compare query then polls while it runs. */
export function useSyncGurus() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: compareApi.syncGurus,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: compareKeys.gurus })
      void client.invalidateQueries({ queryKey: compareKeys.guruCompare })
    },
  })
}

/** My history beside benchmarks fed with the same cash flows. Disabled with no symbols. */
export const useBenchmark = (symbols: string[], start?: string, enabled = true) =>
  useQuery({
    queryKey: compareKeys.benchmark(symbols, start),
    queryFn: () => compareApi.benchmark(symbols, start),
    enabled: enabled && symbols.length > 0,
    placeholderData: keepPreviousData,
    staleTime: 5 * 60_000,
  })
