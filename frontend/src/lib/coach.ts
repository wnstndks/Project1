/**
 * Wording and form helpers for the portfolio coach (DECISIONS.md D-033).
 *
 * The coach checks the portfolio against the policy the user wrote down. It is not a forecast,
 * not a stock pick and not advice, and the words here never say "추천", "사세요", "파세요",
 * "오를" or "예상 수익". Nothing here computes a diagnosis: every figure comes from `/api/coach/*`
 * as it is, and this module only turns it into sentences, the policy form into the request body
 * and the API's policy into form text. Every number is sent as the string the user typed so the
 * backend parses exact decimals; the backend's 422 is the authority on ranges.
 */
import type {
  CoachBeta,
  CoachDiagnosis,
  CoachLagFlag,
  CoachOrder,
  CoachPattern,
  CoachPolicy,
  CoachPolicyFields,
  CoachPolicyInput,
  CoachRiskWindow,
  RuleCheckAll,
} from '../api/client'
import { displaySymbol, formatDate, formatKrw, formatKrwShort, formatQty, signed } from './format'

export const COACH_INTRO_KO =
  '내가 정한 정책을 기준으로 지금 상태를 점검합니다. 예측·종목 추천·투자 조언이 아니며, 모든 숫자는 근거를 함께 적습니다.'

export const COACH_FOOTER_KO = '투자 조언이 아닙니다. 수수료·세금 미포함.'

export const CASH_NOTE_KO = '현금은 이 앱이 알 수 없어 직접 적습니다. 비우면 현금 없이 점검합니다.'

export const DEFAULTS_NOTE_KO = '아직 정책을 저장하지 않아 서버 설정의 기본값을 보여 줍니다. 저장하면 내 정책이 됩니다.'

/** Days after which a hand-entered cash balance counts as old (the backend's CASH_STALE_DAYS). */
export const CASH_STALE_DAYS = 30

export const CASH_STALE_NOTE_KO = `현금 기준일이 ${CASH_STALE_DAYS}일 넘게 지났습니다. 잔고를 다시 적어 주세요.`

export const EMPTY_NOTE_KO = '보유 종목이 없어 점검할 것이 없어요.'

/** The general principle shown in the in-loss checklist, verbatim. */
export const SMALLER_DECISIONS_KO = '판단 크기를 줄이는 것은 일반 원칙입니다.'

// --- form ----------------------------------------------------------------------------------------

/** Won amounts are typed in 만원 (10,000 won) units; everything else as the backend's percent. */
export const POLICY_MANWON_KEYS = ['goal_manwon', 'monthly_manwon'] as const
export const POLICY_PCT_KEYS = [
  'drawdown_tolerance_pct',
  'max_position_weight_pct',
  'max_crypto_weight_pct',
  'max_total_risk_pct',
  'rebalance_band_pt',
] as const
export const TARGET_KEYS = ['target_stock_pct', 'target_crypto_pct', 'target_cash_pct'] as const

export type PolicyManwonKey = (typeof POLICY_MANWON_KEYS)[number]
export type PolicyPctKey = (typeof POLICY_PCT_KEYS)[number]
export type TargetKey = (typeof TARGET_KEYS)[number]
export type PolicyFormKey = PolicyManwonKey | PolicyPctKey | TargetKey | 'goal_date'

/** Every value is a string while editing, so what the user typed is sent as typed. */
export type PolicyForm = Record<PolicyFormKey, string>
export type CashForm = { krw: string; usd: string; as_of: string }
export type CoachForm = { policy: PolicyForm; cash: CashForm }

export const POLICY_LABELS_KO: Record<PolicyFormKey, string> = {
  goal_manwon: '목표 금액 (만원)',
  goal_date: '목표일',
  monthly_manwon: '월 적립 (만원)',
  drawdown_tolerance_pct: '견딜 수 있는 최대 낙폭 (%)',
  max_position_weight_pct: '종목 하나의 비중 상한 (%)',
  max_crypto_weight_pct: '코인 합산 비중 상한 (%)',
  max_total_risk_pct: '손절 합산 손실 상한 (총자산 %)',
  rebalance_band_pt: '리밸런싱 허용 오차 (%p)',
  target_stock_pct: '주식 목표 비중 (%)',
  target_crypto_pct: '코인 목표 비중 (%)',
  target_cash_pct: '현금 목표 비중 (%)',
}

