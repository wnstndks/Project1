import { describe, expect, it } from 'vitest'

import type { RuleSettings } from '../api/client'
import {
  addPricePhrase,
  bannerTitle,
  blockedPhrase,
  chipTone,
  countByStatus,
  defaultsToForm,
  distancePhrase,
  formatInCurrency,
  formToPayload,
  probPhrase,
  RULES_FOOTNOTE_KO,
  settingsToForm,
} from './rules'

const settings: RuleSettings = {
  global: {
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
    max_risk_pct: 2,
  },
  crypto: { cut_loss_pct: 25, trailing_drop_pct: null, add_step_pct: 8 },
  targets: { OLD: { target_weight_pct: 10, cut_loss_pct: null, trailing_drop_pct: null, add_step_pct: null, add_max_steps: 1 } },
  defaults: {
    global: {
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
      max_risk_pct: 2,
    },
    crypto: { cut_loss_pct: 25, trailing_drop_pct: 30, add_step_pct: 8 },
  },
  warnings: [],
  updated_at: null,
  live_trading: false,
}

describe('chip wording', () => {
  it('colours selling blue and buying red, and always names the state in text', () => {
    expect(chipTone('cut')).toEqual({ className: 'bg-loss/10 text-loss', description: '매도 검토' })
    expect(chipTone('add')).toEqual({ className: 'bg-gain/10 text-gain', description: '추매 검토' })
    expect(chipTone('hold').className).toContain('text-ink-2')
  })

  it('counts reviews and builds the banner title, hidden when nothing is under review', () => {
    const counts = countByStatus([{ status: 'cut' }, { status: 'cut' }, { status: 'add' }, { status: 'hold' }])
    expect(counts).toEqual({ cut: 2, add: 1 })
    expect(bannerTitle(counts)).toBe('매도 검토 2종목 · 추매 검토 1종목')
    expect(bannerTitle({ cut: 0, add: 1 })).toBe('추매 검토 1종목')
    expect(bannerTitle({ cut: 0, add: 0 })).toBeUndefined()
  })
})

describe('distance and level wording', () => {
  it('writes the move to the level with sign and one decimal', () => {
    expect(distancePhrase('손절 검토 가격', -8.24)).toBe('손절 검토 가격까지 −8.2%')
    expect(distancePhrase('다음 추매가', -4)).toBe('다음 추매가까지 −4.0%')
  })

  it('says the level is already reached when the distance is not negative', () => {
    expect(distancePhrase('손절 검토 가격', 0)).toBe('이미 손절 검토 가격 이하')
    expect(distancePhrase('손절 검토 가격', 3.1)).toBe('이미 손절 검토 가격 이하')
    expect(distancePhrase('다음 추매가', null)).toBeUndefined()
  })

  it('explains a missing add price', () => {
    const base = { levels: { add_price: null }, rule: { add_max_steps: 2 }, add_steps_done: 2 }
    expect(addPricePhrase(base as never)).toBe('분할매수 2회 모두 사용')
    expect(addPricePhrase({ ...base, rule: { add_max_steps: 0 } } as never)).toBe('분할매수 규칙 없음')
    expect(addPricePhrase({ ...base, levels: { add_price: 90 } } as never)).toBeUndefined()
  })

  it('formats in the position currency', () => {
    expect(formatInCurrency(85, 'USD')).toBe('$85.00')
    expect(formatInCurrency(60_000_000, 'KRW')).toBe('60,000,000원')
  })

  it('lists why a buy is blocked', () => {
    expect(blockedPhrase(['종목 비중 상한', '킬스위치 발동 중'])).toBe('추매 보류: 종목 비중 상한, 킬스위치 발동 중')
    expect(blockedPhrase([])).toBeUndefined()
  })
})

