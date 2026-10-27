import { describe, expect, it } from 'vitest'

import type { CoachDiagnosis, CoachLagFlag, CoachOrder, CoachRiskWindow, RuleCheckAll } from '../api/client'
import {
  ACTUAL_CURVE_SHORT_KO,
  actualCurveNote,
  betaPhrase,
  coachSummary,
  drawdownPhrase,
  FLAGS_NOT_COUNTED_KO,
  fullDate,
  inLossChecklist,
  lagPhrase,
  monthLabel,
  patternPhrase,
  preBuyChecklist,
  rebalanceActionPhrase,
  requiredReturnPhrase,
  reviewViolationsLabel,
  signedKrw,
  SMALLER_DECISIONS_KO,
  swingPhrase,
  violationTone,
  windowLabel,
  windowSpanPhrase,
} from './coach'

// Synthetic values only (public repo).
const window1y: CoachRiskWindow = {
  name: '1y',
  grid: 'stock',
  periods_per_year: 252,
  rows: 250,
  start: '2025-10-16',
  end: '2026-10-16',
  annual_vol_pct: 24.5,
  swing_1sigma_krw: 12_340_000,
  max_drawdown_pct: 18.2,
  drawdown_peak: '2026-02-01',
  drawdown_trough: '2026-04-01',
  coverage_pct: 100,
  included: ['AAA', 'BBB'],
  excluded: [],
  method: 'ledoit_wolf',
  usable: true,
  reason: null,
  peak_at_window_start: false,
}
const unusable: CoachRiskWindow = { ...window1y, name: '3y', usable: false, reason: '겹치는 날이 80일로 120일보다 적습니다' }

const diagnosis: CoachDiagnosis = {
  as_of: '2026-10-16',
  empty: false,
  policy_set: true,
  policy: {
    goal_krw: 100_000_000,
    goal_date: '2036-10-16',
    monthly_contribution_krw: 500_000,
    drawdown_tolerance_pct: 15,
    max_position_weight_pct: 20,
    max_crypto_weight_pct: 30,
    max_total_risk_pct: 8,
    rebalance_band_pt: 5,
    target_stock_pct: 60,
    target_crypto_pct: 20,
    target_cash_pct: 20,
  },
  equity_krw: 50_000_000,
  invested_krw: 40_000_000,
  cash_krw: 10_000_000,
  cash_as_of: '2026-10-10',
  cash_stale: false,
  usd_krw: 1350,
  weights: [
    { symbol: 'AAA', asset_class: 'stock', currency: 'USD', value_krw: 25_000_000, weight_pct: 50, invested_weight_pct: 62.5, target_pct: null, cap_pct: 20 },
    { symbol: 'BBB-USD', asset_class: 'crypto', currency: 'KRW', value_krw: 15_000_000, weight_pct: 30, invested_weight_pct: 37.5, target_pct: null, cap_pct: 20 },
  ],
  concentration: { count: 2, top1_symbol: 'AAA', top1_pct: 62.5, top3_pct: 100, hhi: 0.53, effective_n: 1.9 },
  exposure: { equity_krw: 50_000_000, invested_krw: 40_000_000, stock_pct: 50, crypto_pct: 30, cash_pct: 20, usd_pct: 50 },
  risk: {
    windows: [window1y, unusable],
    actual: {
      since: '2026-01-05',
      points: 285,
      twr_max_drawdown_pct: 22.4,
      current_drawdown_pct: 16.5,
      daily_loss_breaches_1y: 2,
      drawdown_breaches_1y: 1,
      limit_drawdown_pct: 20,
      limit_daily_loss_pct: 3,
    },
    actual_error: null,
  },
  correlation: { symbols: ['AAA', 'BBB-USD'], matrix: [[1, 0.3], [0.3, 1]], method: 'ledoit_wolf', rows: 250, excluded: [] },
  betas: [{ symbol: 'AAA', benchmark: 'SPY', window: '1y', beta: 1.2, r2: 0.45, rows: 250, reason: null }],
  total_risk_pct_equity: 9.5,
  violations: [
    { code: 'position_over_cap', severity: 'warn', label_ko: '종목 비중 상한 초과', detail: 'AAA 비중 50.0%가 상한 20%를 넘음', value: 50, limit: 20, subject: 'AAA' },
    { code: 'cash_stale', severity: 'info', label_ko: '현금 기준일 오래됨', detail: '', value: 40, limit: 30, subject: null },
  ],
  required_annual_return_pct: 4.2,
  goal_years: 10,
  caveats: [],
  checked_at: '2026-10-16T01:00:00',
}