export const CASH_LABELS_KO: Record<keyof CashForm, string> = {
  krw: '원화 현금 (원)',
  usd: '달러 현금 ($)',
  as_of: '현금 기준일',
}

const str = (v: number | null | undefined) => (v === null || v === undefined ? '' : String(v))

/** Won → 만원 as form text (`12_345_000` → `1234.5`). */
export function krwToManwon(v: number | null | undefined): string {
  if (v === null || v === undefined) return ''
  return String(v / 10_000)
}

/**
 * 만원 text → won as an exact decimal string, by moving the point four places (`1234.5` →
 * `12345000`). No floating point: the backend gets the digits the user typed.
 */
export function manwonToKrw(label: string, text: string): string {
  const t = text.trim().replace(/,/g, '')
  const m = /^(\d+)(?:\.(\d+))?$/.exec(t)
  if (!m) throw new Error(`${label}: 0 이상의 숫자를 입력하세요`)
  const frac = m[2] ?? ''
  if (frac.length > 4) throw new Error(`${label}: 만원의 소수 4자리(원 단위)까지만 적을 수 있습니다`)
  const digits = (m[1] + frac.padEnd(4, '0')).replace(/^0+(?=\d)/, '')
  return digits
}

function fieldsToForm(p: CoachPolicyFields): PolicyForm {
  return {
    goal_manwon: krwToManwon(p.goal_krw),
    goal_date: p.goal_date ?? '',
    monthly_manwon: krwToManwon(p.monthly_contribution_krw),
    drawdown_tolerance_pct: str(p.drawdown_tolerance_pct),
    max_position_weight_pct: str(p.max_position_weight_pct),
    max_crypto_weight_pct: str(p.max_crypto_weight_pct),
    max_total_risk_pct: str(p.max_total_risk_pct),
    rebalance_band_pt: str(p.rebalance_band_pt),
    target_stock_pct: str(p.target_stock_pct),
    target_crypto_pct: str(p.target_crypto_pct),
    target_cash_pct: str(p.target_cash_pct),
  }
}

function cashToForm(c: CoachPolicy['cash']): CashForm {
  if (!c) return { krw: '', usd: '', as_of: '' }
  return { krw: str(c.krw), usd: str(c.usd), as_of: c.as_of }
}

/** The stored policy (or the defaults while none is stored) and cash record as form text. */
export function policyToForm(p: CoachPolicy): CoachForm {
  return { policy: fieldsToForm(p.policy), cash: cashToForm(p.cash) }
}

/** The settings defaults as form text; the cash record is the user's data and stays. */
export function defaultsToForm(p: CoachPolicy): CoachForm {
  return { policy: fieldsToForm(p.defaults), cash: cashToForm(p.cash) }
}

const NUMBER = /^-?\d+(\.\d+)?$/

function requiredNumber(label: string, v: string): string {
  const t = v.trim().replace(/,/g, '')
  if (!t) throw new Error(`${label}: 값을 입력하세요`)
  if (!NUMBER.test(t)) throw new Error(`${label}: 숫자를 입력하세요`)
  return t
}

/** Sum of the three asset-class targets, or null while one of them is not a number. */
export function targetSum(p: PolicyForm): number | null {
  let sum = 0
  for (const key of TARGET_KEYS) {
    const t = p[key].trim()
    if (!NUMBER.test(t)) return null
    sum += Number(t)
  }
  return sum
}

const pctText = (v: number) => String(Math.round(v * 1e6) / 1e6)

/**
 * The request body. Amounts in 만원 become exact won strings, percentages stay the typed text.
 * Checked here with a Korean message: emptiness, number shape and the asset-class sum (the
 * backend repeats the sum check and owns the ranges). Cash is sent only when something was
 * typed; blank amounts count as 0 and the date is required with them. All blank sends null,
 * which clears the stored record.
 */
