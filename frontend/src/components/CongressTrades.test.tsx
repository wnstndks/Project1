import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { CongressStatus, CongressTrade, CongressTrades as TradesOut } from '../api/client'
import { CongressMention, CongressTrades } from './CongressTrades'

// Fictional members and tickers only (public repo): nothing from a real filing or a real account.
const NOTE = '미국 하원 의원의 거래 공시입니다. 투자 조언이 아닙니다.'

const state: {
  trades: { data?: TradesOut; error?: unknown }
  status: { data?: CongressStatus; error?: unknown }
  tradesArgs?: { symbols: string[]; days: number }
  statusEnabled?: boolean
  mutate: ReturnType<typeof vi.fn>
} = { trades: {}, status: {}, mutate: vi.fn() }

vi.mock('../api/hooks', () => ({
  useCongressTrades: (symbols: string[], days: number) => {
    state.tradesArgs = { symbols, days }
    return state.trades
  },
  useCongressStatus: (enabled: boolean) => {
    state.statusEnabled = enabled
    return state.status
  },
  useSyncCongress: () => ({ mutate: state.mutate, isPending: false }),
}))

function status(over: Partial<CongressStatus> = {}): CongressStatus {
  return {
    source: 'house',
    synced_at: '2026-10-23T06:00:00',
    index_modified: '2026-10-22T13:00:38',
    stale: false,
    syncing: false,
    error: null,
    docs_total: 10,
    docs_parsed: 10,
    docs_no_text: 0,
    docs_failed: 0,
    docs_pending: 0,
    trades: 3,
    coverage_note: NOTE,
    ...over,
  }
}

function trade(over: Partial<CongressTrade> = {}): CongressTrade {
  return {
    symbol: 'AAA',
    asset_name: 'Fake A Inc',
    asset_type: 'ST',
    member: 'Jane Doe',
    chamber: 'house',
    state: 'MD',
    district: 'MD06',
    party: null,
    owner: 'SP',
    side: 'buy',
    transaction_date: '2026-09-30',
    notification_date: '2026-10-01',
    filing_date: '2026-10-12',
    amount_low: 1001,
    amount_high: 15000,
    amount_label: '$1,001 - $15,000',
    cap_gains_over_200: null,
    doc_id: '20000001',
    doc_url: 'https://example.test/ptr/20000001.pdf',
    ...over,
  }
}

const renderCard = (symbols: string[] | undefined, days = 180) =>
  render(
    <MemoryRouter>
      <CongressTrades symbols={symbols} days={days} />
    </MemoryRouter>,
  )

