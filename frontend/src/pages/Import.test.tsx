import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ImportPreview, ImportPreviewRow, ImportStatus, ManualImport } from '../api/client'
import { Import } from './Import'

type MutateOptions = { onSuccess?: (data: ImportPreview) => void }

const ready: ImportStatus = { configured: true, engine: 'fake', model: 'demo', problem: null }
const state: { status: ImportStatus } = { status: ready }

// What the backend answers for a typed-in row: the resolved symbol, and the current price
// (marked as such) when none was given. Synthetic values only.
function previewFor(data: ManualImport): ImportPreview {
  return {
    broker: null,
    rows: data.rows.map((r): ImportPreviewRow => {
      const base = String(r.symbol).replace(/-USD$/, '')
      const symbol = r.asset_type === 'crypto' ? `${base}-USD` : base
      const filled = r.avg_price == null
      return {
        name: symbol === 'BTC-USD' ? 'Bitcoin' : symbol,
        symbol,
        asset_type: r.asset_type,
        quantity: Number(r.quantity),
        currency: r.currency ?? 'USD',
        avg_price: filled ? 123.45 : Number(r.avg_price),
        cost_krw: null,
        implied_fx: null,
        price_estimated: filled,
        ticker_guessed: false,
        confidence: 'high',
        status: 'ok',
        message: filled ? '평균단가를 입력하지 않아 현재가로 채웠어요.' : null,
        warning: null,
        current_quantity: null,
        diff: 'new',
        delta_quantity: null,
        delta_price: null,
        origin: 'manual',
      }
    }),
  }
}

const manualMutate = vi.fn((data: ManualImport, opts?: MutateOptions) => opts?.onSuccess?.(previewFor(data)))

vi.mock('../api/hooks', () => ({
  useImportStatus: () => ({ data: state.status }),
  usePreviewScreenshots: () => ({ mutate: vi.fn(), isPending: false, data: undefined, error: null }),
  useCommitImport: () => ({ mutate: vi.fn(), isPending: false, error: null }),
  useManualImport: () => ({ mutate: manualMutate, isPending: false, error: null }),
  useSupportedCrypto: () => ({
    data: [
      { symbol: 'BTC-USD', name: 'Bitcoin', asset_type: 'crypto' },
      { symbol: 'ETH-USD', name: 'Ethereum', asset_type: 'crypto' },
    ],
  }),
}))

const renderPage = () =>
  render(
    <MemoryRouter>
      <Import />
    </MemoryRouter>,
  )

const submitManual = () =>
  fireEvent.submit(screen.getByRole('button', { name: '목록에 추가' }).closest('form')!)

const addStock = (symbol: string, quantity: string, price = '') => {
  fireEvent.change(screen.getByLabelText('티커'), { target: { value: symbol } })
  fireEvent.change(screen.getByLabelText('수량'), { target: { value: quantity } })
  fireEvent.change(screen.getByPlaceholderText('비우면 현재가'), { target: { value: price } })
  submitManual()
}

