import { cleanup, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'

import { GuruOverlap } from './GuruOverlap'

function renderOverlap(overlaps = defaultOverlaps, missing = defaultMissing) {
  return render(
    <MemoryRouter>
      <GuruOverlap name="캐시 우드" overlaps={overlaps} missing={missing} />
    </MemoryRouter>,
  )
}

const defaultOverlaps = [
  { symbol: 'AAA', name: 'Fake A', my_weight_pct: 60, guru_weight_pct: 2.14 },
  { symbol: 'BBB-USD', name: 'Fake Coin', my_weight_pct: 40, guru_weight_pct: 0.5 },
]
const defaultMissing = [
  { symbol: 'CCC', name: 'Fake C', weight_pct: 9.5 },
  { symbol: null, name: 'Private Co', weight_pct: 3.25 },
]

describe('GuruOverlap', () => {
  // No vitest globals, so Testing Library cannot auto-unmount between tests.
  afterEach(cleanup)

  it('draws my weight and theirs as two bars per shared ticker, numbers beside them', () => {
    renderOverlap()
    const rows = within(screen.getByRole('list', { name: '캐시 우드과(와) 겹치는 종목' })).getAllByRole('listitem')
    expect(rows).toHaveLength(2)
    expect(within(rows[0]).getByRole('link')).toHaveAttribute('href', '/assets/AAA')
    expect(within(rows[0]).getByRole('img', { name: '내 비중 60.0%' })).toBeInTheDocument()
    expect(within(rows[0]).getByRole('img', { name: '캐시 우드 비중 2.1%' })).toBeInTheDocument()
    // Bars share one scale: my 60% is the widest, their 0.5% is still at least visible.
    const bars = rows.flatMap((r) => Array.from(r.querySelectorAll<HTMLElement>('[role="img"] > div')))
    expect(bars[0].style.width).toBe('100%')
    expect(bars[3].style.width).toBe('1%')
    expect(bars[0].style.background).toBe('var(--series-1)')
    expect(bars[1].style.background).toBe('var(--series-2)')
    expect(within(rows[1]).getByRole('link')).toHaveTextContent('BBB')
  })

  it('lists their top positions I lack as chips, linking only those with a ticker', () => {
    renderOverlap()
    const chips = within(screen.getByRole('list', { name: '캐시 우드의 상위 종목 중 내게 없는 것' })).getAllByRole('listitem')
    expect(chips).toHaveLength(2)
    expect(within(chips[0]).getByRole('link')).toHaveAttribute('href', '/assets/CCC')
    expect(chips[0]).toHaveTextContent('CCC9.5%')
    expect(within(chips[1]).queryByRole('link')).toBeNull()
    expect(chips[1]).toHaveTextContent('Private Co3.3%')
  })

  it('says so when nothing overlaps and hides the empty missing list', () => {
    renderOverlap([], [])
    expect(screen.getByText('내 보유 종목 중 캐시 우드이(가) 들고 있는 종목이 없습니다.')).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: /내게 없는 것/ })).toBeNull()
  })
})