export function formToPolicyPayload(f: CoachForm): CoachPolicyInput {
  const p = f.policy
  const goal = p.goal_manwon.trim()
  const goalDate = p.goal_date.trim()
  const policy: CoachPolicyInput['policy'] = {
    goal_krw: goal ? manwonToKrw(POLICY_LABELS_KO.goal_manwon, goal) : null,
    goal_date: goalDate || null,
    monthly_contribution_krw: manwonToKrw(
      POLICY_LABELS_KO.monthly_manwon,
      requiredNumber(POLICY_LABELS_KO.monthly_manwon, p.monthly_manwon || '0'),
    ),
    drawdown_tolerance_pct: requiredNumber(POLICY_LABELS_KO.drawdown_tolerance_pct, p.drawdown_tolerance_pct),
    max_position_weight_pct: requiredNumber(POLICY_LABELS_KO.max_position_weight_pct, p.max_position_weight_pct),
    max_crypto_weight_pct: requiredNumber(POLICY_LABELS_KO.max_crypto_weight_pct, p.max_crypto_weight_pct),
    max_total_risk_pct: requiredNumber(POLICY_LABELS_KO.max_total_risk_pct, p.max_total_risk_pct),
    rebalance_band_pt: requiredNumber(POLICY_LABELS_KO.rebalance_band_pt, p.rebalance_band_pt),
    target_stock_pct: requiredNumber(POLICY_LABELS_KO.target_stock_pct, p.target_stock_pct),
    target_crypto_pct: requiredNumber(POLICY_LABELS_KO.target_crypto_pct, p.target_crypto_pct),
    target_cash_pct: requiredNumber(POLICY_LABELS_KO.target_cash_pct, p.target_cash_pct),
  }
  const sum = targetSum(p)
  if (sum === null || Math.abs(sum - 100) > 1e-6) {
    throw new Error(`자산군 목표 비중(주식·코인·현금)의 합이 100이어야 합니다 (지금 ${pctText(sum ?? 0)}%)`)
  }
  return { policy, cash: cashPayload(f.cash) }
}

function cashPayload(c: CashForm): CoachPolicyInput['cash'] {
  const krw = c.krw.trim()
  const usd = c.usd.trim()
  const asOf = c.as_of.trim()
  if (!krw && !usd && !asOf) return null
  if (!asOf) throw new Error(`${CASH_LABELS_KO.as_of}: 값을 입력하세요`)
  return {
    krw: krw ? requiredNumber(CASH_LABELS_KO.krw, krw) : '0',
    usd: usd ? requiredNumber(CASH_LABELS_KO.usd, usd) : '0',
    as_of: asOf,
  }
}

// --- status chips ------------------------------------------------------------------------------------

/** Kill switch chip. Text always carries the state; the tone only underlines it. */
export function killSwitchChip(tripped: boolean): { label: string; className: string } {
  return tripped
    ? { label: '킬스위치 켜짐', className: 'bg-danger/10 text-danger' }
    : { label: '킬스위치 꺼짐', className: 'bg-fill text-ink-2' }
}

/** Real-trading chip. Read-only everywhere: only the server's AM_LIVE_TRADING changes it. */
export function liveTradingChip(on: boolean): { label: string; description: string; className: string } {
  return on
    ? { label: '실매매 켜짐', description: '주문이 실제로 나갈 수 있는 상태입니다.', className: 'bg-danger/10 text-danger' }
    : {
        label: '실매매 꺼짐',
        description: '모의투자 기록만 남깁니다. 이 화면에서는 켤 수 없고 서버 설정(AM_LIVE_TRADING)으로만 바뀝니다.',
        className: 'bg-fill text-ink-2',
      }
}

export const KILL_SWITCH_RESET_CONFIRM_KO = '해제하면 모의투자 신호와 추매 검토가 다시 나옵니다. 정말 해제할까요?'

// --- diagnosis wording ------------------------------------------------------------------------------
// Past-window figures (volatility, drawdown, correlation, beta) never get a gain/loss colour or
// an arrow: they describe what the current mix did, not what it will do.

export function windowLabel(name: string): string {
  if (name === '1y') return '1년'
  if (name === '3y') return '3년'
  return name
}

export function riskWindow(d: Pick<CoachDiagnosis, 'risk'>, name: string): CoachRiskWindow | undefined {
  return d.risk.windows.find((w) => w.name === name)
}

const pct1 = (v: number) => `${v.toFixed(1)}%`

/** `1년에 보통 ±1,234만원 흔들려요 (10번 중 7번 안, 지난 1년 기준)`, or why there is no figure. */
export function swingPhrase(w: CoachRiskWindow | undefined): { value: string; text: string; usable: boolean } {
  if (!w) return { value: '—', text: '과거 변동 자료가 없어요.', usable: false }
  if (!w.usable) return { value: '—', text: `계산하지 못했어요: ${w.reason ?? '자료 부족'}`, usable: false }
  return {
    value: `±${formatKrwShort(w.swing_1sigma_krw)}`,
    text: `1년에 보통 이만큼 오르내렸어요 (10번 중 7번 안, 연 ${pct1(w.annual_vol_pct)} · 지난 ${windowLabel(w.name)} 기준).`,
    usable: true,
  }
}

