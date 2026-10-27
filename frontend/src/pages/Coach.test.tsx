import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  CoachDiagnosis,
  CoachPatterns,
  CoachPolicy,
  CoachPolicyInput,
  CoachRebalance,
  CoachReview,
  RuleCheckAll,
} from '../api/client'
import { CurrencyProvider } from '../lib/currency'
import { Coach } from './Coach'

// Synthetic values only. The defaults mirror the settings the backend derives them from:
// 20% position cap, 20% drawdown, 80/20/0 asset classes, 30% crypto cap, 8% total risk.
const defaults: CoachPolicy['policy'] = {
  goal_krw: null,
  goal_date: null,
  monthly_contribution_krw: 0,
  drawdown_tolerance_pct: 20,
  max_position_weight_pct: 20,
  max_crypto_weight_pct: 30,
  max_total_risk_pct: 8,
  rebalance_band_pt: 5,
  target_stock_pct: 80,
  target_crypto_pct: 20,
  target_cash_pct: 0,
}
const unset: CoachPolicy = {
  policy: defaults,
  cash: null,
  defaults,
  warnings: [],
  updated_at: null,
  cash_stale: false,
  policy_set: false,
}
const killOff: RuleCheckAll['kill_switch'] = { tripped: false, reason_code: null, detail: '', since: null }
const killOn: RuleCheckAll['kill_switch'] = {
  tripped: true,
  reason_code: 'daily_loss',
  detail: '일일 손실 한도 초과',
  since: '2026-10-20T03:00:00',
}

const emptyDiagnosis: CoachDiagnosis = {
  as_of: '2026-10-16',
  empty: true,
  policy_set: false,
  policy: defaults,
  equity_krw: 0,
  invested_krw: 0,
  cash_krw: null,
  cash_as_of: null,
  cash_stale: false,
  usd_krw: 1350,
  weights: [],
  concentration: null,
  exposure: null,
  risk: { windows: [], actual: null, actual_error: null },
  correlation: null,
  betas: [],
  total_risk_pct_equity: null,
  violations: [],
  required_annual_return_pct: null,
  goal_years: null,
  caveats: [],
  checked_at: '2026-10-16T01:00:00',
}

const diagnosis: CoachDiagnosis = {
  ...emptyDiagnosis,
  empty: false,
  policy_set: true,
  equity_krw: 40_000_000,
  invested_krw: 40_000_000,
  weights: [
    { symbol: 'AAA', asset_class: 'stock', currency: 'USD', value_krw: 28_000_000, weight_pct: 70, invested_weight_pct: 70, target_pct: null, cap_pct: 20 },
    { symbol: 'BBB-USD', asset_class: 'crypto', currency: 'KRW', value_krw: 12_000_000, weight_pct: 30, invested_weight_pct: 30, target_pct: null, cap_pct: 20 },
  ],
  concentration: { count: 2, top1_symbol: 'AAA', top1_pct: 70, top3_pct: 100, hhi: 0.58, effective_n: 1.7 },
  exposure: { equity_krw: 40_000_000, invested_krw: 40_000_000, stock_pct: 70, crypto_pct: 30, cash_pct: null, usd_pct: 70 },
  risk: {
    windows: [
      {
        name: '1y', grid: 'stock', periods_per_year: 252, rows: 250, start: '2025-10-16', end: '2026-10-16',
        annual_vol_pct: 25, swing_1sigma_krw: 10_000_000, max_drawdown_pct: 12.5, drawdown_peak: null, drawdown_trough: null,
        coverage_pct: 100, included: ['AAA', 'BBB-USD'], excluded: [], method: 'ledoit_wolf', usable: true, reason: null, peak_at_window_start: false,
      },
      {
        name: '3y', grid: 'stock', periods_per_year: 252, rows: 740, start: '2023-10-16', end: '2026-10-16',
        annual_vol_pct: 27, swing_1sigma_krw: 10_800_000, max_drawdown_pct: 31.4, drawdown_peak: null, drawdown_trough: null,
        coverage_pct: 100, included: ['AAA', 'BBB-USD'], excluded: [], method: 'ledoit_wolf', usable: true, reason: null, peak_at_window_start: false,
      },
    ],
    actual: {
      since: '2026-01-05', points: 285, twr_max_drawdown_pct: 9.1, current_drawdown_pct: 2.2,
      daily_loss_breaches_1y: 1, drawdown_breaches_1y: 0, limit_drawdown_pct: 20, limit_daily_loss_pct: 3,
    },
    actual_error: null,
  },
  correlation: { symbols: ['AAA', 'BBB-USD'], matrix: [[1, 0.42], [0.42, 1]], method: 'ledoit_wolf', rows: 740, excluded: [] },
  betas: [{ symbol: 'AAA', benchmark: 'SPY', window: '1y', beta: 1.1, r2: 0.5, rows: 250, reason: null }],
  total_risk_pct_equity: 6.5,
  violations: [
    { code: 'position_over_cap', severity: 'warn', label_ko: '종목 비중 상한 초과', detail: 'AAA 비중 70.0%가 상한 20%를 넘음', value: 70, limit: 20, subject: 'AAA' },
    { code: 'cash_missing', severity: 'info', label_ko: '현금 미입력', detail: '현금을 적지 않아 투자금 기준으로 계산했습니다', value: null, limit: null, subject: null },
  ],
  caveats: ['과거 데이터로 추정한 값이며, 과거는 미래를 보장하지 않습니다.'],
}

