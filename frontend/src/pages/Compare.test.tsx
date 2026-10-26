import { cleanup, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import type { CongressStatus, GuruCompareResult, Holding } from '../api/client'
import { CurrencyProvider } from '../lib/currency'
import { Compare } from './Compare'

// Fictional investors and tickers (public repo); the real list is the backend's business.
const scrolled = vi.fn<(arg?: boolean | ScrollIntoViewOptions) => void>()
const state: {
  compare: { data?: GuruCompareResult; error?: unknown }
  holdings: { data?: Holding[]; error?: unknown }
  congress: { data?: { syncing: boolean; status: CongressStatus; trades: never[] } }
  congressSymbols?: string[]
} = { compare: {}, holdings: {}, congress: {} }

vi.mock('../api/hooks', () => ({
  useGuruCompare: () => state.compare,
  useHoldings: () => state.holdings,
  usePortfolioHistory: () => ({ data: undefined }),
  useBenchmark: () => ({ data: undefined }),
  useGuruHoldings: () => ({ data: undefined }),
  useSyncGurus: () => ({ mutate: vi.fn(), isPending: false }),
  useCongressTrades: (symbols: string[]) => {
    state.congressSymbols = symbols
    return state.congress
  },
  useCongressStatus: () => ({ data: undefined }),
  useSyncCongress: () => ({ mutate: vi.fn(), isPending: false }),
}))

const guru = (id: string, name_ko: string, over: Partial<GuruCompareResult['gurus'][number]['guru']> = {}) => ({
  id,
  name_ko,
  name_en: id,
  source: '13f' as const,
  note: '',
  synced_at: null,
  as_of: null,
  stale: false,
  error: 'AM_SEC_USER_AGENT 미설정',
  sync_note: null,
  holdings_count: 0,
  ...over,
})
const item = (g: ReturnType<typeof guru>, overlaps: string[] = []) => ({
  guru: g,
  overlaps: overlaps.map((symbol) => ({ symbol, name: symbol, my_weight_pct: 10, guru_weight_pct: 1 })),
  top_missing: [],
})
const holding = (symbol: string, asset_type: Holding['asset_type']) => ({ symbol, asset_type }) as Holding
const congressStatus: CongressStatus = {
  source: 'house',
  synced_at: '2026-10-23T06:00:00',
  index_modified: '2026-10-22T13:00:38',
  stale: false,
  syncing: false,
  error: null,
  docs_total: 1,
  docs_parsed: 1,
  docs_no_text: 0,
  docs_failed: 0,
  docs_pending: 0,
  trades: 0,
  coverage_note: '하원 공시입니다. 투자 조언이 아닙니다.',
}

const renderPage = (path = '/compare') =>
  render(
    <CurrencyProvider>
      <MemoryRouter initialEntries={[path]}>
        <Compare />
      </MemoryRouter>
    </CurrencyProvider>,
  )

describe('Compare page', () => {
  beforeAll(() => {
    // jsdom has no layout, so scrollIntoView does not exist; the page calls it for `#congress`.
    Element.prototype.scrollIntoView = scrolled
  })
  afterEach(() => {
    cleanup()
    state.compare = {}
    state.holdings = {}
    state.congress = {}
    state.congressSymbols = undefined
    scrolled.mockClear()
  })

  it('folds the unsynced 13F investors into one card and keeps a card per synced investor', () => {
    state.compare = {
      data: {
        syncing: false,
        gurus: [
          item(guru('fund-a', '펀드 A (ARK)', { source: 'ark', synced_at: '2026-10-22T01:00:00Z', as_of: '2026-10-21', error: null, holdings_count: 5 }), ['AAA']),
          item(guru('inv-b', '투자자 B (운용사 B)')),
          item(guru('inv-c', '투자자 C (운용사 C)')),
          item(guru('inv-d', '투자자 D')),
        ],
      },
    }
    state.holdings = { data: [holding('AAA', 'stock')] }
    state.congress = { data: { syncing: false, status: congressStatus, trades: [] } }
    renderPage()

    // One real card for the synced investor...
    expect(screen.getByRole('heading', { level: 3, name: '펀드 A (ARK)' })).toBeInTheDocument()
    // ...and a single folded card for the three that need the SEC setting, not three empty cards.
    const folded = screen.getByRole('region', { name: '13F 투자자 3명 (동기화 안 됨)' })
    expect(within(folded).getByRole('heading', { level: 3 })).toHaveTextContent('13F 투자자 3명')
    expect(within(folded).getByText('투자자 B (운용사 B), 투자자 C (운용사 C), 투자자 D')).toBeInTheDocument()
    expect(within(folded).getByText(/AM_SEC_USER_AGENT 미설정 — backend\/\.env에 AM_SEC_USER_AGENT/)).toBeInTheDocument()
    expect(screen.queryByRole('heading', { level: 3, name: '투자자 B (운용사 B)' })).toBeNull()
    expect(screen.queryAllByText('아직 자료가 없습니다.')).toHaveLength(0)
    // The investor picker for the top-20 table also skips them.
    expect(within(screen.getByRole('group', { name: '투자자 선택' })).getAllByRole('button')).toHaveLength(1)
  })

  it('states the president/Senate limits up front and places the House card with the #congress anchor', () => {
    state.compare = { data: { syncing: false, gurus: [] } }
    state.holdings = { data: [holding('AAA', 'stock'), holding('BBB-USD', 'crypto'), holding('CCC', 'stock')] }
    state.congress = { data: { syncing: false, status: congressStatus, trades: [] } }
    renderPage()
    expect(screen.getByText(/트럼프 등 대통령·개인의 계좌는 공시되는 포트폴리오가 없어/)).toBeInTheDocument()
    expect(screen.getByText(/의원 거래는 하원 공시만 보여 줍니다/)).toBeInTheDocument()
    const anchor = document.getElementById('congress')
    expect(anchor).not.toBeNull()
    expect(within(anchor as HTMLElement).getByRole('heading', { name: '내 종목을 최근 거래한 미국 하원 의원' })).toBeInTheDocument()
    // Only stock tickers go to the House query; coins never appear in filings.
    expect(state.congressSymbols).toEqual(['AAA', 'CCC'])
    // Without the hash nothing scrolls.
    expect(scrolled).not.toHaveBeenCalled()
  })

  it('scrolls to the House card when opened at /compare#congress once holdings are known', () => {
    state.compare = { data: { syncing: false, gurus: [] } }
    state.holdings = { data: [holding('AAA', 'stock')] }
    state.congress = { data: { syncing: false, status: congressStatus, trades: [] } }
    renderPage('/compare#congress')
    expect(scrolled).toHaveBeenCalledTimes(1)
  })

  it('shows the no-13F hint only when some investor needs it', () => {
    state.compare = {
      data: {
        syncing: false,
        gurus: [item(guru('fund-a', '펀드 A (ARK)', { source: 'ark', synced_at: '2026-10-22T01:00:00Z', error: null, holdings_count: 5 }))],
      },
    }
    state.holdings = { data: [] }
    renderPage()
    expect(screen.queryByText(/AM_SEC_USER_AGENT/)).toBeNull()
    expect(screen.getByText('보유한 주식이 없어 보여 줄 거래가 없습니다.')).toBeInTheDocument()
  })
})