/** The deepest fall today's mix would have had over the window, beside the tolerance the user wrote. */
export function drawdownPhrase(
  w: CoachRiskWindow | undefined,
  tolerancePct: number,
): { value: string; text: string; over: boolean | null } {
  if (!w || !w.usable) {
    return {
      value: '—',
      text: `지금 구성의 과거 낙폭을 계산하지 못했어요${w?.reason ? `: ${w.reason}` : '.'}`,
      over: null,
    }
  }
  const over = w.max_drawdown_pct > tolerancePct + 1e-9
  return {
    value: `−${pct1(w.max_drawdown_pct)}`,
    text: `지금 구성으로 지난 ${windowLabel(w.name)}을 지났다면 가장 깊은 하락이에요${drawdownSpan(w)}. 내가 견딜 수 있다고 적은 값은 −${tolerancePct}%${
      over ? '이고, 그보다 깊어요.' : '이고, 그 안이에요.'
    }`,
    over,
  }
}

/** ` (고점 2.1 → 저점 4.1)`, or ` (창 시작부터 4.1까지)` when the window opened at the peak. */
function drawdownSpan(w: CoachRiskWindow): string {
  if (!w.drawdown_trough) return ''
  if (w.drawdown_peak) return ` (고점 ${formatDate(w.drawdown_peak)} → 저점 ${formatDate(w.drawdown_trough)})`
  if (w.peak_at_window_start) return ` (창 시작부터 ${formatDate(w.drawdown_trough)}까지)`
  return ''
}

/** Chip tone for a violation; the label and detail always say what it is. */
export function violationTone(severity: string): string {
  return severity === 'warn' ? 'bg-danger/10 text-danger' : 'bg-fill text-ink-2'
}

/**
 * One sentence for the home card, or nothing when there is nothing to say (loading, no
 * holdings). "No holdings" is checked before "no policy": with nothing held the card stays
 * hidden even when no policy is saved (N-COACH-4).
 */
export function coachSummary(d: Partial<CoachDiagnosis> | undefined): string | undefined {
  if (!d) return undefined
  if (d.empty) return undefined
  if (!d.policy_set) return '정책을 아직 정하지 않았어요 →'
  const warns = (d.violations ?? []).filter((v) => v.severity === 'warn').length
  const crypto = d.exposure?.crypto_pct ?? 0
  const parts = [`정책 위반 ${warns}건`, `코인 비중 ${Math.round(crypto)}%`]
  if (d.cash_krw === null || d.cash_krw === undefined) parts.push('현금 미입력')
  return `${parts.join(' · ')} →`
}

/** `SPY가 1% 움직일 때 평균 1.20% 움직였어요 (…)`: the slope in the trade currency, past year. */
export function betaPhrase(b: CoachBeta): string {
  if (b.beta === null) return `${displaySymbol(b.benchmark)} 대비 계산하지 못했어요: ${b.reason ?? '자료 부족'}`
  const fit = b.r2 === null ? '' : `, 설명력 ${Math.round(b.r2 * 100)}%`
  return `${displaySymbol(b.benchmark)}가 1% 움직일 때 평균 ${b.beta.toFixed(2)}% 움직였어요 (${b.rows}일${fit}, 지난 1년)`
}

/** The goal arithmetic as a sentence; undefined without a goal. Never a forecast. */
export function requiredReturnPhrase(d: Pick<CoachDiagnosis, 'goal_years' | 'required_annual_return_pct'>): string | undefined {
  if (d.goal_years === null) return undefined
  if (d.goal_years <= 0) return '목표일이 지났어요. 새 목표일을 적어 주세요.'
  if (d.required_annual_return_pct === null) {
    return `목표까지 ${d.goal_years.toFixed(1)}년. 지금 자산과 적립만으로 닿거나(0%), 연 100%로도 닿지 않아 필요 수익률을 계산하지 않았어요.`
  }
  return `목표까지 ${d.goal_years.toFixed(1)}년 · 해마다 ${d.required_annual_return_pct.toFixed(1)}% 수익이 필요해요 (산수이지 예측이 아닙니다).`
}

// --- checklists --------------------------------------------------------------------------------------

export type ChecklistState = 'ok' | 'warn' | 'info'
export type ChecklistItem = { label: string; state: ChecklistState; detail: string }