const rebalance: CoachRebalance = {
  empty: false,
  equity_krw: 40_000_000,
  cash_known: false,
  band_pt: 5,
  class_targets: { stock: 80, crypto: 20, cash: null },
  unallocated_pct: 0,
  targets: [
    { symbol: 'AAA', asset_class: 'stock', current_pct: 70, target_pct: 20, drift_pt: 50, source: 'remainder', capped: true },
    { symbol: 'BBB-USD', asset_class: 'crypto', current_pct: 30, target_pct: 20, drift_pt: 10, source: 'remainder', capped: false },
  ],
  orders: [
    {
      symbol: 'AAA', side: 'sell', requested_krw: 20_000_000, allowed_krw: 20_000_000, status: 'accepted', reasons: [], labels: [],
      approx_qty: 49.38, price: 300, currency: 'USD', price_krw: 405_000, realized_pnl_krw_if_sold: 3_000_000,
    },
    {
      symbol: 'BBB-USD', side: 'sell', requested_krw: 4_000_000, allowed_krw: 4_000_000, status: 'accepted', reasons: [], labels: [],
      approx_qty: 0.05, price: 80_000_000, currency: 'KRW', price_krw: 80_000_000, realized_pnl_krw_if_sold: -500_000,
    },
  ],
  after: { weights: [{ symbol: 'AAA', weight_pct: 20 }, { symbol: 'BBB-USD', weight_pct: 20 }], cash_krw: 24_000_000, cash_pct: null },
  notes: ['현금 기록이 없어 매도 대금 범위에서만 매수를 계산했습니다'],
  headline_ko: '내 정책과 지금 비중의 차이예요. 예측이 아니고, 주문은 내지 않습니다.',
  disclaimer_ko: '투자 조언이 아닙니다. 수수료·세금 미포함.',
}

const patterns: CoachPatterns = {
  empty: false,
  window_start: '2025-10-16',
  window_end: '2026-10-16',
  trades_considered: 5,
  trades_without_bars: 0,
  patterns: [
    {
      code: 'chasing_buy', label_ko: '급등 뒤 매수', count: 1, detail: '매수 전 20봉 동안 15% 넘게 움직인 뒤 산 거래', months: [],
      trades: [{ code: 'chasing_buy', label_ko: '급등 뒤 매수', trade_id: 7, symbol: 'AAA', date: '2026-03-03', detail: '매수 전 20봉 동안 +17.9% 움직인 뒤 샀습니다', value: 17.9 }],
    },
    { code: 'averaging_down_below_cut', label_ko: '손절선 아래 물타기', count: 0, detail: '평균단가 기준 손절선 아래에서 추가로 산 거래', trades: [], months: [] },
    { code: 'quick_rebuy_after_loss', label_ko: '손실 매도 뒤 재매수', count: 0, detail: '손실로 판 뒤 10일 안에 같은 종목을 다시 산 거래', trades: [], months: [] },
    { code: 'overtrading', label_ko: '거래 횟수 급증', count: 1, detail: '직전 12개월 평균의 2배를 넘고 6건 이상 거래한 달', trades: [], months: ['2026-03'] },
  ],
  monthly: [{ month: '2026-03', buys: 6, sells: 1, total: 7 }, { month: '2026-04', buys: 0, sells: 0, total: 0 }],
  rule_lag: [],
  caveats: ['거래 기록에서 집계한 패턴이며, 예측이나 신호가 아닙니다.'],
}

