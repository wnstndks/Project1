import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { CurrencyProvider } from '../lib/currency'
import { PnL } from './ui'

function renderIn(currency: 'KRW' | 'USD', ui: React.ReactElement) {
  localStorage.setItem('asset-manager.currency', currency)
  return render(<CurrencyProvider>{ui}</CurrencyProvider>)
}

describe('PnL', () => {
  afterEach(() => localStorage.clear())

  it('marks gains red with an up arrow and plus sign', () => {
    renderIn('USD', <PnL value={12.5} pct={3.2} />)
    const el = screen.getByText(/\+\$12\.50/)
    expect(el).toHaveClass('text-gain')
    expect(el).toHaveTextContent('▲+$12.50(+3.20%)')
  })

  it('marks losses blue with a down arrow and minus sign', () => {
    renderIn('USD', <PnL value={-4} />)
    const el = screen.getByText(/−\$4\.00/)
    expect(el).toHaveClass('text-loss')
    expect(el).toHaveTextContent('▼−$4.00')
  })

  it('formats in won by default', () => {
    render(
      <CurrencyProvider>
        <PnL value={-397_000} />
      </CurrencyProvider>,
    )
    expect(screen.getByText(/−₩397,000/)).toHaveClass('text-loss')
  })
})
