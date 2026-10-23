import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { RuleCheck, RuleCheckAll } from '../api/client'
import { RuleCard } from './RuleCard'

// Demo numbers only: a $100 stock bought at $100 and a won coin, nothing from a real account.
const stock: RuleCheck = {
  symbol: 'AAA',
  asset_type: 'stock',
  currency: 'USD',
  status: 'hold',
  label_ko: '관망',
  chip_ko: '관망',
  triggers: [
    { code: 'insufficient_history', label_ko: '이력 부족', detail: '확정 봉이 부족해 건너뜀: 60일선', kind: 'info' },
  ],
  levels: {
    cut_price: 85,
    cut_loss_price: 85,
    trailing_high: 100,
    trailing_stop_price: 80,
    add_price: 95,
    next_add_step: 1,
    ma_short: 99,
    ma_long: null,
    target_weight_pct: 30,
    risk_amount: 150,
  },
  rule: {
    cut_loss_pct: 15,
    trailing_lookback_days: 60,
    trailing_drop_pct: 20,
    below_ma_days: 5,
    ma_long: 60,
    ma_short: 20,
    add_step_pct: 5,
    add_max_steps: 2,
    add_requires_above_ma_short: true,
    target_weight_gap_pt: 5,
    target_weight_pct: 30,
  },
  price: 100,
  avg_cost: 100,
  quantity: 10,
  weight_pct: 12.5,
  add_steps_done: 0,
  cut_distance_pct: -15,
  add_distance_pct: -5,
  blocked_by: [],
  blocked_labels: [],
  add_cap_krw: null,
  risk_pct_equity: 1.9,
  weight_room_pt: 7.5,
  notes: ['현금 기록이 없어 추매 가능 금액을 확인하지 못했습니다'],
  as_of: '2026-10-22',
  bars: 40,
  history_error: null,
  cut_prob_1m: 0.12,
  cut_prob_1m_label: '약 10%',
  forecast_status: 'ok',
}

const coin: RuleCheck = {
  ...stock,
  symbol: 'BBB-USD',
  asset_type: 'crypto',
  currency: 'KRW',
  status: 'cut',
  label_ko: '손절 검토',
  chip_ko: '매도 검토',
  triggers: [{ code: 'cut_loss', label_ko: '손절 기준 도달', detail: '평균단가 대비 −26.0% (기준 −25%)', kind: 'cut' }],
  levels: { ...stock.levels, cut_price: 60_000_000, cut_loss_price: 60_000_000, add_price: null, next_add_step: null, risk_amount: 0 },
  price: 59_200_000,
  avg_cost: 80_000_000,
  cut_distance_pct: 1.35,
  add_distance_pct: null,
  blocked_labels: ['종목 비중 상한'],
  blocked_by: ['max_position_weight'],
  risk_pct_equity: 0,
  cut_prob_1m_label: null,
  forecast_status: 'not_trained',
  add_steps_done: 2,
}

const data: RuleCheckAll = {
  checks: [stock, coin],
  skipped: [{ symbol: 'CCC', reason: 'avg_cost and price must be positive numbers' }],
  total_risk_pct_equity: 1.9,
  kill_switch: { tripped: false, reason_code: null, detail: '', since: null },
  live_trading: false,
  labels: {
    status: { cut: '손절 검토', add: '추매 검토', hold: '관망' },
    block: {},
    prob_caveat: '기간 끝에 그 아래일 확률이며, 도중에 한 번 닿을 확률은 대략 두 배입니다',
  },
  settings_notes: [],
  checked_at: '2026-10-23T01:00:00',
}

vi.mock('../api/hooks', () => ({
  useRuleCheck: () => ({ data, error: null }),
}))

function renderCard(symbol: string, fx?: number) {
  return render(
    <MemoryRouter>
      <RuleCard symbol={symbol} fx={fx} />
    </MemoryRouter>,
  )
}

describe('RuleCard', () => {
  // No vitest globals, so Testing Library cannot auto-unmount between tests.
  afterEach(() => cleanup())

  it('shows a dollar position in dollars first with the won view small, and distances', () => {
    renderCard('AAA', 1400)
    expect(screen.getByText('관망', { selector: 'span.text-\\[15px\\]' })).toBeInTheDocument()
    expect(screen.getByText('$85.00')).toBeInTheDocument()
    expect(screen.getByText('119,000원')).toBeInTheDocument()
    expect(screen.getByText('손절 검토 가격까지 −15.0%')).toBeInTheDocument()
    expect(screen.getByText('다음 추매가까지 −5.0%')).toBeInTheDocument()
    expect(screen.getByText('$95.00')).toBeInTheDocument()
    expect(screen.getByText(/1\/2회차 · 평균단가 −5%/)).toBeInTheDocument()
    expect(screen.getByText('봉 부족')).toBeInTheDocument()
    expect(screen.getByText('상한까지 7.5%p')).toBeInTheDocument()
    // Loss at the stop: $150 × 1400 = 210,000원 → 21만원, and the share of equity.
    expect(screen.getByText(/약 21만원/)).toBeInTheDocument()
    expect(screen.getByText('총자산의 1.9%')).toBeInTheDocument()
  })

  it('uses the backend probability text with its caveat and lists notes and the link', () => {
    renderCard('AAA', 1400)
    expect(screen.getByText(/확률 약 10% \(범위 예측 기준, 참고\)\. 기간 끝에 그 아래일 확률이며/)).toBeInTheDocument()
    expect(screen.getByText('없음')).toBeInTheDocument() // no fired condition
    expect(screen.getByText('이력 부족')).toBeInTheDocument()
    expect(screen.getByText('현금 기록이 없어 추매 가능 금액을 확인하지 못했습니다')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '규칙 바꾸기 →' })).toHaveAttribute('href', '/rules')
    expect(screen.getByText(/규칙 점검은 예측이 아니라 내가 정한 규칙의 결과입니다/)).toBeInTheDocument()
    expect(screen.getByText(/투자 조언이 아닙니다/)).toBeInTheDocument()
    // The won figures beside a dollar position are today's-rate conversions, and the card says so.
    expect(screen.getByText(/달러 종목의 원화 금액은 오늘 환율로 환산했습니다/)).toBeInTheDocument()
  })

  it('shows a won coin in won only, the fired condition, the block and the missing forecast', () => {
    renderCard('BBB-USD', 1400)
    expect(screen.getByText('매도 검토')).toHaveClass('text-loss')
    expect(screen.getByText('손절 검토', { selector: 'span.text-\\[15px\\]' })).toBeInTheDocument()
    expect(screen.getAllByText('60,000,000원').length).toBeGreaterThan(0)
    expect(screen.queryByText(/\$/)).toBeNull()
    expect(screen.getByText('이미 손절 검토 가격 이하')).toBeInTheDocument()
    expect(screen.getByText('손절 기준 도달')).toBeInTheDocument()
    expect(screen.getByText('분할매수 2회 모두 사용')).toBeInTheDocument()
    expect(screen.getByText('추매 보류: 종목 비중 상한')).toBeInTheDocument()
    expect(screen.getByText(/예측 모델이 아직 학습되지 않아/)).toBeInTheDocument()
    // A won position has no conversion, so no rate note.
    expect(screen.queryByText(/오늘 환율로 환산/)).toBeNull()
  })

  it('reports a skipped symbol with the engine reason', () => {
    renderCard('CCC')
    expect(screen.getByText(/점검하지 못했습니다: avg_cost and price/)).toBeInTheDocument()
  })
})
