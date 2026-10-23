import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { RuleStatusChip } from './RuleStatusChip'

describe('RuleStatusChip', () => {
  // No vitest globals, so Testing Library cannot auto-unmount between tests.
  afterEach(() => cleanup())

  it('shows the backend label in blue for a sell review', () => {
    render(<RuleStatusChip status="cut" label="매도 검토" />)
    const chip = screen.getByText('매도 검토')
    expect(chip).toHaveClass('text-loss')
    expect(chip).toHaveAttribute('title', expect.stringContaining('예측이 아닙니다'))
  })

  it('shows a buy-more review in red and hold in gray, always with text', () => {
    render(
      <>
        <RuleStatusChip status="add" label="추매 검토" />
        <RuleStatusChip status="hold" label="관망" />
      </>,
    )
    expect(screen.getByText('추매 검토')).toHaveClass('text-gain')
    expect(screen.getByText('관망')).toHaveClass('text-ink-2')
  })

  it('carries no price or probability', () => {
    const { container } = render(<RuleStatusChip status="cut" label="매도 검토" />)
    expect(container.textContent).toBe('매도 검토')
  })
})
