import type { components } from './schema'

type Schemas = components['schemas']
export type AssetType = Schemas['AssetType']
export type Side = Schemas['Side']
export type Currency = Schemas['Currency']
export type KimchiPremium = Schemas['KimchiPremiumOut']
export type CorporateAction = Schemas['CorporateActionOut']
export type ActionStatus = Schemas['ActionStatus']
export type Bar = Schemas['BarOut']
export type Quote = Schemas['QuoteOut']
export type AssetInfo = Schemas['AssetInfo']
export type Holding = Schemas['HoldingOut']
export type Summary = Schemas['SummaryOut']
export type HistoryPoint = Schemas['HistoryPointOut']
export type Sparkline = Schemas['SparklineOut']
export type Transaction = Schemas['TransactionOut']
export type TransactionInput = Schemas['TransactionIn']
export type SymbolForecast = Schemas['SymbolForecastOut']
export type HorizonForecast = Schemas['HorizonForecastOut']
export type PortfolioForecast = Schemas['PortfolioForecastOut']
export type ForecastStatus = Schemas['ForecastStatusOut']
export type ForecastJob = Schemas['ForecastJobOut']
export type ForecastBacktestPoint = Schemas['ForecastBacktestPoint']
export type TrackRecord = Schemas['TrackRecordOut']
export type Assumptions = Schemas['AssumptionsOut']
export type ProjectionInput = Schemas['ProjectionIn']
export type Projection = Schemas['ProjectionOut']
export type ImportStatus = Schemas['ImportStatusOut']
export type News = Schemas['NewsOut']
export type ImportPreview = Schemas['PreviewOut']
export type ImportPreviewRow = Schemas['PreviewRowOut']
export type ImportCommit = Schemas['CommitIn']
// Rule checks (plan G): the user's own buy-more / stop-loss rules, not trading signals.
export type RuleCheckAll = Schemas['RuleCheckAllOut']
export type RuleCheck = Schemas['RuleCheckOut']
export type RuleTrigger = Schemas['RuleTriggerOut']
export type RuleSettings = Schemas['RuleSettingsOut']
export type RuleSettingsInput = Schemas['RuleSettingsIn']

export class ApiError extends Error {
  readonly status: number
  /** Machine-readable reason from the backend (e.g. 'not_trained'), when it sends one. */
  readonly code?: string

  constructor(status: number, message: string, code?: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

/** FastAPI returns `detail` as a string for domain errors and as a list for validation errors. */
function errorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return detail
        .map((d: { loc?: unknown[]; msg?: string }) => `${d.loc?.slice(1).join('.') ?? ''}: ${d.msg}`)
        .join(', ')
    }
  }
  return fallback
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // FormData bodies must let the browser set the multipart boundary header itself.
  const json = !(init?.body instanceof FormData)
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { ...(json && { 'Content-Type': 'application/json' }), ...init?.headers },
  })
  if (res.status === 204) return undefined as T
  const body = await res.json().catch(() => null)
  if (!res.ok) {
    const code = body && typeof body === 'object' && 'code' in body ? String(body.code) : undefined
    throw new ApiError(res.status, errorMessage(body, res.statusText), code)
  }
  return body as T
}

function query(params: Record<string, string | undefined>): string {
  const entries = Object.entries(params).filter((e): e is [string, string] => e[1] !== undefined)
  return entries.length ? `?${new URLSearchParams(entries)}` : ''
}

