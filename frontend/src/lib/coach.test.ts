import { describe, expect, it } from 'vitest'

import type { CoachPolicy } from '../api/client'
import {
  CASH_LABELS_KO,
  CASH_NOTE_KO,
  COACH_FOOTER_KO,
  COACH_INTRO_KO,
  defaultsToForm,
  formToPolicyPayload,
  killSwitchChip,
  KILL_SWITCH_RESET_CONFIRM_KO,
  krwToManwon,
  liveTradingChip,
  manwonToKrw,
  POLICY_LABELS_KO,
  policyToForm,
  targetSum,
} from './coach'

// Synthetic policy only (public repo): nothing from a real account.
const fields: CoachPolicy['policy'] = {
  goal_krw: 50_000_000,
  goal_date: '2030-01-01',
  monthly_contribution_krw: 300_000,
  drawdown_tolerance_pct: 15,
  max_position_weight_pct: 12.5,
  max_crypto_weight_pct: 30,
  max_total_risk_pct: 8,
  rebalance_band_pt: 5,
  target_stock_pct: 60,
  target_crypto_pct: 20,
  target_cash_pct: 20,
}
const defaults: CoachPolicy['policy'] = {
  ...fields,
  goal_krw: null,
  goal_date: null,
  monthly_contribution_krw: 0,
  drawdown_tolerance_pct: 20,
  max_position_weight_pct: 20,
  target_stock_pct: 80,
  target_crypto_pct: 20,
  target_cash_pct: 0,
}
const stored: CoachPolicy = {
  policy: fields,
  cash: { krw: 1_500_000, usd: 200.5, as_of: '2026-10-20' },
  defaults,
  warnings: [],
  updated_at: '2026-10-25T01:02:03',
  cash_stale: false,
  policy_set: true,
}

describe('만원 conversion', () => {
  it('moves the decimal point four places without floating point', () => {
    expect(manwonToKrw('x', '1000')).toBe('10000000')
    expect(manwonToKrw('x', '1234.5')).toBe('12345000')
    expect(manwonToKrw('x', '0.0001')).toBe('1')
    expect(manwonToKrw('x', '0')).toBe('0')
    expect(manwonToKrw('x', '1,000')).toBe('10000000')
    expect(krwToManwon(12_345_000)).toBe('1234.5')
    expect(krwToManwon(null)).toBe('')
  })

  it('refuses negatives, text and sub-won fractions with the field named', () => {
    expect(() => manwonToKrw('목표 금액 (만원)', '-5')).toThrow('목표 금액 (만원): 0 이상의 숫자를 입력하세요')
    expect(() => manwonToKrw('목표 금액 (만원)', 'abc')).toThrow('숫자')
    expect(() => manwonToKrw('목표 금액 (만원)', '1.00001')).toThrow('원 단위')
  })
})

