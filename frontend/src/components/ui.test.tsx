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

  it('rounds the percentage to the requested digits', () => {
    renderIn('USD', <PnL pctOnly value={0} pct={-8.14} digits={1} />)
    expect(screen.getByText(/−8\.1%/)).toHaveClass('text-loss')
    renderIn('USD', <PnL value={2} pct={2.345} digits={1} />)
    expect(screen.getByText(/\+\$2\.00/)).toHaveTextContent('▲+$2.00(+2.3%)')
  })

  it('formats in won by default', () => {
    render(
      <CurrencyProvider>
        <PnL value={-397_000} />
      </CurrencyProvider>,
    )
    expect(screen.getByText(/−397,000원/)).toHaveClass('text-loss')
  })
})