const review: CoachReview = {
  empty: false,
  month: '2026-10',
  start: '2026-09-30',
  end: '2026-10-16',
  start_point: '2026-09-30',
  end_point: '2026-10-16',
  start_value_krw: 38_000_000,
  end_value_krw: 40_000_000,
  change_krw: 2_000_000,
  contributions_krw: 1_000_000,
  market_pnl_krw: 1_000_000,
  realized_pnl_krw: -200_000,
  dividends_krw: 0,
  benchmarks: [
    { symbol: 'SPY', name_ko: 'S&P 500 ETF', start_value_krw: 38_000_000, end_value_krw: 39_500_000, change_krw: 1_500_000, excess_krw: 500_000 },
    { symbol: 'BTC-USD', name_ko: '비트코인', start_value_krw: 38_000_000, end_value_krw: 41_000_000, change_krw: 3_000_000, excess_krw: -1_000_000 },
  ],
  trades: { buys: 2, sells: 1 },
  flagged_trades: [],
  flags_counted: true,
  suspicious_trades: 0,
  violations_now: 1,
  months_available: ['2026-10', '2026-09'],
  caveats: ['벤치마크는 같은 날 같은 돈을 넣었을 때의 값이며, 배당은 양쪽 모두 빠져 있습니다.'],
}

/** The rendered element has no gain/loss class and no arrow next to it. */
function expectUncoloured(el: HTMLElement) {
  expect(el.className).not.toMatch(/text-(gain|loss)/)
  expect(el.textContent).not.toMatch(/[▲▼]/)
}

type Q<T> = { data?: T; error?: unknown; isFetching?: boolean }
const state: {
  policy: CoachPolicy
  check: Partial<RuleCheckAll> | undefined
  diagnosis: Q<CoachDiagnosis>
  rebalance: Q<CoachRebalance>
  patterns: Q<CoachPatterns>
  review: Q<CoachReview>
  reviewMonth?: string
} = { policy: unset, check: undefined, diagnosis: {}, rebalance: {}, patterns: {}, review: {} }
const save = vi.fn(async (body: CoachPolicyInput) => body)
const reset = vi.fn()

vi.mock('../api/hooks', () => ({
  useCoachPolicy: () => ({ data: state.policy, error: null }),
  useUpdateCoachPolicy: () => ({ mutateAsync: save, isPending: false, isSuccess: false, data: undefined, error: null }),
  useRuleCheck: () => ({ data: state.check }),
  useResetKillSwitch: () => ({ mutate: reset, isPending: false, error: null }),
  useCoachDiagnosis: () => state.diagnosis,
  useCoachRebalance: () => state.rebalance,
  useCoachPatterns: () => state.patterns,
  useCoachReview: (month?: string) => {
    state.reviewMonth = month
    return state.review
  },
}))

const renderPage = () =>
  render(
    <CurrencyProvider>
      <MemoryRouter>
        <Coach />
      </MemoryRouter>
    </CurrencyProvider>,
  )

const field = (label: string) => screen.getByLabelText(label) as HTMLInputElement
const type = (label: string, value: string) => fireEvent.change(field(label), { target: { value } })
const submit = () => fireEvent.submit(screen.getByRole('button', { name: '저장' }).closest('form')!)

function resetState() {
  save.mockClear()
  reset.mockClear()
  state.policy = unset
  state.check = { kill_switch: killOff, live_trading: false }
  state.diagnosis = { data: emptyDiagnosis }
  state.rebalance = { data: { ...rebalance, empty: true } }
  state.patterns = { data: { ...patterns, empty: true } }
  state.review = { data: { ...review, empty: true } }
}

