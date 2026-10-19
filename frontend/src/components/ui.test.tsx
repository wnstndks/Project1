import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { PnL } from './ui'

describe('PnL', () => {
  it('marks gains red with an up arrow and plus sign', () => {
    render(<PnL value={12.5} pct={3.2} />)
    const el = screen.getByText(/\+\$12\.50/)
    expect(el).toHaveClass('text-gain')
    expect(el).toHaveTextContent('▲+$12.50(+3.20%)')
  })

  it('marks losses blue with a down arrow and minus sign', () => {
    render(<PnL value={-4} />)
    const el = screen.getByText(/−\$4\.00/)
    expect(el).toHaveClass('text-loss')
    expect(el).toHaveTextContent('▼−$4.00')
  })
})