describe('CongressTrades', () => {
  afterEach(() => {
    cleanup()
    state.trades = {}
    state.status = {}
    state.tradesArgs = undefined
    state.statusEnabled = undefined
    state.mutate = vi.fn()
  })

  it('shows a skeleton and says the filings are being fetched during a first sync', () => {
    state.trades = { data: { syncing: true, status: status({ synced_at: null, docs_parsed: 0 }), trades: [] } }
    renderCard(['AAA', 'BBB'])
    expect(state.tradesArgs).toEqual({ symbols: ['AAA', 'BBB'], days: 180 })
    // The trades response already carries the status, so the separate status query stays off.
    expect(state.statusEnabled).toBe(false)
    expect(screen.getByRole('status')).toHaveTextContent('공시 문서를 받는 중입니다')
    expect(document.querySelector('.animate-pulse')).not.toBeNull()
    expect(screen.queryByText(/공시가 없습니다/)).toBeNull()
  })

  it('says there is nothing in the window once the sync is done with no trades', () => {
    state.trades = { data: { syncing: false, status: status(), trades: [] } }
    renderCard(['AAA'], 90)
    expect(screen.getByText('최근 90일 안에 내 종목을 거래한 하원 의원 공시가 없습니다.')).toBeInTheDocument()
    expect(screen.queryByRole('status')).toBeNull()
    expect(document.querySelector('.animate-pulse')).toBeNull()
  })

  it('groups trades per ticker, shows three, folds the rest, and links the filing in a new tab', () => {
    const trades = [
      trade({ member: 'Jane Doe', transaction_date: '2026-09-30', filing_date: '2026-10-12' }),
      trade({ member: 'John Roe', owner: 'SELF', side: 'sell_partial', transaction_date: '2026-09-28', doc_id: '2' }),
      trade({ member: 'Ann Poe', owner: 'JT', side: 'sell', transaction_date: '2026-09-20', amount_low: 50_000_000, amount_high: null, doc_id: '3' }),
      trade({ member: 'Jane Doe', side: 'exchange', transaction_date: '2026-09-10', doc_id: '4' }),
      trade({ symbol: 'BBB', asset_name: 'Fake B', member: 'John Roe', transaction_date: '2026-10-01', doc_id: '5' }),
    ]
    state.trades = { data: { syncing: false, status: status(), trades } }
    renderCard(['AAA', 'BBB'])

    // Coverage note as sent, and the index date on the facts line.
    expect(screen.getByText(NOTE)).toBeInTheDocument()
    expect(screen.getByText(/색인 갱신 10\.22/)).toBeInTheDocument()

    // BBB was traded most recently, so it comes first.
    const sections = screen.getAllByRole('region')
    expect(sections.map((s) => s.getAttribute('aria-label'))).toEqual(['BBB 하원 의원 거래', 'AAA 하원 의원 거래'])

    const aaa = within(sections[1])
    expect(aaa.getByRole('link', { name: 'AAA' })).toHaveAttribute('href', '/assets/AAA')
    expect(aaa.getByText('· 의원 3명 · 4건')).toBeInTheDocument()
    // Three newest shown; the fourth sits behind "더 보기".
    expect(aaa.getAllByRole('listitem')).toHaveLength(4)
    expect(aaa.getByText('더 보기 (1건)')).toBeInTheDocument()
    // Jane Doe appears twice: a buy in the visible three and the exchange inside the fold.
    expect(aaa.getAllByText('Jane Doe (MD06) · 배우자 계좌')).toHaveLength(2)
    expect(aaa.getByText('John Roe (MD06) · 본인 계좌')).toBeInTheDocument()
    expect(aaa.getByText('일부 매도')).toBeInTheDocument()
    expect(aaa.getByText('$50,000,000 이상')).toBeInTheDocument()
    expect(aaa.getByText('교환')).toBeInTheDocument()
    expect(aaa.getByText('거래 9.30 · 공시 10.12')).toBeInTheDocument()

    // Side badges are neutral: no gain/loss colour, no arrows.
    const badges = [...screen.getAllByText('매수'), ...screen.getAllByText('매도'), ...screen.getAllByText('일부 매도')]
    for (const b of badges) {
      expect(b.className).not.toMatch(/text-gain|text-loss/)
      expect(b.textContent).not.toMatch(/[▲▼]/)
    }

    // The filing opens on the Clerk's site in a new tab.
    const [doc] = aaa.getAllByRole('link', { name: 'Jane Doe 공시 원문 (새 탭)' })
    expect(doc).toHaveAttribute('href', 'https://example.test/ptr/20000001.pdf')
    expect(doc).toHaveAttribute('target', '_blank')
    expect(doc).toHaveAttribute('rel', 'noopener noreferrer')

    // No "지금 받기" without a backlog, and no signal/recommendation wording anywhere.
    expect(screen.queryByRole('button', { name: '지금 받기' })).toBeNull()
    expect(document.body.textContent).not.toMatch(/신호|추천/)
  })

  it('explains unreadable scans and the backlog, and lets me ask for the next batch', () => {
    state.trades = {
      data: {
        syncing: false,
        status: status({ docs_no_text: 9, docs_pending: 469, stale: true, error: 'HTTP 503' }),
        trades: [trade()],
      },
    }
    renderCard(['AAA'])
    expect(screen.getByText('9건은 스캔 문서라 읽지 못했습니다 · 469건 더 받는 중', { exact: false })).toBeInTheDocument()
    expect(screen.getByText(/최근 공시가 빠져 있을 수 있습니다/)).toBeInTheDocument()
    expect(screen.getByText('최근 갱신 실패: HTTP 503')).toBeInTheDocument()
    const button = screen.getByRole('button', { name: '지금 받기' })
    expect(button).toBeEnabled()
    fireEvent.click(button)
    expect(state.mutate).toHaveBeenCalledTimes(1)
  })

  it('disables the fetch button while a sync runs and says more is coming under the list', () => {
    state.trades = { data: { syncing: true, status: status({ docs_pending: 60 }), trades: [trade()] } }
    renderCard(['AAA'])
    expect(screen.getByRole('button', { name: '지금 받기' })).toBeDisabled()
    expect(screen.getByRole('status')).toHaveTextContent('공시 문서를 더 받는 중입니다')
    expect(screen.getByText('Jane Doe (MD06) · 배우자 계좌')).toBeInTheDocument()
  })

  it('keeps the caveats from the status query when I hold no stocks, and skeletons while holdings load', () => {
    state.status = { data: status({ docs_pending: 5 }) }
    renderCard([])
    expect(state.statusEnabled).toBe(true)
    expect(screen.getByText(NOTE)).toBeInTheDocument()
    expect(screen.getByText('보유한 주식이 없어 보여 줄 거래가 없습니다.')).toBeInTheDocument()
    cleanup()
    renderCard(undefined)
    expect(document.querySelector('.animate-pulse')).not.toBeNull()
    expect(screen.queryByText(/보여 줄 거래가 없습니다/)).toBeNull()
  })

  it('shows the error when the trades request fails', () => {
    state.trades = { error: new Error('서버 오류') }
    renderCard(['AAA'])
    expect(screen.getByRole('alert')).toHaveTextContent('서버 오류')
  })
})

describe('CongressMention', () => {
  afterEach(() => {
    cleanup()
    state.trades = {}
    state.tradesArgs = undefined
  })

  const renderLine = (symbol: string) =>
    render(
      <MemoryRouter>
        <CongressMention symbol={symbol} />
      </MemoryRouter>,
    )

  it('counts distinct members for this symbol and links to the compare card', () => {
    state.trades = {
      data: {
        syncing: false,
        status: status(),
        trades: [trade({ member: 'Jane Doe' }), trade({ member: 'Jane Doe', doc_id: '2' }), trade({ member: 'John Roe', doc_id: '3' })],
      },
    }
    renderLine('AAA')
    expect(state.tradesArgs).toEqual({ symbols: ['AAA'], days: 180 })
    expect(screen.getByRole('link', { name: '최근 180일 이 종목을 거래한 하원 의원 2명' })).toHaveAttribute(
      'href',
      '/compare#congress',
    )
  })

  it('renders nothing while loading, with no trades, or without a symbol', () => {
    state.trades = {}
    const { container } = renderLine('AAA')
    expect(container).toBeEmptyDOMElement()
    cleanup()
    state.trades = { data: { syncing: false, status: status(), trades: [] } }
    expect(renderLine('AAA').container).toBeEmptyDOMElement()
    cleanup()
    state.trades = { data: { syncing: false, status: status(), trades: [trade()] } }
    expect(renderLine('').container).toBeEmptyDOMElement()
    expect(state.tradesArgs?.symbols).toEqual([])
  })
})
