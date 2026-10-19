import type { components } from './schema'

type Schemas = components['schemas']
export type AssetType = Schemas['AssetType']
export type Side = Schemas['Side']
export type Bar = Schemas['BarOut']
export type Quote = Schemas['QuoteOut']
export type AssetInfo = Schemas['AssetInfo']
export type Holding = Schemas['HoldingOut']
export type Summary = Schemas['SummaryOut']
export type HistoryPoint = Schemas['HistoryPointOut']
export type Transaction = Schemas['TransactionOut']
export type TransactionInput = Schemas['TransactionIn']
export type Forecast = Schemas['ForecastOut']
export type BacktestPoint = Schemas['BacktestPoint']
export type TrainingJob = Schemas['TrainingJobOut']
export type Assumptions = Schemas['AssumptionsOut']
export type ProjectionInput = Schemas['ProjectionIn']
export type Projection = Schemas['ProjectionOut']
export type ImportStatus = Schemas['ImportStatusOut']
export type News = Schemas['NewsOut']
export type ImportPreview = Schemas['PreviewOut']
export type ImportPreviewRow = Schemas['PreviewRowOut']
export type ImportCommit = Schemas['CommitIn']

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
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
  if (!res.ok) throw new ApiError(res.status, errorMessage(body, res.statusText))
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

  transactions: () => request<Transaction[]>('/transactions'),
  createTransaction: (data: TransactionInput) =>
    request<Transaction>('/transactions', { method: 'POST', body: JSON.stringify(data) }),
  updateTransaction: (id: number, data: TransactionInput) =>
    request<Transaction>(`/transactions/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteTransaction: (id: number) => request<void>(`/transactions/${id}`, { method: 'DELETE' }),

  supportedCrypto: () => request<AssetInfo[]>('/market/crypto'),
  assetInfo: (symbol: string) => request<AssetInfo>(`/market/${encodeURIComponent(symbol)}/info`),
  forecast: (symbol: string) => request<Forecast>(`/predictions/${encodeURIComponent(symbol)}`),
  backtest: (symbol: string) =>
    request<BacktestPoint[]>(`/predictions/${encodeURIComponent(symbol)}/backtest`),
  startTraining: (symbol: string) =>
    request<TrainingJob>(`/predictions/${encodeURIComponent(symbol)}/train`, { method: 'POST' }),
  trainingStatus: (symbol: string) =>
    request<TrainingJob>(`/predictions/${encodeURIComponent(symbol)}/train`),
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
  usdKrw: () => request<Quote>('/market/fx/usdkrw'),
  quote: (symbol: string) => request<Quote>(`/market/${encodeURIComponent(symbol)}/quote`),
  history: (symbol: string, start?: string, end?: string) =>
    request<Bar[]>(`/market/${encodeURIComponent(symbol)}/history${query({ start, end })}`),
}