const rules = {
  checks: [{ status: 'cut' }, { status: 'hold' }],
  kill_switch: { tripped: false, reason_code: null, detail: '', since: null },
} as unknown as RuleCheckAll

const BANNED = /추천|사세요|파세요|오를|예상 수익/

describe('diagnosis wording', () => {
  it('names the window and the won swing without a gain/loss cue', () => {
    expect(windowLabel('1y')).toBe('1년')
    const swing = swingPhrase(window1y)
    expect(swing.value).toBe('±1,234만원')
    expect(swing.text).toContain('10번 중 7번 안')
    expect(swing.text).toContain('지난 1년 기준')
    expect(swing.value).not.toMatch(/[▲▼]/)
    expect(swingPhrase(unusable).usable).toBe(false)
    expect(swingPhrase(unusable).text).toContain('겹치는 날이 80일')
    expect(swingPhrase(undefined).value).toBe('—')
  })

  it('puts the past drawdown beside the tolerance the user wrote', () => {
    const over = drawdownPhrase(window1y, 15)
    expect(over.value).toBe('−18.2%')
    expect(over.over).toBe(true)
    expect(over.text).toContain('지난 1년을 지났다면')
    expect(over.text).toContain('−15%')
    expect(over.text).toContain('고점 ')
    expect(over.text).toContain('→ 저점 ')
    expect(drawdownPhrase(window1y, 25).over).toBe(false)
    expect(drawdownPhrase(unusable, 15).over).toBeNull()
    // The window opened at the peak: no peak date, so the span starts at the window.
    const fromStart = drawdownPhrase({ ...window1y, drawdown_peak: null, peak_at_window_start: true }, 15)
    expect(fromStart.text).toContain('창 시작부터')
    expect(fromStart.text).not.toContain('고점')
    expect(drawdownPhrase({ ...window1y, drawdown_peak: null, drawdown_trough: null }, 15).text).not.toContain('(')
  })

  it('tones violations by severity and summarises for the home card', () => {
    expect(violationTone('warn')).toContain('text-danger')
    expect(violationTone('info')).toContain('text-ink-2')
    expect(coachSummary(diagnosis)).toBe('정책 위반 1건 · 코인 비중 30% →')
    expect(coachSummary({ ...diagnosis, cash_krw: null })).toBe('정책 위반 1건 · 코인 비중 30% · 현금 미입력 →')
    expect(coachSummary({ ...diagnosis, policy_set: false })).toBe('정책을 아직 정하지 않았어요 →')
    expect(coachSummary({ ...diagnosis, empty: true })).toBeUndefined()
    // Nothing held: hidden even before a policy is saved (N-COACH-4).
    expect(coachSummary({ ...diagnosis, empty: true, policy_set: false })).toBeUndefined()
    expect(coachSummary(undefined)).toBeUndefined()
  })

  it('shows why the real curve is missing, verbatim, as a note', () => {
    const reason = '단가 확인이 필요한 거래 2건(AAA, BBB)이 있어 실제 추이의 낙폭을 계산하지 않았습니다. 거래 페이지에서 단가를 고치면 계산됩니다.'
    const withoutCurve: CoachDiagnosis = { ...diagnosis, risk: { ...diagnosis.risk, actual: null, actual_error: reason } }
    expect(actualCurveNote(withoutCurve)).toBe(reason)
    expect(actualCurveNote({ risk: { windows: [], actual: null, actual_error: null } })).toBe(ACTUAL_CURVE_SHORT_KO)
    const item = inLossChecklist(withoutCurve, rules)[1]
    expect(item).toEqual({ label: '낙폭 vs 허용 낙폭', state: 'info', detail: reason })
    // No figure is shown, so no pass/fail either.
    expect(item.detail).not.toMatch(/%/)
  })

  it('reads beta and the goal arithmetic as plain sentences', () => {
    expect(betaPhrase(diagnosis.betas[0])).toBe('SPY가 1% 움직일 때 평균 1.20% 움직였어요 (250일, 설명력 45%, 지난 1년)')
    expect(betaPhrase({ ...diagnosis.betas[0], beta: null, r2: null, rows: 0, reason: '겹치는 날이 적음' })).toContain('계산하지 못했어요')
    expect(requiredReturnPhrase(diagnosis)).toBe('목표까지 10.0년 · 해마다 4.2% 수익이 필요해요 (산수이지 예측이 아닙니다).')
    expect(requiredReturnPhrase({ goal_years: null, required_annual_return_pct: null })).toBeUndefined()
    expect(requiredReturnPhrase({ goal_years: 10, required_annual_return_pct: null })).toContain('계산하지 않았어요')
    expect(requiredReturnPhrase({ goal_years: -1, required_annual_return_pct: null })).toContain('목표일이 지났어요')
  })
})