export const CHECKLIST_STATE_KO: Record<ChecklistState, string> = { ok: '충족', warn: '주의', info: '참고' }

const round1 = (v: number) => Math.round(v * 10) / 10
/** Percentage points with a real minus sign: `−30%p`. */
const fmtPt = (v: number) => `${v < 0 ? '−' : ''}${Math.abs(round1(v))}%p`

/** Before a buy: room under the caps, the stop-loss total, cash and the kill switch. */
export function preBuyChecklist(d: CoachDiagnosis, rules?: RuleCheckAll): ChecklistItem[] {
  const items: ChecklistItem[] = []
  const top = [...d.weights].sort((a, b) => b.weight_pct - a.weight_pct)[0]
  if (top) {
    const room = top.cap_pct - top.weight_pct
    items.push({
      label: '종목 상한까지 여유',
      state: room > 0 ? 'ok' : 'warn',
      detail: `가장 큰 종목 ${displaySymbol(top.symbol)} ${pct1(top.weight_pct)} · 상한 ${top.cap_pct}% · 여유 ${fmtPt(room)}`,
    })
  }
  const total = d.total_risk_pct_equity
  const riskCap = Number(d.policy.max_total_risk_pct)
  items.push(
    total === null
      ? { label: '손절 시 손실 vs 한도', state: 'info', detail: '규칙 점검 결과가 없어 확인하지 못했어요.' }
      : {
          label: '손절 시 손실 vs 한도',
          state: total > riskCap ? 'warn' : 'ok',
          detail: `모든 손절이 걸리면 총자산의 ${pct1(total)} · 상한 ${riskCap}%`,
        },
  )
  const crypto = d.exposure?.crypto_pct ?? 0
  const cryptoCap = Number(d.policy.max_crypto_weight_pct)
  items.push({
    label: '코인 상한까지 여유',
    state: crypto < cryptoCap ? 'ok' : 'warn',
    detail: `코인 합산 ${pct1(crypto)} · 상한 ${cryptoCap}% · 여유 ${fmtPt(cryptoCap - crypto)}`,
  })
  items.push(
    d.cash_krw === null
      ? { label: '현금 여유', state: 'info', detail: '현금을 적지 않아 확인할 수 없어요.' }
      : {
          label: '현금 여유',
          state: d.cash_stale ? 'warn' : 'ok',
          detail: `현금 ${formatKrwShort(d.cash_krw)} (기준일 ${d.cash_as_of ?? '—'}${d.cash_stale ? ', 오래됨' : ''})`,
        },
  )
  items.push(killSwitchItem(rules))
  return items
}

/** While losing: what the rules say, the real drawdown against the tolerance, the switch, and the principle. */
export function inLossChecklist(d: CoachDiagnosis, rules?: RuleCheckAll): ChecklistItem[] {
  const items: ChecklistItem[] = []
  if (rules) {
    const cuts = rules.checks.filter((c) => c.status === 'cut').length
    items.push({
      label: '발동한 내 규칙',
      state: cuts > 0 ? 'warn' : 'ok',
      detail: cuts > 0 ? `손절 검토 ${cuts}종목 — 규칙 페이지에서 확인하세요.` : '손절 검토에 걸린 종목이 없어요.',
    })
  } else {
    items.push({ label: '발동한 내 규칙', state: 'info', detail: '규칙 점검 결과를 아직 받지 못했어요.' })
  }
  const actual = d.risk.actual
  const tolerance = Number(d.policy.drawdown_tolerance_pct)
  items.push(
    actual
      ? {
          label: '낙폭 vs 허용 낙폭',
          state: actual.current_drawdown_pct > tolerance ? 'warn' : 'ok',
          detail: `지금 고점 대비 −${pct1(actual.current_drawdown_pct)} · 허용 −${tolerance}% (입금을 뺀 실제 추이 기준)`,
        }
      : // Not computed (mis-priced trades, a refused curve, too short): the server's reason as
        // it is, as a note rather than a pass or a warning.
        { label: '낙폭 vs 허용 낙폭', state: 'info', detail: actualCurveNote(d) },
  )
  items.push(killSwitchItem(rules))
  items.push({ label: '판단 크기 줄이기', state: 'info', detail: `${SMALLER_DECISIONS_KO} 한 번에 결정하지 않아도 됩니다.` })
  return items
}

export const ACTUAL_CURVE_SHORT_KO = '실제 추이가 아직 짧아 낙폭을 계산하지 못했어요.'

