import { cleanup, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { HeldFundamentals } from '../api/client'
import { ApiError } from '../api/client'
import { FUNDAMENTALS_BANNED_RE } from '../lib/fundamentals'
import { AAA, BANK, DISCLAIMER_KO, ETF, FAILED, LOSS, NON_OPERATING, OP_LOSS } from '../lib/fundamentals.fixtures'
import { FundamentalsSummary } from './FundamentalsSummary'

const held: HeldFundamentals = {
  items: [AAA, LOSS, ETF],
  as_of: '2026-11-11',
  source_ko: 'Yahoo Finance',
  disclaimer_ko: DISCLAIMER_KO,
}

type Q = { data?: HeldFundamentals; error?: unknown; isLoading?: boolean }
const state: { query: Q } = { query: {} }

vi.mock('../api/hooks', () => ({
  useHeldFundamentals: () => state.query,
}))

const renderSummary = () =>
  render(
    <MemoryRouter>
      <FundamentalsSummary />
    </MemoryRouter>,
  )

describe('FundamentalsSummary (home)', () => {
  beforeEach(() => {
    state.query = { data: held }
  })
  afterEach(cleanup)

  it('renders nothing while loading, on an error and when no stock is held', () => {
    state.query = { isLoading: true }
    expect(renderSummary().container).toBeEmptyDOMElement()
    cleanup()
    state.query = { error: new ApiError(502, '시세 공급자 오류') }
    expect(renderSummary().container).toBeEmptyDOMElement()
    cleanup()
    // A failed refetch keeps the old data in the query: still hidden.
    state.query = { data: held, error: new Error('네트워크') }
    expect(renderSummary().container).toBeEmptyDOMElement()
    cleanup()
    state.query = { data: { ...held, items: [], as_of: null } }
    expect(renderSummary().container).toBeEmptyDOMElement()
  })

  it('is folded by default, one linked row per stock with four figures', () => {
    const { container } = renderSummary()
    const details = container.querySelector('details') as HTMLElement
    expect(details).not.toHaveAttribute('open')
    expect(within(details).getByText('보유 주식 재무 한눈에')).toBeInTheDocument()

    const rows = within(screen.getByRole('list', { name: '보유 주식 재무 한눈에' })).getAllByRole('listitem')
    expect(rows).toHaveLength(2) // the ETF is not a row
    const first = within(rows[0])
    expect(first.getByRole('link')).toHaveAttribute('href', '/assets/AAA')
    expect(first.getByText('AAA')).toBeInTheDocument()
    expect(first.getByText('AAA Inc.')).toBeInTheDocument()
    expect(first.getAllByRole('term').map((t) => t.textContent)).toEqual(['PER', 'PBR', '영업이익률', '매출 성장률'])
    expect(first.getAllByRole('definition').map((d) => d.textContent)).toEqual(['28.4배', '45.1배', '31.2%', '+6.1%'])

    const second = within(rows[1])
    expect(second.getByRole('link')).toHaveAttribute('href', '/assets/BBB')
    expect(second.getAllByRole('definition').map((d) => d.textContent)).toEqual(['– (적자)', '45.1배', '−18.3%', '−7.3%'])
  })

  it('names held ETFs in a footnote and closes with the source, the date and the disclaimer', () => {
    renderSummary()
    expect(screen.getByText('재무제표가 없는 자산 (ETF 등): SPY')).toBeInTheDocument()
    expect(screen.getByText(`Yahoo Finance · 2026-11-11 기준. ${DISCLAIMER_KO}`)).toBeInTheDocument()
  })

  it('says a stock could not be fetched instead of a row of dashes, and flags kept figures', () => {
    state.query = { data: { ...held, items: [{ ...AAA, stale: true, error: 'x' }, FAILED] } }
    renderSummary()
    const rows = screen.getAllByRole('listitem')
    expect(within(rows[1]).getByText('지금은 재무 숫자를 받지 못했어요.')).toBeInTheDocument()
    expect(within(rows[1]).queryByRole('term')).not.toBeInTheDocument()
    expect(screen.getByText(/Yahoo Finance · 2026-11-11 기준 · 일부는 마지막으로 받은 값\./)).toBeInTheDocument()
  })

  it('marks a PER that sits beside an operating loss with a word, not a colour', () => {
    state.query = { data: { ...held, items: [OP_LOSS] } }
    const { container } = renderSummary()
    const row = within(screen.getByRole('listitem'))
    expect(row.getByRole('link')).toHaveAttribute('href', '/assets/EEE')
    expect(row.getAllByRole('definition').map((d) => d.textContent)).toEqual(['20.1배 (영업적자)', '45.1배', '−35.2%', '+6.1%'])
    expect(container.querySelector('[class*="text-gain"], [class*="text-loss"], [class*="text-danger"]')).toBeNull()
  })

  it('says in a word why a bank has no operating margin, so the dash is not read as a failure', () => {
    state.query = { data: { ...held, items: [BANK] } }
    renderSummary()
    const row = within(screen.getByRole('listitem'))
    expect(row.getAllByRole('definition').map((d) => d.textContent)).toEqual(['28.4배', '45.1배', '– (항목 없음)', '+6.1%'])
    expect(row.queryByText('지금은 재무 숫자를 받지 못했어요.')).not.toBeInTheDocument()
  })

  it('leaves the home row unmarked when net income is above operating income (the asset page says it)', () => {
    state.query = { data: { ...held, items: [NON_OPERATING] } }
    const { container } = renderSummary()
    const row = within(screen.getByRole('listitem'))
    expect(row.getAllByRole('definition').map((d) => d.textContent)).toEqual(['28.4배', '45.1배', '31.2%', '+6.1%'])
    expect(container.textContent).not.toContain('순이익')
  })

  it('shows only the footnote when every held stock is an ETF', () => {
    state.query = { data: { ...held, items: [ETF], as_of: null } }
    renderSummary()
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
    expect(screen.getByText('재무제표가 없는 자산 (ETF 등): SPY')).toBeInTheDocument()
    expect(screen.getByText(`Yahoo Finance. ${DISCLAIMER_KO}`)).toBeInTheDocument()
  })

  it('is a wrapping list, not a table, and never judges a figure', () => {
    const { container } = renderSummary()
    expect(container.querySelector('table')).toBeNull()
    expect(container.querySelector('[class*="overflow-x"]')).toBeNull()
    expect(container.querySelector('dl')).toHaveClass('grid-cols-2')
    expect(container.textContent).not.toMatch(FUNDAMENTALS_BANNED_RE)
    expect(container.textContent).not.toMatch(/[▲▼]/)
    expect(container.querySelector('[class*="text-gain"], [class*="text-loss"]')).toBeNull()
  })
})
