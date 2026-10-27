import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { CoachDiagnosis } from '../api/client'
import { CoachCard } from './CoachCard'

const state: { data?: Partial<CoachDiagnosis> } = {}

vi.mock('../api/hooks', () => ({ useCoachDiagnosis: () => state }))

// Synthetic figures only.
const diagnosis = (over: Partial<CoachDiagnosis>): Partial<CoachDiagnosis> => ({
  empty: false,
  policy_set: true,
  cash_krw: null,
  violations: [],
  exposure: { equity_krw: 1, invested_krw: 1, stock_pct: 70, crypto_pct: 30, cash_pct: null, usd_pct: 70 },
  ...over,
})

const renderCard = () =>
  render(
    <MemoryRouter>
      <CoachCard />
    </MemoryRouter>,
  )

describe('CoachCard', () => {
  afterEach(cleanup)

  it('renders nothing while loading or on error', () => {
    state.data = undefined
    const { container } = renderCard()
    expect(container).toBeEmptyDOMElement()
  })

  it('nudges to write a policy when none is saved', () => {
    state.data = diagnosis({ policy_set: false })
    renderCard()
    expect(screen.getByRole('link')).toHaveAttribute('href', '/coach')
    expect(screen.getByText('정책을 아직 정하지 않았어요 →')).toBeInTheDocument()
  })

  it('summarises violations, the coin share and missing cash, with the disclaimer', () => {
    state.data = diagnosis({
      violations: [
        { code: 'crypto_over_cap', severity: 'warn', label_ko: '코인 합산 상한 초과', detail: '', value: 30, limit: 20, subject: 'crypto' },
        { code: 'cash_missing', severity: 'info', label_ko: '현금 미입력', detail: '', value: null, limit: null, subject: null },
      ],
    })
    renderCard()
    expect(screen.getByText('정책 위반 1건 · 코인 비중 30% · 현금 미입력 →')).toBeInTheDocument()
    expect(screen.getByText(/투자 조언이 아닙니다/)).toBeInTheDocument()
  })

  it('renders nothing with no holdings', () => {
    state.data = diagnosis({ empty: true })
    const { container } = renderCard()
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing with no holdings even before a policy is saved', () => {
    // N-COACH-4: "nothing held" wins over the policy nudge.
    state.data = diagnosis({ empty: true, policy_set: false })
    const { container } = renderCard()
    expect(container).toBeEmptyDOMElement()
  })
})