export const api = {
  summary: () => request<Summary>('/portfolio/summary'),
  holdings: () => request<Holding[]>('/portfolio/holdings'),
  portfolioHistory: (start?: string) => request<HistoryPoint[]>(`/portfolio/history${query({ start })}`),
  sparklines: (days = 30) => request<Sparkline[]>(`/portfolio/sparklines?days=${days}`),

  transactions: () => request<Transaction[]>('/transactions'),
  createTransaction: (data: TransactionInput) =>
    request<Transaction>('/transactions', { method: 'POST', body: JSON.stringify(data) }),
  updateTransaction: (id: number, data: TransactionInput) =>
    request<Transaction>(`/transactions/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  convertCurrency: (symbol: string, currency: Currency) =>
    request<Transaction[]>('/transactions/convert-currency', {
      method: 'POST',
      body: JSON.stringify({ symbol, currency }),
    }),
  deleteTransaction: (id: number) => request<void>(`/transactions/${id}`, { method: 'DELETE' }),
  deleteAllTransactions: (scope: 'all' | 'imports') =>
    request<{ deleted: number }>(`/transactions${query({ confirm: scope })}`, { method: 'DELETE' }),

  supportedCrypto: () => request<AssetInfo[]>('/market/crypto'),
  assetInfo: (symbol: string) => request<AssetInfo>(`/market/${encodeURIComponent(symbol)}/info`),
  forecastStatus: () => request<ForecastStatus>('/forecasts/status'),
  startForecastTraining: () => request<ForecastJob>('/forecasts/train', { method: 'POST' }),
  forecast: (symbol: string) => request<SymbolForecast>(`/forecasts/${encodeURIComponent(symbol)}`),
  trackRecord: (symbol?: string) => request<TrackRecord>(`/forecasts/track-record${query({ symbol })}`),
  portfolioForecast: () => request<PortfolioForecast>('/forecasts/portfolio'),
  forecastBacktest: (symbol: string, horizon: string) =>
    request<ForecastBacktestPoint[]>(
      `/forecasts/${encodeURIComponent(symbol)}/backtest${query({ horizon })}`,
    ),
  assumptions: () => request<Assumptions>('/projection/assumptions'),
  simulate: (input: ProjectionInput) =>
    request<Projection>('/projection/simulate', { method: 'POST', body: JSON.stringify(input) }),
  importStatus: () => request<ImportStatus>('/imports/status'),
  previewScreenshots: (files: File[]) => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    return request<ImportPreview>('/imports/screenshot', { method: 'POST', body: form })
  },
  commitImport: (data: ImportCommit) =>
    request<{ created: number }>('/imports/commit', { method: 'POST', body: JSON.stringify(data) }),
  news: (symbol: string) => request<News>(`/news/${encodeURIComponent(symbol)}`),
  corporateActions: () => request<CorporateAction[]>('/corporate-actions'),
  setActionStatus: (id: number, status: ActionStatus) =>
    request<CorporateAction[]>(
      `/corporate-actions/${id}/${status === 'confirmed' ? 'confirm' : 'ignore'}`,
      { method: 'POST' },
    ),
  setWithholding: (symbol: string, rate: string) =>
    request<CorporateAction[]>('/corporate-actions/withholding', {
      method: 'POST',
      body: JSON.stringify({ symbol, rate }),
    }),
  confirmAllDividends: () =>
    request<CorporateAction[]>('/corporate-actions/dividends/confirm-all', { method: 'POST' }),
  kimchi: () => request<KimchiPremium[]>('/market/kimchi'),
  usdKrw: () => request<Quote>('/market/fx/usdkrw'),
  quote: (symbol: string) => request<Quote>(`/market/${encodeURIComponent(symbol)}/quote`),
  history: (symbol: string, start?: string, end?: string) =>
    request<Bar[]>(`/market/${encodeURIComponent(symbol)}/history${query({ start, end })}`),

  // Rule checks and settings. Percentages go as strings so the backend parses exact decimals.
  rulesCheck: () => request<RuleCheckAll>('/rules/check'),
  rulesSettings: () => request<RuleSettings>('/rules/settings'),
  updateRulesSettings: (data: RuleSettingsInput) =>
    request<RuleSettings>('/rules/settings', { method: 'PUT', body: JSON.stringify(data) }),

  /** Every held symbol's forecast in one request (ratios to the latest close). */
  forecastsHeld: () => request<HeldForecast[]>('/forecasts/held'),
}

// --- Well-known investors and "same money" benchmarks (Compare page) ---
export type Guru = Schemas['GuruOut']
export type GuruHolding = Schemas['GuruHoldingOut']
export type GuruHoldings = Schemas['GuruHoldingsOut']
export type GuruCompare = Schemas['GuruCompareOut']
export type GuruCompareResult = Schemas['CompareOut']
export type GuruSync = Schemas['SyncOut']
export type Overlap = Schemas['OverlapOut']
export type MissingHolding = Schemas['MissingOut']
export type Benchmark = Schemas['BenchmarkOut']
export type BenchmarkSeries = Schemas['BenchmarkSeriesOut']
export type BenchmarkPoint = Schemas['BenchmarkPointOut']

/** Kept apart from `api` so parallel edits to that object never collide; same `request` underneath. */
export const compareApi = {
  gurus: () => request<Guru[]>('/gurus'),
  guruCompare: () => request<GuruCompareResult>('/gurus/compare'),
  guruHoldings: (id: string, top = 20) =>
    request<GuruHoldings>(`/gurus/${encodeURIComponent(id)}/holdings?top=${top}`),
  syncGurus: () => request<GuruSync>('/gurus/sync', { method: 'POST' }),
  benchmark: (symbols: string[], start?: string) =>
    request<Benchmark>(`/portfolio/benchmark${query({ symbols: symbols.join(',') || undefined, start })}`),
}

// --- US House members' STOCK Act trade disclosures (Compare page, asset detail) ---
export type CongressTrade = Schemas['CongressTradeOut']
export type CongressTrades = Schemas['CongressTradesOut']
export type CongressStatus = Schemas['CongressStatusOut']
export type CongressSync = Schemas['CongressSyncOut']

/** Own object like `compareApi`, so edits here never collide with `api`. */
export const congressApi = {
  trades: (symbols: string[], days = 180) =>
    request<CongressTrades>(
      `/congress/trades${query({ symbols: symbols.join(',') || undefined, days: String(days) })}`,
    ),
  status: () => request<CongressStatus>('/congress/status'),
  sync: () => request<CongressSync>('/congress/sync', { method: 'POST' }),
}

// --- Forecasts: all held symbols at once (`api.forecastsHeld`) and the live verdict ---
export type HeldForecast = Schemas['HeldForecastOut']
export type HeldHorizonForecast = Schemas['HeldHorizonOut']
/** `ForecastStatus.live[assetClass][horizon]`: reasons, not the report's raw edge flags. */
export type LiveVerdict = Schemas['LiveVerdictOut']