describe('Coach page: policy form', () => {
  beforeEach(resetState)
  afterEach(cleanup)

  it('shows the defaults with the intro, the "not saved yet" note, the cash note and the disclaimer', () => {
    renderPage()
    expect(screen.getByRole('heading', { name: '포트폴리오 코치' })).toBeInTheDocument()
    expect(screen.getByText(/예측·종목 추천·투자 조언이 아니며/)).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('기본값을 보여 줍니다')
    expect(field('종목 하나의 비중 상한 (%)')).toHaveValue('20')
    expect(field('주식 목표 비중 (%)')).toHaveValue('80')
    expect(field('목표 금액 (만원)')).toHaveValue('')
    expect(screen.getByText(/합 100%/)).toBeInTheDocument()
    expect(screen.getByText(/현금은 이 앱이 알 수 없어 직접 적습니다/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '규칙 페이지에서' })).toHaveAttribute('href', '/rules')
    expect(screen.getByText('투자 조언이 아닙니다. 수수료·세금 미포함.')).toBeInTheDocument()
    // Real trading is shown read-only, and off.
    expect(screen.getByText('실매매 꺼짐')).toBeInTheDocument()
    expect(screen.getByText('킬스위치 꺼짐')).toBeInTheDocument()
  })

  it('refuses asset-class targets that do not add up to 100 before calling the API', () => {
    renderPage()
    type('주식 목표 비중 (%)', '90')
    expect(screen.getByText(/합 110%/)).toHaveTextContent('100이어야 합니다')
    submit()
    expect(save).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent('합이 100이어야 합니다 (지금 110%)')
  })

  it('sends every number as a string, 만원 amounts as won, and the cash record', async () => {
    renderPage()
    type('목표 금액 (만원)', '1000')
    type('목표일', '2030-01-01')
    type('월 적립 (만원)', '30.5')
    type('견딜 수 있는 최대 낙폭 (%)', '15')
    type('주식 목표 비중 (%)', '60')
    type('현금 목표 비중 (%)', '20')
    type('원화 현금 (원)', '1500000')
    type('현금 기준일', '2026-10-20')
    submit()
    await vi.waitFor(() => expect(save).toHaveBeenCalledTimes(1))
    expect(save.mock.calls[0][0]).toEqual({
      policy: {
        goal_krw: '10000000',
        goal_date: '2030-01-01',
        monthly_contribution_krw: '305000',
        drawdown_tolerance_pct: '15',
        max_position_weight_pct: '20',
        max_crypto_weight_pct: '30',
        max_total_risk_pct: '8',
        rebalance_band_pt: '5',
        target_stock_pct: '60',
        target_crypto_pct: '20',
        target_cash_pct: '20',
      },
      cash: { krw: '1500000', usd: '0', as_of: '2026-10-20' },
    })
  })

  it('fills the defaults on reset without saving, and shows the stored policy otherwise', () => {
    state.policy = {
      ...unset,
      policy: { ...defaults, max_position_weight_pct: 12.5, goal_krw: 50_000_000, goal_date: '2030-01-01' },
      cash: { krw: 100, usd: 0, as_of: '2026-08-01' },
      cash_stale: true,
      updated_at: '2026-10-25T01:02:03',
      policy_set: true,
    }
    renderPage()
    expect(screen.queryByText(/기본값을 보여 줍니다/)).not.toBeInTheDocument()
    expect(field('종목 하나의 비중 상한 (%)')).toHaveValue('12.5')
    expect(field('목표 금액 (만원)')).toHaveValue('5000')
    expect(screen.getByText(/현금 기준일이 30일 넘게 지났습니다/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '기본값으로 되돌리기' }))
    expect(field('종목 하나의 비중 상한 (%)')).toHaveValue('20')
    expect(field('목표 금액 (만원)')).toHaveValue('')
    // The cash record is the user's data and stays.
    expect(field('원화 현금 (원)')).toHaveValue('100')
    expect(screen.getByText(/저장을 눌러야 적용됩니다/)).toBeInTheDocument()
    expect(save).not.toHaveBeenCalled()
  })
})

