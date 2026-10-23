import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Benchmark, GuruCompareResult, HistoryPoint } from '../api/client'
import { CurrencyProvider } from '../lib/currency'
import { daysAgo } from '../lib/format'
import { CompareCard } from './CompareCard'

const state: {
  compare: { data?: GuruCompareResult; error?: unknown }
  history: { data?: HistoryPoint[] }
  benchmark: { data?: Benchmark }
  benchmarkEnabled?: boolean
} = { compare: {}, history: {}, benchmark: {} }

vi.mock('../api/hooks', () => ({
  useGuruCompare: () => state.compare,
  usePortfolioHistory: () => state.history,
  useBenchmark: (_symbols: string[], _start: string | undefined, enabled: boolean) => {
    state.benchmarkEnabled = enabled
    return state.benchmark
  },
}))

const guru = (id: string, name_ko: string, over: Partial<GuruCompareResult['gurus'][number]['guru']> = {}) => ({
  id,
  name_ko,
  name_en: id,
  source: 'ark' as const,
  note: '',
  synced_at: '2026-10-22T01:00:00Z',
  as_of: '2026-10-21',
  stale: false,
  error: null,
  sync_note: null,
  holdings_count: 10,
  ...over,
})
const overlap = (symbol: string) => ({ symbol, name: symbol, my_weight_pct: 10, guru_weight_pct: 1 })
const point = (date: string, usd: number, krw: number): HistoryPoint => ({
  date,
  market_value: usd,
  market_value_krw: krw,
  cost_basis: usd,
  cost_basis_krw: krw,
})

function renderCard(currency: 'KRW' | 'USD' = 'KRW') {
  localStorage.setItem('asset-manager.currency', currency)
  return render(
    <CurrencyProvider>
      <MemoryRouter>
        <CompareCard />
      </MemoryRouter>
    </CurrencyProvider>,
  )
}

describe('CompareCard', () => {
  afterEach(() => {
    cleanup()
    localStorage.clear()
    state.compare = {}
    state.history = {}
    state.benchmark = {}
  })

  it('counts overlaps per investor and links to the compare page', () => {
    state.compare = {
      data: {
        syncing: false,
        gurus: [
          { guru: guru('cathie-wood', '캐시 우드'), overlaps: [overlap('AAA'), overlap('BBB')], top_missing: [] },
          { guru: guru('warren-buffett', '워런 버핏', { source: '13f' }), overlaps: [overlap('AAA')], top_missing: [] },
          { guru: guru('ray-dalio', '레이 달리오', { source: '13f' }), overlaps: [], top_missing: [] },
        ],
      },
    }
    state.history = { data: [point(daysAgo(1), 1, 1)] }
    renderCard()
    expect(screen.getByText('캐시 우드(ARK)와 겹치는 종목 2개 · 버핏 1개')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '자세히 →' })).toHaveAttribute('href', '/compare')
    // Under a week of history the benchmark line is neither fetched nor shown.
    expect(state.benchmarkEnabled).toBe(false)
    expect(screen.queryByText(/같은 돈을/)).toBeNull()
  })

  it('shows the SPY line from the backend values once there is a week of history', () => {
    state.compare = { data: { syncing: false, gurus: [] } }
    state.history = { data: [point(daysAgo(10), 1000, 1_400_000)] }
    state.benchmark = {
      data: {
        mine: [point(daysAgo(1), 1100, 1_540_000)],
        benchmarks: [{ symbol: 'SPY', name_ko: 'S&P 500 ETF', points: [{ date: daysAgo(1), value: 1050, value_krw: 1_470_000 }] }],
      },
    }
    renderCard()
    expect(state.benchmarkEnabled).toBe(true)
    expect(screen.getByText(/같은 돈을 SPY에 넣었다면 지금 약 1,470,000원/)).toHaveTextContent('(내 자산 1,540,000원)')
    // No investor loaded at all: not "no overlap", but "no data yet".
    expect(screen.getByText('아직 투자자 자료가 없습니다.')).toBeInTheDocument()
  })

  it('distinguishes "nobody holds mine" from "no data"', () => {
    state.compare = {
      data: { syncing: false, gurus: [{ guru: guru('cathie-wood', '캐시 우드'), overlaps: [], top_missing: [] }] },
    }
    state.history = { data: [] }
    renderCard()
    expect(screen.getByText('내 보유 종목을 들고 있는 유명 투자자가 없습니다.')).toBeInTheDocument()
  })

  it('says it is loading during a first sync and points to the SEC setting when 13F is off', () => {
    state.compare = {
      data: {
        syncing: true,
        gurus: [
          { guru: guru('cathie-wood', '캐시 우드', { synced_at: null, holdings_count: 0 }), overlaps: [], top_missing: [] },
          {
            guru: guru('warren-buffett', '워런 버핏', { source: '13f', synced_at: null, error: 'AM_SEC_USER_AGENT 미설정', holdings_count: 0 }),
            overlaps: [],
            top_missing: [],
          },
        ],
      },
    }
    renderCard('USD')
    expect(screen.getByText('불러오는 중…')).toBeInTheDocument()
    expect(screen.getByText(/AM_SEC_USER_AGENT/)).toBeInTheDocument()
  })
})