/** Why the real curve's drawdown is missing: the server's sentence verbatim, or the short-history default. */
export function actualCurveNote(d: Pick<CoachDiagnosis, 'risk'>): string {
  return d.risk.actual_error ?? ACTUAL_CURVE_SHORT_KO
}

function killSwitchItem(rules?: RuleCheckAll): ChecklistItem {
  if (!rules) return { label: '킬스위치', state: 'info', detail: '상태를 아직 받지 못했어요.' }
  return rules.kill_switch.tripped
    ? { label: '킬스위치', state: 'warn', detail: `켜져 있어 모의투자 신호와 추매 검토가 멈춰 있어요 (${rules.kill_switch.detail || rules.kill_switch.reason_code || ''}).` }
    : { label: '킬스위치', state: 'ok', detail: '꺼져 있어요.' }
}

// --- rebalancing and patterns -----------------------------------------------------------------------

const qtyUnit = (symbol: string) => (symbol.endsWith('-USD') ? '개' : '주')

/** `줄이기 120만원 · 약 3주`, `늘리기 …`, or why it is blocked. Never "사세요/파세요". */
export function rebalanceActionPhrase(o: CoachOrder): string {
  const verb = o.side === 'sell' ? '줄이기' : '늘리기'
  if (o.status === 'rejected') return `${verb} 막힘 (${o.labels.join(', ') || o.reasons.join(', ') || '사유 없음'})`
  const qty = o.approx_qty === null ? '' : ` · 약 ${formatQty(o.approx_qty)}${qtyUnit(o.symbol)}`
  const clipped = o.status === 'clipped' ? ` (요청 ${formatKrwShort(o.requested_krw)} 중)` : ''
  return `${verb} ${formatKrwShort(o.allowed_krw)}${qty}${clipped}`
}

/**
 * A hypothetical amount with its sign only: `+3,000,000원`, `−500,000원`, `0원`. Used for the
 * "if sold" realized P&L of the rebalance table, which is an assumption and so gets neither the
 * gain/loss colour nor an arrow (N-COACH-3); only money actually realized is coloured.
 */
export function signedKrw(v: number): string {
  return signed(v, formatKrw)
}

/** `급등 뒤 매수 2건`. */
export function patternPhrase(p: Pick<CoachPattern, 'label_ko' | 'count'>): string {
  return `${p.label_ko} ${p.count}건`
}

/**
 * `AAA: 2026년 9월 1일부터 12봉째 손절 검토 가격 아래 ($120.00)`. When every loaded bar was
 * already below the stop, `since` is only the first bar loaded and `days` a lower bound, so it
 * reads `12봉 이상 (조회 범위 처음부터)` (N-COACH-6).
 */
export function lagPhrase(l: CoachLagFlag): string {
  const price = l.currency === 'KRW' ? formatKrw(l.cut_price) : `$${l.cut_price.toFixed(2)}`
  const length = l.since_window_start ? `${l.days}봉 이상 (조회 범위 처음부터)` : `${l.days}봉째`
  return `${displaySymbol(l.symbol)}: ${fullDate(l.since)}부터 ${length} 손절 검토 가격 아래 (${price})`
}

/** `2026-10-27` → `2026년 10월 27일`, always with the year (unlike `formatDate`, which drops this year's). */
export function fullDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  return m ? `${m[1]}년 ${Number(m[2])}월 ${Number(m[3])}일` : iso
}

/** `2025년 10월 27일부터 2026년 10월 27일까지`: both ends in one format, so the years never mix. */
export function windowSpanPhrase(start: string, end: string): string {
  return `${fullDate(start)}부터 ${fullDate(end)}까지`
}

/**
 * The review headline's count comes from the weight- and exposure-based checks alone (no
 * bars), so it can be lower than the diagnosis count; the label says which checks (N-COACH-5).
 */
export function reviewViolationsLabel(n: number): string {
  return `지금 비중·자산군 위반 ${n}건`
}

/** Shown in the review when the month starts before the habit window (today − 1 year). */
export const FLAGS_NOT_COUNTED_KO = '습관 점검은 최근 1년 거래만 보기 때문에 이 달은 세지 않았어요.'

/** `2026-10` → `2026년 10월`. */
export function monthLabel(key: string): string {
  const m = /^(\d{4})-(\d{2})$/.exec(key)
  return m ? `${m[1]}년 ${Number(m[2])}월` : key
}