describe('probability wording', () => {
  const caveat = '기간 끝에 그 아래일 확률이며, 도중에 한 번 닿을 확률은 대략 두 배입니다'

  it('uses the backend text verbatim with the caveat and never a raw number', () => {
    const r = probPhrase({ cut_prob_1m_label: '약 15%', forecast_status: 'ok' }, caveat)
    expect(r.available).toBe(true)
    expect(r.text).toBe(`1개월 뒤 손절 검토 가격 아래로 끝날 확률 약 15% (범위 예측 기준, 참고). ${caveat}.`)
    expect(probPhrase({ cut_prob_1m_label: '10% 미만', forecast_status: 'ok' }, caveat).text).toContain('10% 미만')
  })

  it('names the reason when there is no probability', () => {
    expect(probPhrase({ cut_prob_1m_label: null, forecast_status: 'not_trained' }, caveat)).toEqual({
      text: '1개월 뒤 손절 검토 가격 아래로 끝날 확률: 예측 모델이 아직 학습되지 않아 계산하지 않았습니다',
      available: false,
    })
    expect(probPhrase({ cut_prob_1m_label: null, forecast_status: 'error:KeyError' }, caveat).text).toContain('실패')
    expect(probPhrase({ cut_prob_1m_label: null, forecast_status: 'whatever' }, caveat).text).toContain('쓸 수 없어')
  })

  it('keeps the required disclosures in the footnote', () => {
    for (const s of ['예측이 아니라', "'우위 없음'", '검토 시작', '확정 종가', '투자 조언이 아닙니다']) {
      expect(RULES_FOOTNOTE_KO).toContain(s)
    }
  })
})

describe('settings form', () => {
  it('turns settings into text with a row per held symbol and keeps stored overrides', () => {
    const form = settingsToForm(settings, ['AAPL', 'BTC-USD'])
    expect(form.global.cut_loss_pct).toBe('15')
    expect(form.global.add_requires_above_ma_short).toBe(true)
    expect(form.crypto).toEqual({ cut_loss_pct: '25', trailing_drop_pct: '', add_step_pct: '8' })
    expect(Object.keys(form.targets)).toEqual(['AAPL', 'BTC-USD', 'OLD'])
    expect(form.targets.AAPL.target_weight_pct).toBe('')
    expect(form.targets.OLD).toEqual({ target_weight_pct: '10', cut_loss_pct: '', trailing_drop_pct: '', add_step_pct: '', add_max_steps: '1' })
  })

  it('resets to the defaults and clears every symbol override', () => {
    const form = defaultsToForm({ ...settings, global: { ...settings.global, cut_loss_pct: 7 } }, ['AAPL'])
    expect(form.global.cut_loss_pct).toBe('15')
    expect(form.crypto.trailing_drop_pct).toBe('30')
    expect(form.targets.AAPL.target_weight_pct).toBe('')
    expect(form.targets.OLD.target_weight_pct).toBe('')
  })

  it('sends percentages as the typed strings, integers as numbers and blanks as null', () => {
    const form = settingsToForm(settings, ['AAPL'])
    form.global.cut_loss_pct = ' 12.5 '
    form.targets.AAPL.target_weight_pct = '20'
    const body = formToPayload(form)
    expect(body.global.cut_loss_pct).toBe('12.5')
    expect(body.global.trailing_lookback_days).toBe(60)
    expect(body.global.add_requires_above_ma_short).toBe(true)
    expect(body.crypto).toEqual({ cut_loss_pct: '25', trailing_drop_pct: null, add_step_pct: '8' })
    expect(body.targets.AAPL).toEqual({
      target_weight_pct: '20',
      cut_loss_pct: null,
      trailing_drop_pct: null,
      add_step_pct: null,
      add_max_steps: null,
    })
    expect(body.targets.OLD.add_max_steps).toBe(1)
  })

  it('rejects blanks and non-integers with a Korean message naming the field', () => {
    const form = settingsToForm(settings, [])
    form.global.cut_loss_pct = ''
    expect(() => formToPayload(form)).toThrow('손절 검토 (평균단가 대비 −%): 값을 입력하세요')
    form.global.cut_loss_pct = '15'
    form.global.ma_long = '60.5'
    expect(() => formToPayload(form)).toThrow('장기 이동평균 (봉 수): 정수를 입력하세요')
    form.global.ma_long = '60'
    form.targets.OLD.add_max_steps = 'x'
    expect(() => formToPayload(form)).toThrow('OLD 최대 횟수: 정수를 입력하세요')
  })
})