describe('Import page: typing holdings in', () => {
  beforeEach(() => {
    manualMutate.mockClear()
    state.status = ready
  })
  afterEach(cleanup)

  it('adds a typed-in stock to the review table, ticked, and notes the filled-in price', () => {
    renderPage()
    expect(screen.getByRole('heading', { name: '보유 종목 가져오기' })).toBeInTheDocument()
    expect(screen.queryByText('2. 확인 및 수정')).not.toBeInTheDocument()

    addStock('aapl', '10')

    // Strings, not numbers: the backend parses exact decimals. No price -> null.
    expect(manualMutate).toHaveBeenCalledTimes(1)
    expect(manualMutate.mock.calls[0][0]).toEqual({
      rows: [{ asset_type: 'stock', symbol: 'AAPL', quantity: '10', avg_price: null, currency: 'USD' }],
    })
    expect(screen.getByText('2. 확인 및 수정')).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'AAPL 가져오기' })).toBeChecked()
    expect(screen.getByText('주식 · 직접 입력')).toBeInTheDocument()
    expect(screen.getByText(/현재가로 채웠어요/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '1개 종목 가져오기' })).toBeEnabled()
    // The form is cleared for the next entry.
    expect(screen.getByLabelText('티커')).toHaveValue('')
    expect(screen.getByLabelText('수량')).toHaveValue('')
  })

  it('sends a typed price as is and does not mark the row as estimated', () => {
    renderPage()
    addStock('MSFT', '2', '300.5')
    expect(manualMutate.mock.calls[0][0]).toEqual({
      rows: [{ asset_type: 'stock', symbol: 'MSFT', quantity: '2', avg_price: '300.5', currency: 'USD' }],
    })
    expect(screen.getByDisplayValue('300.5')).toBeInTheDocument()
    expect(screen.queryByText(/현재가로 채웠어요/)).not.toBeInTheDocument()
  })

  it('offers the supported coins and a currency toggle that defaults to won', () => {
    renderPage()
    fireEvent.click(within(screen.getByRole('radiogroup', { name: '자산 종류' })).getByRole('radio', { name: '코인' }))

    const select = screen.getByLabelText('코인')
    expect(within(select).getByRole('option', { name: 'BTC · Bitcoin' })).toBeInTheDocument()
    expect(within(select).getByRole('option', { name: 'ETH · Ethereum' })).toBeInTheDocument()
    const currency = screen.getByRole('radiogroup', { name: '거래 통화' })
    expect(within(currency).getByRole('radio', { name: '원화 (업비트·빗썸)' })).toBeChecked()
    expect(screen.getByPlaceholderText('비우면 현재가')).toBeInTheDocument()
    expect(screen.getByText('평균단가 (KRW, 선택)')).toBeInTheDocument()

    fireEvent.change(select, { target: { value: 'BTC-USD' } })
    fireEvent.change(screen.getByLabelText('수량'), { target: { value: '0.01' } })
    submitManual()

    expect(manualMutate.mock.calls[0][0]).toEqual({
      rows: [{ asset_type: 'crypto', symbol: 'BTC-USD', quantity: '0.01', avg_price: null, currency: 'KRW' }],
    })
    expect(screen.getByRole('checkbox', { name: 'Bitcoin 가져오기' })).toBeChecked()
    expect(screen.getByText('코인 · 직접 입력')).toBeInTheDocument()
    expect(screen.getByText('원화 거래')).toBeInTheDocument()
  })

  it('switching to dollars for a coin is sent along', () => {
    renderPage()
    fireEvent.click(within(screen.getByRole('radiogroup', { name: '자산 종류' })).getByRole('radio', { name: '코인' }))
    fireEvent.click(
      within(screen.getByRole('radiogroup', { name: '거래 통화' })).getByRole('radio', { name: '달러 (해외 거래소)' }),
    )
    fireEvent.change(screen.getByLabelText('코인'), { target: { value: 'ETH-USD' } })
    fireEvent.change(screen.getByLabelText('수량'), { target: { value: '0.5' } })
    submitManual()
    expect(manualMutate.mock.calls[0][0]).toMatchObject({ rows: [{ symbol: 'ETH-USD', currency: 'USD' }] })
  })

  it('adding the same symbol again replaces the earlier row', () => {
    renderPage()
    addStock('MSFT', '2', '300')
    addStock('MSFT', '5', '310')
    expect(screen.getAllByRole('checkbox', { name: 'MSFT 가져오기' })).toHaveLength(1)
    expect(screen.getByDisplayValue('5')).toBeInTheDocument()
    expect(screen.queryByDisplayValue('2')).not.toBeInTheDocument()

    addStock('AAPL', '1', '100')
    expect(screen.getAllByRole('checkbox', { name: /가져오기$/ })).toHaveLength(2)
    expect(screen.getByRole('button', { name: '2개 종목 가져오기' })).toBeEnabled()
  })

  it('keeps the manual entry available when the screenshot reader is not set up', () => {
    state.status = {
      configured: false,
      engine: 'claude',
      model: 'claude-demo',
      problem: 'AM_ANTHROPIC_API_KEY가 설정되지 않았습니다.',
    }
    renderPage()
    expect(screen.getByText('AM_ANTHROPIC_API_KEY가 설정되지 않았습니다.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '보유 종목 읽기' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '목록에 추가' })).toBeInTheDocument()

    addStock('AAPL', '3')
    expect(screen.getByRole('checkbox', { name: 'AAPL 가져오기' })).toBeChecked()
  })
})
