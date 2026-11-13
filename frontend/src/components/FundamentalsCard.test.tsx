import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Fundamentals } from '../api/client'
import { ApiError } from '../api/client'
import { FUNDAMENTALS_BANNED_RE } from '../lib/fundamentals'
import { AAA, ADR, BANK, COIN, DISCLAIMER_KO, ETF, FAILED, LOSS, NON_OPERATING, OP_LOSS } from '../lib/fundamentals.fixtures'
import { FundamentalsCard } from './FundamentalsCard'

type Q = { data?: Fundamentals; error?: unknown }
const state: { query: Q; asked: string[] } = { query: {}, asked: [] }

vi.mock('../api/hooks', () => ({
  useFundamentals: (symbol: string) => {
    state.asked.push(symbol)
    return state.query
  },
}))

const renderCard = (symbol = 'AAA') =>
  render(
    <MemoryRouter>
      <FundamentalsCard symbol={symbol} />
    </MemoryRouter>,
  )

/** The value cell beside a figure's label. */
const valueOf = (label: string) => screen.getByText(label, { selector: 'dt' }).nextElementSibling as HTMLElement

const NO_GAIN_LOSS = '[class*="text-gain"], [class*="text-loss"]'

describe('FundamentalsCard', () => {
  beforeEach(() => {
    state.query = { data: AAA }
    state.asked = []
  })
  afterEach(cleanup)

  it('shows the company line, every figure with its meaning, and the source with the disclaimer', () => {
    renderCard()
    expect(state.asked).toEqual(['AAA'])
    expect(screen.getByRole('heading', { name: '기업 재무' })).toBeInTheDocument()
    expect(screen.getByText('AAA Inc. · Technology · Software - Application')).toBeInTheDocument()
    expect(screen.getByText('회사가 공개한 재무 숫자예요. 예측이나 매매 신호가 아닙니다.')).toBeInTheDocument()

    const figures: [string, string][] = [
      ['시가총액', '3.40조 달러'],
      ['PER', '28.4배'],
      ['예상 PER', '24.1배'],
      ['PBR', '45.1배'],
      ['PSR', '8.70배'],
      ['EPS', '$6.42'],
      ['영업이익률', '31.2%'],
      ['순이익률', '24.3%'],
      ['ROE', '151.9%'],
      ['매출 성장률', '+6.1%'],
      ['이익 성장률', '−3.4%'],
      ['부채비율', '154.5%'],
      ['배당수익률', '0.43%'],
    ]
    for (const [label, value] of figures) expect(valueOf(label), label).toHaveTextContent(value)
    expect(screen.getAllByRole('term')).toHaveLength(13)

    // Meanings in everyday words; the ones whose period differs say which.
    expect(screen.getByText('주가가 1주당 순이익의 몇 배인지 (최근 12개월 이익)')).toBeInTheDocument()
    expect(screen.getByText('증권가 추정 이익 기준(추정)')).toBeInTheDocument()
    expect(screen.getByText('매출 100원 중 영업으로 남긴 돈 (최근 분기)')).toBeInTheDocument()
    expect(screen.getByText('매출 100원 중 세금까지 내고 남긴 돈 (최근 12개월)')).toBeInTheDocument()
    expect(screen.getByText('자기 돈으로 1년에 번 비율')).toBeInTheDocument()
    for (const title of ['가치', '수익성·성장', '안정성·배당']) {
      expect(screen.getByRole('heading', { name: title })).toBeInTheDocument()
    }

    expect(screen.getByText(`Yahoo Finance · 2026-11-11 기준. ${DISCLAIMER_KO}`)).toBeInTheDocument()
    expect(screen.getByText(/이 숫자만으로 매수·매도를 판단할 수 없습니다. 업종마다 기준이 다릅니다./)).toBeInTheDocument()
    expect(screen.getByText(/투자 조언이 아닙니다/)).toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows the income statement by year, switches to quarters, and names the currency', () => {
    renderCard()
    const table = screen.getByRole('table', { name: '매출·영업이익·순이익' })
    expect(within(table).getAllByRole('columnheader').map((h) => h.textContent)).toEqual([
      '회계연도 끝',
      '매출',
      '영업이익',
      '순이익',
    ])
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows.map((r) => r.textContent)).toEqual(['2025.094,161억1,331억1,120억', '2024.093,910억1,232억937억'])
    expect(screen.getByText('금액은 미국 달러(USD) 기준이에요.')).toBeInTheDocument()

    expect(screen.getByRole('radio', { name: '연간' })).toBeChecked()
    fireEvent.click(screen.getByRole('radio', { name: '분기' }))
    expect(screen.getByRole('columnheader', { name: '분기 끝' })).toBeInTheDocument()
    expect(within(screen.getByRole('table')).getAllByRole('row')[1]).toHaveTextContent('2026.06940억282억234억')
  })

  it('folds the business description and marks it as the English original', () => {
    const { container } = renderCard()
    const details = container.querySelector('details')
    expect(details).not.toHaveAttribute('open')
    expect(within(details as HTMLElement).getByText('사업 설명 (영문 원문)')).toBeInTheDocument()
    expect(screen.getByText(AAA.summary as string)).toHaveAttribute('lang', 'en')
    cleanup()
    state.query = { data: { ...AAA, summary: null } }
    expect(renderCard().container.querySelector('details')).toBeNull()
  })

  it('says why a loss-making company has no PER, with signs only and no gain/loss colour', () => {
    state.query = { data: LOSS }
    const { container } = renderCard('BBB')
    expect(valueOf('PER')).toHaveTextContent('–')
    expect(screen.getByText('적자라 PER을 계산할 수 없어요')).toBeInTheDocument()
    expect(valueOf('예상 PER')).toHaveTextContent('–')
    expect(screen.getByText('추정 이익이 적자라 예상 PER을 계산할 수 없어요')).toBeInTheDocument()
    expect(valueOf('EPS')).toHaveTextContent('−$1.23')
    expect(valueOf('영업이익률')).toHaveTextContent('−18.3%')
    expect(valueOf('순이익률')).toHaveTextContent('−12.5%')
    expect(valueOf('매출 성장률')).toHaveTextContent('−7.3%')
    // Missing with no stated reason: a dash only.
    expect(valueOf('이익 성장률').textContent).toBe('–')
    expect(valueOf('배당수익률')).toHaveTextContent('배당 없음')
    expect(within(screen.getByRole('table')).getAllByRole('row')[1]).toHaveTextContent('2025.12200억−31.0억−25.0억')
    // No quarterly rows: the tab says so instead of an empty table.
    fireEvent.click(screen.getByRole('radio', { name: '분기' }))
    expect(screen.getByText('이 기간의 손익계산서를 받지 못했어요.')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()

    expect(container.querySelector(NO_GAIN_LOSS)).toBeNull()
    expect(container.textContent).not.toMatch(/[▲▼]/)
  })

  it('points out, on the PER line itself, a PER that sits beside an operating loss', () => {
    state.query = { data: OP_LOSS }
    const { container } = renderCard('EEE')
    const label = screen.getByText('PER', { selector: 'dt' })
    expect(valueOf('PER')).toHaveTextContent('20.1배')
    expect(
      within(label).getByText(
        '최근 분기 영업이익은 적자인데 최근 12개월 순이익은 흑자예요. PER은 순이익 기준이니 영업이익도 함께 보세요.',
      ),
    ).toBeInTheDocument()
    // The figures it refers to are on the same card, in the neutral ink.
    expect(valueOf('영업이익률')).toHaveTextContent('−35.2%')
    fireEvent.click(screen.getByRole('radio', { name: '분기' }))
    expect(within(screen.getByRole('table')).getAllByRole('row')[1]).toHaveTextContent('2026.06940억−331억120억')
    expect(container.querySelector(NO_GAIN_LOSS)).toBeNull()

    cleanup()
    state.query = { data: { ...OP_LOSS, notes: ['operating_loss_net_profit_annual'] } }
    renderCard('EEE')
    expect(within(screen.getByText('PER', { selector: 'dt' })).getByText(/^최근 회계연도 영업이익은 적자인데/)).toBeInTheDocument()
    // A company without the note says nothing of the kind.
    cleanup()
    state.query = { data: AAA }
    renderCard()
    expect(screen.queryByText(/영업이익은 적자인데/)).not.toBeInTheDocument()
  })

  it('says on the operating margin line why a bank has none, and leaves the column as dashes', () => {
    state.query = { data: BANK }
    renderCard('FFF')
    expect(valueOf('영업이익률').textContent).toBe('–')
    expect(
      within(screen.getByText('영업이익률', { selector: 'dt' })).getByText(
        '이 회사 손익계산서에는 영업이익 항목이 없어 영업이익률을 계산하지 않았어요',
      ),
    ).toBeInTheDocument()
    expect(valueOf('순이익률')).toHaveTextContent('24.3%')
    expect(within(screen.getByRole('table')).getAllByRole('row')[1]).toHaveTextContent('2025.121,800억–570억')

    cleanup()
    state.query = { data: { ...BANK, notes: ['zero_revenue_quarter'] } }
    renderCard('FFF')
    expect(
      within(screen.getByText('영업이익률', { selector: 'dt' })).getByText('최근 분기 매출이 0이라 영업이익률을 계산할 수 없어요'),
    ).toBeInTheDocument()
  })

  it('says on the net margin line when net income is above operating income', () => {
    state.query = { data: NON_OPERATING }
    const { container } = renderCard('GGG')
    const label = screen.getByText('순이익률', { selector: 'dt' })
    expect(valueOf('순이익률')).toHaveTextContent('52.4%')
    expect(valueOf('영업이익률')).toHaveTextContent('31.2%')
    expect(
      within(label).getByText('최근 12개월 순이익이 영업이익보다 커요. 순이익에는 영업 외 손익이 더해져 있어요.'),
    ).toBeInTheDocument()
    // Only that line carries it, and the two figures stay in the neutral ink.
    expect(screen.getAllByText(/순이익이 영업이익보다 커요/)).toHaveLength(1)
    expect(container.querySelector(NO_GAIN_LOSS)).toBeNull()

    cleanup()
    state.query = { data: { ...NON_OPERATING, notes: ['net_income_above_operating_income_annual'] } }
    renderCard('GGG')
    expect(
      within(screen.getByText('순이익률', { selector: 'dt' })).getByText(/^최근 회계연도 순이익이 영업이익보다 커요/),
    ).toBeInTheDocument()
    cleanup()
    state.query = { data: AAA }
    renderCard()
    expect(screen.queryByText(/순이익이 영업이익보다 커요/)).not.toBeInTheDocument()
  })

  it('marks figures kept from before a failed refresh as the last ones received', () => {
    state.query = { data: { ...AAA, stale: true, error: 'yfinance info failed for AAA: rate limited' } }
    renderCard()
    const note = screen.getByRole('status')
    expect(note).toHaveTextContent('새 값을 받지 못해 마지막으로 받은 값을 보여 줘요.')
    expect(note).toHaveTextContent('yfinance info failed for AAA: rate limited')
    expect(screen.getByText(`Yahoo Finance · 2026-11-11 기준 · 마지막으로 받은 값. ${DISCLAIMER_KO}`)).toBeInTheDocument()
    // The figures are still there.
    expect(valueOf('PER')).toHaveTextContent('28.4배')
  })

  it('says so in one line when nothing could be fetched yet, with the reason and no figures', () => {
    state.query = { data: FAILED }
    renderCard('DDD')
    expect(screen.getByText(/지금은 재무 숫자를 받지 못했어요\./)).toBeInTheDocument()
    expect(screen.getByText('(yfinance info failed for DDD: timeout)')).toBeInTheDocument()
    expect(screen.queryByRole('term')).not.toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it.each([
    ['a coin', COIN],
    ['an ETF', ETF],
  ])('shows one line for %s: an asset without statements', (_, data) => {
    state.query = { data }
    const { container } = renderCard(data.symbol)
    expect(screen.getByRole('heading', { name: '기업 재무' })).toBeInTheDocument()
    expect(screen.getByText('재무제표가 없는 자산이에요 (코인·ETF 등).')).toBeInTheDocument()
    expect(screen.queryByRole('term')).not.toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(container.querySelector('details')).toBeNull()
  })

  it('explains the dashes of an ADR once and counts its statement in the statement currency', () => {
    state.query = { data: ADR }
    renderCard('CCC')
    expect(screen.getByText('재무제표 통화(TWD)와 거래 통화가 달라 일부 지표는 계산하지 않았어요')).toBeInTheDocument()
    for (const label of ['시가총액', 'PBR', 'PSR', 'EPS']) expect(valueOf(label).textContent, label).toBe('–')
    expect(valueOf('PER')).toHaveTextContent('28.4배')
    expect(within(screen.getByRole('table')).getAllByRole('row')[1]).toHaveTextContent('2025.122.90조1.30조1.10조')
    expect(screen.getByText('금액은 재무제표 통화(TWD) 기준이에요.')).toBeInTheDocument()
  })

  it('shows a placeholder while loading and the error box on a failure', () => {
    state.query = {}
    const { container } = renderCard()
    expect(screen.getByRole('status')).toHaveTextContent('불러오는 중')
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull()
    cleanup()
    state.query = { error: new ApiError(502, 'yfinance request failed') }
    renderCard()
    expect(screen.getByRole('alert')).toHaveTextContent('yfinance request failed')
    expect(screen.getByRole('heading', { name: '기업 재무' })).toBeInTheDocument()
  })

  it.each([
    ['profit', AAA],
    ['loss', LOSS],
    ['operating loss beside a PER', OP_LOSS],
    ['bank', BANK],
    ['net income above operating income', NON_OPERATING],
    ['ADR', ADR],
    ['stale', { ...AAA, stale: true, error: 'x' }],
    ['failed', FAILED],
    ['coin', COIN],
  ])('never judges a figure: no verdict word, arrow or gain/loss colour (%s)', (_, data) => {
    state.query = { data }
    const { container } = renderCard(data.symbol)
    // The English business description is the company's own text, not the app's wording.
    const text = (container.textContent ?? '').replace(data.summary ?? '', '')
    expect(text).not.toMatch(FUNDAMENTALS_BANNED_RE)
    expect(text).not.toMatch(/[▲▼]/)
    expect(container.querySelector(NO_GAIN_LOSS)).toBeNull()
  })
})