describe('form round trip', () => {
  it('shows the stored policy in 만원 and percent text, and the cash record', () => {
    const form = policyToForm(stored)
    expect(form.policy.goal_manwon).toBe('5000')
    expect(form.policy.goal_date).toBe('2030-01-01')
    expect(form.policy.monthly_manwon).toBe('30')
    expect(form.policy.max_position_weight_pct).toBe('12.5')
    expect(form.cash).toEqual({ krw: '1500000', usd: '200.5', as_of: '2026-10-20' })
  })

  it('fills the defaults but keeps the cash record the user typed', () => {
    const form = defaultsToForm(stored)
    expect(form.policy.goal_manwon).toBe('')
    expect(form.policy.target_stock_pct).toBe('80')
    expect(form.cash.krw).toBe('1500000')
  })

  it('builds a payload of strings, with won amounts and the cash record', () => {
    const body = formToPolicyPayload(policyToForm(stored))
    expect(body.policy).toEqual({
      goal_krw: '50000000',
      goal_date: '2030-01-01',
      monthly_contribution_krw: '300000',
      drawdown_tolerance_pct: '15',
      max_position_weight_pct: '12.5',
      max_crypto_weight_pct: '30',
      max_total_risk_pct: '8',
      rebalance_band_pt: '5',
      target_stock_pct: '60',
      target_crypto_pct: '20',
      target_cash_pct: '20',
    })
    expect(body.cash).toEqual({ krw: '1500000', usd: '200.5', as_of: '2026-10-20' })
    for (const v of Object.values(body.policy)) if (v !== null) expect(typeof v).toBe('string')
  })

  it('sends no goal and no cash when those are blank, and a blank monthly amount as 0', () => {
    const form = policyToForm({ ...stored, cash: null, policy: { ...fields, goal_krw: null, goal_date: null } })
    form.policy.monthly_manwon = ''
    const body = formToPolicyPayload(form)
    expect(body.policy.goal_krw).toBeNull()
    expect(body.policy.goal_date).toBeNull()
    expect(body.policy.monthly_contribution_krw).toBe('0')
    expect(body.cash).toBeNull()
  })

  it('needs the cash date once an amount is typed, and fills a blank amount with 0', () => {
    const form = policyToForm({ ...stored, cash: null })
    form.cash.krw = '500000'
    expect(() => formToPolicyPayload(form)).toThrow(`${CASH_LABELS_KO.as_of}: 값을 입력하세요`)
    form.cash.as_of = '2026-10-20'
    expect(formToPolicyPayload(form).cash).toEqual({ krw: '500000', usd: '0', as_of: '2026-10-20' })
  })

  it('names an empty or non-numeric field', () => {
    const form = policyToForm(stored)
    form.policy.drawdown_tolerance_pct = ''
    expect(() => formToPolicyPayload(form)).toThrow(`${POLICY_LABELS_KO.drawdown_tolerance_pct}: 값을 입력하세요`)
    form.policy.drawdown_tolerance_pct = '15%'
    expect(() => formToPolicyPayload(form)).toThrow('숫자를 입력하세요')
  })
})

describe('asset-class sum', () => {
  it('adds the three targets and is null while one is not a number', () => {
    expect(targetSum(policyToForm(stored).policy)).toBe(100)
    const form = policyToForm(stored)
    form.policy.target_cash_pct = ''
    expect(targetSum(form.policy)).toBeNull()
  })

  it('refuses a sum other than 100 with the sum in the message (the server repeats this check)', () => {
    const form = policyToForm(stored)
    form.policy.target_stock_pct = '70'
    expect(() => formToPolicyPayload(form)).toThrow('자산군 목표 비중(주식·코인·현금)의 합이 100이어야 합니다 (지금 110%)')
    form.policy.target_stock_pct = '59.99'
    expect(() => formToPolicyPayload(form)).toThrow('지금 99.99%')
    // Within the backend's 1e-6 tolerance: accepted, like the server would.
    form.policy.target_stock_pct = '59.9999999'
    expect(formToPolicyPayload(form).policy.target_stock_pct).toBe('59.9999999')
  })
})

describe('wording', () => {
  it('names the states in text and never recommends anything', () => {
    expect(killSwitchChip(true).label).toBe('킬스위치 켜짐')
    expect(killSwitchChip(false).label).toBe('킬스위치 꺼짐')
    expect(liveTradingChip(false).label).toBe('실매매 꺼짐')
    expect(liveTradingChip(false).description).toContain('AM_LIVE_TRADING')
    expect(liveTradingChip(true).label).toBe('실매매 켜짐')
    const banned = /사세요|파세요|오를|예상 수익/
    const sentences = [
      COACH_INTRO_KO,
      COACH_FOOTER_KO,
      CASH_NOTE_KO,
      KILL_SWITCH_RESET_CONFIRM_KO,
      liveTradingChip(true).description,
      liveTradingChip(false).description,
      ...Object.values(POLICY_LABELS_KO),
      ...Object.values(CASH_LABELS_KO),
    ]
    for (const s of sentences) expect(s).not.toMatch(banned)
    // "추천" appears only in the disclaimer that says there is none.
    for (const s of sentences.filter((s) => s !== COACH_INTRO_KO)) expect(s).not.toContain('추천')
    expect(COACH_INTRO_KO).toContain('종목 추천·투자 조언이 아니며')
    expect(COACH_FOOTER_KO).toContain('투자 조언이 아닙니다')
  })
})