describe('Coach page: kill switch', () => {
  beforeEach(resetState)
  afterEach(cleanup)

  it('has no reset button while the switch is off', () => {
    renderPage()
    expect(screen.getByText('킬스위치 꺼짐')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '해제' })).not.toBeInTheDocument()
  })

  it('asks twice inline before resetting a tripped switch, and can be cancelled', () => {
    state.check = { kill_switch: killOn, live_trading: false }
    renderPage()
    expect(screen.getByText('킬스위치 켜짐')).toBeInTheDocument()
    expect(screen.getByText(/일일 손실 한도 초과/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '해제' }))
    const confirm = screen.getByRole('group', { name: '킬스위치 해제 확인' })
    expect(confirm).toHaveTextContent('정말 해제할까요?')
    fireEvent.click(within(confirm).getByRole('button', { name: '취소' }))
    expect(reset).not.toHaveBeenCalled()
    expect(screen.queryByRole('group', { name: '킬스위치 해제 확인' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '해제' }))
    fireEvent.click(screen.getByRole('button', { name: '해제 확인' }))
    expect(reset).toHaveBeenCalledTimes(1)
    // No actor and no detail from the screen: the server fixes the actor.
    expect(reset.mock.calls[0][0]).toBeUndefined()
  })

  it('shows real trading as on when the server says so, without a way to change it', () => {
    state.check = { kill_switch: killOff, live_trading: true }
    renderPage()
    expect(screen.getByText('실매매 켜짐')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /실매매/ })).not.toBeInTheDocument()
  })
})

