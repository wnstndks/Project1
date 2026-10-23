import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { HeldForecast, Holding } from '../api/client'
import { CurrencyProvider } from '../lib/currency'
import { isoDate } from '../lib/format'
import { HoldingsList } from './HoldingsList'

// A past bar (the US close) for the stock, a live quote dated today for the coin.
const STOCK_AS_OF = '2026-10-22T00:00:00'
const COIN_AS_OF = `${isoDate(new Date())}T03:15:00`

function horizon(over: Partial<HeldForecast['horizons'][number]>): HeldForecast['horizons'][number] {
  return {
    horizon: '1w',
    as_of: '2026-10-22',
    target_date: '2026-10-29',
    low_ratio: 0.964,
    mid_ratio: 1.005,
    high_ratio: 1.045,
    p_up: 0.53,
    baseline_p_up: 0.54,
    direction_edge: false,
    range_edge: false,
    direction_reason: 'not_significant',
    range_reason: 'not_significant',
    ...over,
  }
}

// One request for the whole list; only the first fake symbol has a forecast, one for the rules too.
vi.mock('../api/hooks', () => ({
  useHeldForecasts: () => ({
    data: [
      {
        symbol: 'AAA',
        asset_class: 'stock',
        horizons: [horizon({ horizon: '1d', target_date: '2026-10-23', low_ratio: 0.98, high_ratio: 1.02 }), horizon({})],
      },
    ],
    error: null,
  }),
  useRuleCheck: () => ({
    data: {
      checks: [
        { symbol: 'AAA', status: 'cut', chip_ko: '매도 검토' },
        { symbol: 'BBB-USD', status: 'hold', chip_ko: '관망' },
      ],
    },
    error: null,
  }),
}))

function holding(over: Partial<Holding>): Holding {
  return {
    symbol: 'AAA',
    // The backend names only coins; a stock's name is its ticker.
    name: 'AAA',
    asset_type: 'stock',
    currency: 'USD',
    quantity: 13,
    avg_cost: 80,
    cost_basis: 1040,
    price: 100,
    price_as_of: STOCK_AS_OF,
    prev_close: 98.8,
    day_change: 1.2,
    day_change_pct: 1.21,
    day_change_krw: 1700,
    market_value: 1300,
    unrealized_pnl: 260,
    unrealized_pct: 25,
    realized_pnl: 0,
    dividends: 0,
    avg_cost_krw: 112_000,
    cost_basis_krw: 1_456_000,
    price_krw: 140_000,
    market_value_krw: 1_820_000,
    unrealized_pnl_krw: 364_000,
    unrealized_pct_krw: 25,
    realized_pnl_krw: 0,
    weight: 60,
    ...over,
  }
}

const rows = [
  holding({}),
  holding({
    symbol: 'BBB-USD',
    name: 'Fake Coin',
    asset_type: 'crypto',
    quantity: 0.5,
    avg_cost: 2, // 50x below the price: the import read something else as the unit price
    price: 100,
    price_as_of: COIN_AS_OF,
    day_change: -3,
    day_change_pct: -2.5,
    day_change_krw: -4200,
    weight: 40,
  }),
]

function renderList(currency: 'KRW' | 'USD' = 'USD') {
  localStorage.setItem('asset-manager.currency', currency)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <CurrencyProvider>
        <MemoryRouter>
          <HoldingsList
            holdings={rows}
            sparklines={[
              { symbol: 'AAA', closes: [90, 95, 100] },
              { symbol: 'BBB-USD', closes: [] },
            ]}
          />
        </MemoryRouter>
      </CurrencyProvider>
    </QueryClientProvider>,
  )
}