describe('checklists', () => {
  it('builds the pre-buy list from caps, the stop total, cash and the switch', () => {
    const items = preBuyChecklist(diagnosis, rules)
    expect(items.map((i) => [i.label, i.state])).toEqual([
      ['종목 상한까지 여유', 'warn'],
      ['손절 시 손실 vs 한도', 'warn'],
      // Exactly at the coin cap: no room left, so this is a warning too.
      ['코인 상한까지 여유', 'warn'],
      ['현금 여유', 'ok'],
      ['킬스위치', 'ok'],
    ])
    expect(items[0].detail).toBe('가장 큰 종목 AAA 50.0% · 상한 20% · 여유 −30%p')
    expect(items[2].detail).toBe('코인 합산 30.0% · 상한 30% · 여유 0%p')
    expect(preBuyChecklist({ ...diagnosis, exposure: { ...diagnosis.exposure!, crypto_pct: 10 } }, rules)[2]).toMatchObject({ state: 'ok' })
    expect(items[1].detail).toBe('모든 손절이 걸리면 총자산의 9.5% · 상한 8%')
    expect(items[3].detail).toContain('1,000만원')
    expect(preBuyChecklist({ ...diagnosis, cash_krw: null }, rules)[3]).toMatchObject({ state: 'info' })
    expect(preBuyChecklist({ ...diagnosis, total_risk_pct_equity: null }, undefined)[1]).toMatchObject({ state: 'info' })
    expect(preBuyChecklist(diagnosis, undefined)[4]).toMatchObject({ state: 'info' })
  })

  it('builds the in-loss list with the general principle, verbatim', () => {
    const items = inLossChecklist(diagnosis, rules)
    expect(items.map((i) => [i.label, i.state])).toEqual([
      ['발동한 내 규칙', 'warn'],
      ['낙폭 vs 허용 낙폭', 'warn'],
      ['킬스위치', 'ok'],
      ['판단 크기 줄이기', 'info'],
    ])
    expect(items[0].detail).toContain('손절 검토 1종목')
    expect(items[1].detail).toContain('−16.5%')
    expect(items[3].detail).toContain(SMALLER_DECISIONS_KO)
    const tripped = { ...rules, kill_switch: { ...rules.kill_switch, tripped: true, detail: '일일 손실' } }
    expect(inLossChecklist(diagnosis, tripped)[2]).toMatchObject({ state: 'warn' })
    expect(inLossChecklist({ ...diagnosis, risk: { ...diagnosis.risk, actual: null } }, rules)[1]).toMatchObject({ state: 'info' })
  })
})

