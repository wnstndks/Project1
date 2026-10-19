import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Transaction, TransactionInput } from '../api/client'
import { TransactionForm } from './TransactionForm'

function renderForm(
  onSubmit: (data: TransactionInput) => Promise<unknown>,
  props: Partial<Parameters<typeof TransactionForm>[0]> = {},
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, enabled: false } } })
  render(
    <QueryClientProvider client={client}>
      <TransactionForm editing={null} onCancel={() => {}} pending={false} error={null} {...props} onSubmit={onSubmit} />
    </QueryClientProvider>,
  )
}

const typeInto = (placeholder: string, value: string) =>
  fireEvent.change(screen.getByPlaceholderText(placeholder), { target: { value } })

describe('TransactionForm', () => {
  it('keeps the typed values when saving fails', async () => {
    const onSubmit = vi.fn<(d: TransactionInput) => Promise<unknown>>().mockRejectedValue(new Error('oversell'))
    renderForm(onSubmit)
    typeInto('AAPL', 'AAPL')
    typeInto('10', '3')
    fireEvent.submit(screen.getByRole('button', { name: '거래 추가' }).closest('form')!)

    await waitFor(() => expect(onSubmit).toHaveBeenCalled())
    expect(screen.getByPlaceholderText('AAPL')).toHaveValue('AAPL')
    expect(screen.getByPlaceholderText('10')).toHaveValue('3')
  })

  it('sends quantities as exact strings and preserves the recorded fx rate when editing', async () => {
    const editing = {
      id: 1,
      asset_type: 'stock',
      symbol: 'AAPL',
      side: 'buy',
      trade_date: '2026-10-01',
      quantity: 10,
      price: 100,
      fee: 0,
      fx_rate: 1320,
      seq: 0,
      note: null,
      created_at: '2026-10-01T00:00:00',
      usd_krw: 1320,
    } as Transaction
    const onSubmit = vi.fn<(d: TransactionInput) => Promise<unknown>>().mockResolvedValue({})
    renderForm(onSubmit, { editing })
    fireEvent.submit(screen.getByRole('button', { name: '수정 저장' }).closest('form')!)

    await waitFor(() => expect(onSubmit).toHaveBeenCalled())
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ quantity: '10', fx_rate: '1320' })
  })
})