describe('Coach page: checks', () => {
  beforeEach(resetState)
  afterEach(cleanup)

  it('says there is nothing to check without holdings, in every section', () => {
    renderPage()
    expect(screen.getAllByText('보유 종목이 없어 점검할 것이 없어요.')).toHaveLength(3)
    expect(screen.getByText('거래 기록이 없어 돌아볼 달이 없어요.')).toBeInTheDocument()
    expect(screen.queryByText('체크리스트')).not.toBeInTheDocument()
  })

  it('shows skeletons while loading and the error when a section fails', () => {
    state.diagnosis = {}
    state.rebalance = { error: new Error('시세를 받지 못했습니다') }
    renderPage()
    expect(screen.getByRole('alert')).toHaveTextContent('시세를 받지 못했습니다')
    expect(screen.queryByText(/정책 위반/)).not.toBeInTheDocument()
  })

  it('renders the diagnosis tiles, violations, past-window phrases, checklists and the missing-cash note', () => {
    state.diagnosis = { data: diagnosis }
    state.check = { kill_switch: killOff, live_trading: false, checks: [{ status: 'cut' }] } as unknown as RuleCheckAll
    renderPage()
    expect(screen.getByText('총자산')).toBeInTheDocument()
    expect(screen.getByText(/현금 미입력 · 투자금만/)).toBeInTheDocument()
    expect(screen.getByText('1.7개')).toBeInTheDocument()
    expect(screen.getByText('±1,000만원')).toBeInTheDocument()
    expect(screen.getByText(/10번 중 7번 안/)).toBeInTheDocument()
    expect(screen.getByText('−31.4%')).toBeInTheDocument()
    expect(screen.getByText(/견딜 수 있다고 적은 값은 −20%이고, 그보다 깊어요/)).toBeInTheDocument()
    expect(screen.getByText('정책 위반 1건')).toBeInTheDocument()
    expect(screen.getByText(/AAA 비중 70.0%가 상한 20%를 넘음/)).toBeInTheDocument()
    expect(screen.getByText(/참고 · 현금 미입력/)).toBeInTheDocument()
    // Past-window figures carry no arrow.
    expect(screen.getByText('−31.4%').textContent).not.toMatch(/[▲▼]/)
    expect(screen.getByText(/과거는 미래를 보장하지 않습니다/)).toBeInTheDocument()
    // Correlation table with the number in every cell, beta sentence, actual drawdown.
    const table = screen.getByRole('table', { name: '종목 간 상관' })
    expect(within(table).getAllByText('0.42')).toHaveLength(2) // symmetric, a number in every cell
    expect(screen.getByText(/SPY가 1% 움직일 때 평균 1.10% 움직였어요/)).toBeInTheDocument()
    expect(screen.getByText('−9.1%')).toBeInTheDocument()
    expect(screen.getByText(/지금 고점 대비 −2.2% · 허용 −20%/)).toBeInTheDocument()
    // Checklists built from the diagnosis and the rule check.
    expect(screen.getByText('사기 전에')).toBeInTheDocument()
    expect(screen.getByText('손실 중일 때')).toBeInTheDocument()
    expect(screen.getByText(/손절 검토 1종목/)).toBeInTheDocument()
    expect(screen.getByText(/판단 크기를 줄이는 것은 일반 원칙입니다/)).toBeInTheDocument()
    expect(screen.getByText(/현금을 적지 않아 확인할 수 없어요/)).toBeInTheDocument()
  })

  it('shows the server reason, as a note, when the real curve was not computed', () => {
    const reason = '단가 확인이 필요한 거래 1건(AAA)이 있어 실제 추이의 낙폭을 계산하지 않았습니다. 거래 페이지에서 단가를 고치면 계산됩니다.'
    state.diagnosis = { data: { ...diagnosis, risk: { ...diagnosis.risk, actual: null, actual_error: reason } } }
    state.check = { kill_switch: killOff, live_trading: false, checks: [] } as unknown as RuleCheckAll
    renderPage()
    // Once in the "실제 추이의 낙폭" disclosure, once in the in-loss checklist.
    expect(screen.getAllByText(reason)).toHaveLength(2)
    expect(screen.getByText(/참고 · 낙폭 vs 허용 낙폭/)).toBeInTheDocument()
    expect(screen.queryByText(/지금 고점 대비/)).not.toBeInTheDocument()
    expect(screen.queryByText('−9.1%')).not.toBeInTheDocument()
  })

  it('renders the rebalance table with 줄이기 wording, blocked reasons and the headline', () => {
    state.rebalance = { data: rebalance }
    renderPage()
    expect(screen.getByText('내 정책과 지금 비중의 차이예요. 예측이 아니고, 주문은 내지 않습니다.')).toBeInTheDocument()
    expect(screen.getByText('줄이기 2,000만원 · 약 49.38주')).toBeInTheDocument()
    expect(screen.getByText('줄이기 400만원 · 약 0.05개')).toBeInTheDocument()
    // "If sold" P&L is an assumption: sign only, no colour, no arrow (N-COACH-3).
    expectUncoloured(screen.getByText('+3,000,000원'))
    expectUncoloured(screen.getByText('−500,000원'))
    expect(screen.getByText('상한 적용')).toBeInTheDocument()
    expect(screen.getByText(/현금 기록이 없어 매도 대금 범위에서만/)).toBeInTheDocument()
    expect(screen.getByText(/남는 매도 대금 2,400만원/)).toBeInTheDocument()
    expect(screen.getAllByText('투자 조언이 아닙니다. 수수료·세금 미포함.').length).toBeGreaterThanOrEqual(2)
    expect(document.body.textContent).not.toMatch(/사세요|파세요|추천해/)
  })

  it('renders the habit counts with their trades and the busiest month', () => {
    state.patterns = { data: patterns }
    renderPage()
    // Both ends of the window in the same format, year included.
    expect(screen.getByText(/2025년 10월 16일부터 2026년 10월 16일까지 거래 5건을 봤어요/)).toBeInTheDocument()
    expect(screen.getByText('급등 뒤 매수 1건')).toBeInTheDocument()
    expect(screen.getByText('손실 매도 뒤 재매수 0건')).toBeInTheDocument()
    expect(screen.getByText('거래 횟수 급증 1건')).toBeInTheDocument()
    expect(screen.getByText('2026년 3월')).toBeInTheDocument()
    expect(screen.getByText(/가장 많이 거래한 달은 2026년 3월 7건/)).toBeInTheDocument()
    expect(screen.getByText(/매수 전 20봉 동안 \+17.9% 움직인 뒤 샀습니다/)).toBeInTheDocument()
    expect(screen.getByText('손절선 아래 보유 지속 0종목')).toBeInTheDocument()
  })

  it('marks a stop-loss lag that fills the whole loaded range as a lower bound', () => {
    state.patterns = {
      data: {
        ...patterns,
        rule_lag: [
          { symbol: 'AAA', currency: 'USD', cut_price: 120, days: 12, since: '2026-09-01', last_close: 100, since_window_start: false },
          { symbol: 'BBB-USD', currency: 'KRW', cut_price: 60_000_000, days: 282, since: '2025-09-01', last_close: 50_000_000, since_window_start: true },
        ],
      },
    }
    renderPage()
    expect(screen.getByText('손절선 아래 보유 지속 2종목')).toBeInTheDocument()
    expect(screen.getByText('AAA: 2026년 9월 1일부터 12봉째 손절 검토 가격 아래 ($120.00)')).toBeInTheDocument()
    expect(screen.getByText('BBB: 2025년 9월 1일부터 282봉 이상 (조회 범위 처음부터) 손절 검토 가격 아래 (60,000,000원)')).toBeInTheDocument()
  })

  it('renders the monthly review with a month picker and coloured realized figures only', () => {
    state.review = { data: review }
    renderPage()
    expect(screen.getByText(/2026년 10월 \(/)).toBeInTheDocument()
    // The headline count says which checks it comes from (weights and exposure only).
    expect(screen.getByText(/지금 비중·자산군 위반 1건/)).toBeInTheDocument()
    expect(screen.queryByText(/지금 정책 위반/)).not.toBeInTheDocument()
    expect(screen.getByText('= 넣은 돈 (매수 − 매도)')).toBeInTheDocument()
    const market = screen.getByText('+1,000,000원') // market P&L, red with ▲ beside it
    expect(market.className).toContain('text-gain')
    expect(market.textContent).toMatch(/▲/)
    expect(screen.getByText('−200,000원')).toBeInTheDocument()
    expect(screen.getByText('S&P 500 ETF 대비')).toBeInTheDocument()
    expect(screen.getByText('−1,000,000원')).toBeInTheDocument()
    expect(screen.getByText('습관 점검에 걸린 거래 0건')).toBeInTheDocument()
    expect(screen.getByText('이 달에는 없어요.')).toBeInTheDocument()
    const picker = screen.getByRole('combobox', { name: '달 선택' })
    expect(picker).toHaveValue('2026-10')
    fireEvent.change(picker, { target: { value: '2026-09' } })
    expect(state.reviewMonth).toBe('2026-09')
  })

  it('drops the gain/loss colour from the deposit split while a mis-priced trade is inside the month', () => {
    const caveat = '넣은 돈·시장 손익에 단가 확인이 필요한 거래 1건이 들어 있어 값이 왜곡될 수 있습니다.'
    state.review = { data: { ...review, suspicious_trades: 1, caveats: [caveat, ...review.caveats] } }
    renderPage()
    expect(screen.getByText(caveat)).toBeInTheDocument()
    // Market result and the benchmark excess: sign only. Realized P&L is ledger fact and stays coloured.
    expectUncoloured(screen.getByText('+1,000,000원'))
    expectUncoloured(screen.getByText('+500,000원'))
    expectUncoloured(screen.getByText('−1,000,000원'))
    expect(screen.getByText('−200,000원').className).toContain('text-loss')
  })

  it('says the habit flags were not counted for a month before the one-year window', () => {
    const caveat = '습관 점검은 최근 1년 거래만 보므로 이 달의 플래그는 세지 않았습니다.'
    state.review = { data: { ...review, month: '2025-06', flags_counted: false, caveats: [caveat, ...review.caveats] } }
    renderPage()
    expect(screen.getByText('습관 점검에 걸린 거래 집계 안 함')).toBeInTheDocument()
    expect(screen.getByText(caveat)).toBeInTheDocument()
    expect(screen.queryByText(/습관 점검에 걸린 거래 0건/)).not.toBeInTheDocument()
    expect(screen.queryByText('이 달에는 없어요.')).not.toBeInTheDocument()
  })
})