describe('HoldingsList', () => {
  // No vitest globals, so Testing Library cannot auto-unmount between tests.
  afterEach(() => {
    cleanup()
    localStorage.clear()
  })

  it('renders one linked row per holding, largest weight first, with a chevron and sparkline', () => {
    renderList()
    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(within(items[0]).getAllByRole('link')[0]).toHaveAttribute('href', '/assets/AAA')
    expect(within(items[1]).getAllByRole('link')[0]).toHaveAttribute('href', '/assets/BBB-USD')
    expect(within(items[0]).getByText('13주 · 비중 60.0%')).toBeInTheDocument()
    // Only coins carry a name from the backend; it leads the subtitle.
    expect(within(items[1]).getByText('Fake Coin · 0.5 BBB · 비중 40.0%')).toBeInTheDocument()
    expect(items[0].querySelector('polyline')).not.toBeNull()
    expect(items[1].querySelector('polyline')).toBeNull()
  })

  it('flags the holding whose average cost is 20x off its price, with a link to the check list', () => {
    renderList()
    const badges = screen.getAllByText('단가 확인')
    expect(badges).toHaveLength(1)
    const items = screen.getAllByRole('listitem')
    expect(within(items[1]).getByText('단가 확인')).toHaveClass('text-danger')
    expect(within(items[0]).queryByText('단가 확인')).toBeNull()
    // The badge's title is not reachable by touch, so the row also says it in text, as a link.
    const fix = within(items[1]).getByRole('link', { name: '단가 확인 필요 · 거래에서 수정' })
    expect(fix).toHaveAttribute('href', '/transactions?check=1')
    expect(within(items[0]).queryByText(/단가 확인 필요/)).toBeNull()
    // No link nested inside the row link.
    expect(items[1].querySelector('a a')).toBeNull()
  })

  it("shows the session's move to one decimal, red up and blue down, dated by the quote", () => {
    renderList()
    const items = screen.getAllByRole('listitem')
    const up = within(items[0]).getByText(/\+1\.2%/)
    expect(up).toHaveClass('text-gain')
    expect(up).toHaveTextContent('▲+1.2%')
    const down = within(items[1]).getByText(/−2\.5%/)
    expect(down).toHaveClass('text-loss')
    expect(down).toHaveTextContent('▼−2.5%')
    // The stock's quote is a past close, the coin's is from today.
    expect(within(items[0]).getByText('전일 대비')).toBeInTheDocument()
    expect(within(items[1]).getByText('오늘')).toBeInTheDocument()
    expect(within(items[0]).getByText('$100.00')).toBeInTheDocument()
    expect(within(items[0]).getByText('$1,300.00')).toBeInTheDocument()
    // The return rate is one decimal in the list too.
    expect(within(items[0]).getByText(/\+25\.0%/)).toHaveTextContent('▲+25.0%')
  })

  it('adds the one-week range hint only where a forecast exists', () => {
    renderList()
    const items = screen.getAllByRole('listitem')
    expect(
      within(items[0]).getByText('1주 변동 범위 대체로 −3.6%~+4.5% 사이 (10번 중 8번) · 참고용'),
    ).toBeInTheDocument()
    expect(within(items[1]).queryByText(/변동 범위/)).toBeNull()
  })

  it('shows the rule-check chip joined by symbol, with text and tone', () => {
    renderList()
    const items = screen.getAllByRole('listitem')
    expect(within(items[0]).getByText('매도 검토')).toHaveClass('text-loss')
    expect(within(items[1]).getByText('관망')).toHaveClass('text-ink-2')
  })

  it('lets the chips wrap under the ticker rather than shrink or be clipped in a narrow title column', () => {
    renderList()
    const items = screen.getAllByRole('listitem')
    // The second row carries both chips (단가 확인 + 관망), the case that clipped on a 390px phone.
    const badge = within(items[1]).getByText('단가 확인')
    const chip = within(items[1]).getByText('관망')
    expect(badge).toHaveClass('shrink-0')
    expect(chip).toHaveClass('shrink-0', 'whitespace-nowrap')
    expect(badge.parentElement).toHaveClass('flex-wrap')
    expect(badge.parentElement).toBe(chip.parentElement)
  })

  it('switches prices and values to won', () => {
    renderList('KRW')
    const items = screen.getAllByRole('listitem')
    expect(within(items[0]).getByText('140,000원')).toBeInTheDocument()
    expect(within(items[0]).getByText('1,820,000원')).toBeInTheDocument()
  })
})