describe('rebalancing and pattern wording', () => {
  const order: CoachOrder = {
    symbol: 'AAA',
    side: 'sell',
    requested_krw: 15_000_000,
    allowed_krw: 15_000_000,
    status: 'accepted',
    reasons: [],
    labels: [],
    approx_qty: 37.5,
    price: 300,
    currency: 'USD',
    price_krw: 405_000,
    realized_pnl_krw_if_sold: 2_000_000,
  }

  it('says 줄이기/늘리기 with the amount and rough quantity, and why a buy is blocked', () => {
    expect(rebalanceActionPhrase(order)).toBe('줄이기 1,500만원 · 약 37.5주')
    const buy: CoachOrder = { ...order, symbol: 'BBB-USD', side: 'buy', status: 'clipped', allowed_krw: 2_500_000, reasons: ['max_order_fraction'], labels: ['1회 주문 상한'], approx_qty: 0.0123 }
    expect(rebalanceActionPhrase(buy)).toBe('늘리기 250만원 · 약 0.0123개 (요청 1,500만원 중)')
    const blocked: CoachOrder = { ...buy, status: 'rejected', allowed_krw: 0, reasons: ['cash'], labels: ['현금 부족'], approx_qty: 0 }
    expect(rebalanceActionPhrase(blocked)).toBe('늘리기 막힘 (현금 부족)')
  })

  it('writes the hypothetical "if sold" P&L with its sign only, no arrow', () => {
    expect(signedKrw(2_000_000)).toBe('+2,000,000원')
    expect(signedKrw(-500_000)).toBe('−500,000원')
    expect(signedKrw(0)).toBe('0원')
    expect(signedKrw(1234.6)).toBe('+1,235원')
    expect(signedKrw(order.realized_pnl_krw_if_sold!)).not.toMatch(/[▲▼]/)
  })

  it('counts patterns and names months', () => {
    expect(patternPhrase({ label_ko: '급등 뒤 매수', count: 2 })).toBe('급등 뒤 매수 2건')
    expect(monthLabel('2026-10')).toBe('2026년 10월')
    expect(monthLabel('abc')).toBe('abc')
  })

  it('writes both ends of the habit window in one format, year included', () => {
    expect(fullDate('2025-10-27')).toBe('2025년 10월 27일')
    expect(fullDate('2026-01-05')).toBe('2026년 1월 5일')
    expect(fullDate('nonsense')).toBe('nonsense')
    expect(windowSpanPhrase('2025-10-27', '2026-10-27')).toBe('2025년 10월 27일부터 2026년 10월 27일까지')
  })

  it('reads a position below its stop with "이상" when the loaded bars were all below it', () => {
    const lag: CoachLagFlag = {
      symbol: 'AAA',
      currency: 'USD',
      cut_price: 120,
      days: 12,
      since: '2026-09-01',
      last_close: 100,
      since_window_start: false,
    }
    expect(lagPhrase(lag)).toBe('AAA: 2026년 9월 1일부터 12봉째 손절 검토 가격 아래 ($120.00)')
    expect(lagPhrase({ ...lag, since_window_start: true })).toBe(
      'AAA: 2026년 9월 1일부터 12봉 이상 (조회 범위 처음부터) 손절 검토 가격 아래 ($120.00)',
    )
    const won: CoachLagFlag = { ...lag, symbol: 'BBB-USD', currency: 'KRW', cut_price: 60_000_000, days: 282, since_window_start: true }
    expect(lagPhrase(won)).toContain('BBB: ')
    expect(lagPhrase(won)).toContain('282봉 이상')
    expect(lagPhrase(won)).toContain('(60,000,000원)')
  })

  it('names what the review headline counts', () => {
    expect(reviewViolationsLabel(3)).toBe('지금 비중·자산군 위반 3건')
    expect(reviewViolationsLabel(0)).toBe('지금 비중·자산군 위반 0건')
    expect(FLAGS_NOT_COUNTED_KO).toContain('최근 1년')
  })

  it('never uses the banned words in any generated sentence', () => {
    const lag: CoachLagFlag = { symbol: 'AAA', currency: 'USD', cut_price: 120, days: 12, since: '2026-09-01', last_close: 100, since_window_start: true }
    const sentences = [
      swingPhrase(window1y).text,
      drawdownPhrase(window1y, 15).text,
      betaPhrase(diagnosis.betas[0]),
      requiredReturnPhrase(diagnosis) ?? '',
      rebalanceActionPhrase(order),
      coachSummary(diagnosis) ?? '',
      signedKrw(-1),
      lagPhrase(lag),
      windowSpanPhrase('2025-10-27', '2026-10-27'),
      reviewViolationsLabel(1),
      FLAGS_NOT_COUNTED_KO,
      ACTUAL_CURVE_SHORT_KO,
      ...preBuyChecklist(diagnosis, rules).flatMap((i) => [i.label, i.detail]),
      ...inLossChecklist(diagnosis, rules).flatMap((i) => [i.label, i.detail]),
    ]
    for (const s of sentences) expect(s).not.toMatch(BANNED)
  })
})
