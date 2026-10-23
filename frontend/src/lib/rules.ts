/**
 * Wording and form helpers for the buy-more / stop-loss rule checks (plan G, D-027).
 *
 * A rule check is the result of the user's own rules, not a forecast and not a trading signal.
 * Nothing here computes a level or a probability: levels, distances and probability text come
 * from `/api/rules/check` as they are. This module only turns them into sentences and turns the
 * settings form into the request body.
 */
import type { RuleCheck, RuleSettings, RuleSettingsInput } from '../api/client'
import { formatKrw, formatPct, formatUsd } from './format'

export type RuleStatus = 'cut' | 'add' | 'hold'

/**
 * Chip tone by status. Korean convention: selling is blue (`text-loss`), buying red
 * (`text-gain`); the text always carries the meaning, so colour is never the only cue.
 */
export function chipTone(status: string): { className: string; description: string } {
  if (status === 'cut') return { className: 'bg-loss/10 text-loss', description: '매도 검토' }
  if (status === 'add') return { className: 'bg-gain/10 text-gain', description: '추매 검토' }
  return { className: 'bg-fill text-ink-2', description: '관망' }
}

/** Amount in the position's own currency: dollars for stocks, won for coins held on Upbit. */
export function formatInCurrency(v: number, currency: string): string {
  return currency === 'KRW' ? formatKrw(v) : formatUsd(v)
}

/**
 * `손절 검토 가격까지 −8.2%`. The backend's distance is `(level / price − 1) × 100`, so a value
 * at or above zero means the price is already at or under the level.
 */
export function distancePhrase(target: string, pct: number | null | undefined): string | undefined {
  if (pct === null || pct === undefined || !Number.isFinite(pct)) return undefined
  if (pct >= 0) return `이미 ${target} 이하`
  return `${target}까지 ${formatPct(pct, true, 1)}`
}

/** Why a step-add price is missing: no steps configured, or all of them used. */
export function addPricePhrase(check: Pick<RuleCheck, 'levels' | 'rule' | 'add_steps_done'>): string | undefined {
  if (check.levels.add_price !== null) return undefined
  if (check.rule.add_max_steps === 0) return '분할매수 규칙 없음'
  return `분할매수 ${check.rule.add_max_steps}회 모두 사용`
}

const FORECAST_UNAVAILABLE: Record<string, string> = {
  not_trained: '예측 모델이 아직 학습되지 않아 계산하지 않았습니다',
  insufficient_history: '시세 이력이 짧아 계산하지 않았습니다',
  unavailable: '예측을 쓸 수 없어 계산하지 않았습니다',
  no_1m_horizon: '1개월 예측이 없어 계산하지 않았습니다',
  invalid_quantiles: '예측 범위가 올바르지 않아 계산하지 않았습니다',
}

/**
 * The reference probability as a sentence: the backend's rounded text verbatim (never a raw
 * number) plus its caveat, or the reason there is none.
 */
export function probPhrase(
  check: Pick<RuleCheck, 'cut_prob_1m_label' | 'forecast_status'>,
  caveat: string,
): { text: string; available: boolean } {
  if (check.cut_prob_1m_label) {
    return {
      text: `1개월 뒤 손절 검토 가격 아래로 끝날 확률 ${check.cut_prob_1m_label} (범위 예측 기준, 참고). ${caveat}.`,
      available: true,
    }
  }
  const reason =
    FORECAST_UNAVAILABLE[check.forecast_status] ??
    (check.forecast_status.startsWith('error:') ? '예측 계산에 실패해 계산하지 않았습니다' : FORECAST_UNAVAILABLE.unavailable)
  return { text: `1개월 뒤 손절 검토 가격 아래로 끝날 확률: ${reason}`, available: false }
}

/** `추매 보류: 종목 비중 상한, 킬스위치 발동 중` or nothing. */
export function blockedPhrase(labels: string[]): string | undefined {
  return labels.length ? `추매 보류: ${labels.join(', ')}` : undefined
}

/** Count of reviews by status for the home banner. */
export function countByStatus(checks: Pick<RuleCheck, 'status'>[]): { cut: number; add: number } {
  return {
    cut: checks.filter((c) => c.status === 'cut').length,
    add: checks.filter((c) => c.status === 'add').length,
  }
}

/** `매도 검토 2종목 · 추매 검토 1종목`, or undefined when there is nothing to review. */
export function bannerTitle(counts: { cut: number; add: number }): string | undefined {
  const parts: string[] = []
  if (counts.cut > 0) parts.push(`매도 검토 ${counts.cut}종목`)
  if (counts.add > 0) parts.push(`추매 검토 ${counts.add}종목`)
  return parts.length ? parts.join(' · ') : undefined
}

export const RULES_FOOTNOTE_KO =
  "규칙 점검은 예측이 아니라 내가 정한 규칙의 결과입니다. 예측 모델의 매매 신호는 현재 '우위 없음'입니다. " +
  "손절가는 '검토 시작' 기준이며 그 가격에 팔 수 있다는 뜻이 아닙니다. 갭·장중 변동·환율로 실제 체결가는 다를 수 있습니다. " +
  '손절·추매가는 현재가, 이동평균 조건은 확정 종가 기준입니다. 투자 조언이 아닙니다.'

export const PRICE_BASIS_KO = '손절·추매가는 현재가, 이동평균 조건은 확정 종가 기준입니다.'

// --- settings form -----------------------------------------------------------------------------

export const GLOBAL_PCT_KEYS = ['cut_loss_pct', 'trailing_drop_pct', 'add_step_pct', 'target_weight_gap_pt', 'max_risk_pct'] as const
export const GLOBAL_INT_KEYS = ['trailing_lookback_days', 'below_ma_days', 'ma_long', 'ma_short', 'add_max_steps'] as const
export const CRYPTO_KEYS = ['cut_loss_pct', 'trailing_drop_pct', 'add_step_pct'] as const
export const SYMBOL_PCT_KEYS = ['target_weight_pct', 'cut_loss_pct', 'trailing_drop_pct', 'add_step_pct'] as const

export type GlobalPctKey = (typeof GLOBAL_PCT_KEYS)[number]
export type GlobalIntKey = (typeof GLOBAL_INT_KEYS)[number]
export type CryptoKey = (typeof CRYPTO_KEYS)[number]
export type SymbolPctKey = (typeof SYMBOL_PCT_KEYS)[number]

/** Every number is a string while editing, so what the user typed is sent as typed. */
export type GlobalForm = Record<GlobalPctKey | GlobalIntKey, string> & { add_requires_above_ma_short: boolean }
export type CryptoForm = Record<CryptoKey, string>
export type SymbolForm = Record<SymbolPctKey, string> & { add_max_steps: string }
export type RuleForm = { global: GlobalForm; crypto: CryptoForm; targets: Record<string, SymbolForm> }

export const GLOBAL_LABELS: Record<GlobalPctKey | GlobalIntKey | 'add_requires_above_ma_short', string> = {
  cut_loss_pct: '손절 검토 (평균단가 대비 −%)',
  trailing_lookback_days: '추적 손절 고점 기간 (봉 수)',
  trailing_drop_pct: '추적 손절 (고점 대비 −%)',
  below_ma_days: '장기선 아래 연속 봉 수',
  ma_long: '장기 이동평균 (봉 수)',
  ma_short: '단기 이동평균 (봉 수)',
  add_step_pct: '추매 단계 (평균단가 대비 −%마다)',
  add_max_steps: '추매 최대 횟수',
  add_requires_above_ma_short: '추매는 단기선 위에서만',
  target_weight_gap_pt: '목표 비중 미달 (−%p 이하)',
  max_risk_pct: '포지션 리스크 한도 (손절 시 손실, 총자산 %)',
}

export const CRYPTO_LABELS: Record<CryptoKey, string> = {
  cut_loss_pct: '손절 검토 −%',
  trailing_drop_pct: '추적 손절 −%',
  add_step_pct: '추매 단계 −%',
}

export const SYMBOL_LABELS: Record<SymbolPctKey | 'add_max_steps', string> = {
  target_weight_pct: '목표 비중 %',
  cut_loss_pct: '손절 −%',
  trailing_drop_pct: '추적 손절 −%',
  add_step_pct: '추매 단계 −%',
  add_max_steps: '최대 횟수',
}

const str = (v: number | null | undefined) => (v === null || v === undefined ? '' : String(v))

const emptySymbol = (): SymbolForm => ({
  target_weight_pct: '',
  cut_loss_pct: '',
  trailing_drop_pct: '',
  add_step_pct: '',
  add_max_steps: '',
})

function globalToForm(g: RuleSettings['global']): GlobalForm {
  return {
    cut_loss_pct: str(g.cut_loss_pct),
    trailing_lookback_days: str(g.trailing_lookback_days),
    trailing_drop_pct: str(g.trailing_drop_pct),
    below_ma_days: str(g.below_ma_days),
    ma_long: str(g.ma_long),
    ma_short: str(g.ma_short),
    add_step_pct: str(g.add_step_pct),
    add_max_steps: str(g.add_max_steps),
    add_requires_above_ma_short: g.add_requires_above_ma_short,
    target_weight_gap_pt: str(g.target_weight_gap_pt),
    max_risk_pct: str(g.max_risk_pct),
  }
}

function cryptoToForm(c: RuleSettings['crypto']): CryptoForm {
  return { cut_loss_pct: str(c.cut_loss_pct), trailing_drop_pct: str(c.trailing_drop_pct), add_step_pct: str(c.add_step_pct) }
}

/**
 * The saved settings as form text. `symbols` are the held symbols: each gets a row even without
 * an override, and a stored override for a symbol no longer held keeps its row so it is not lost
 * on the next save.
 */
export function settingsToForm(s: RuleSettings, symbols: string[]): RuleForm {
  const targets: Record<string, SymbolForm> = {}
  for (const symbol of [...symbols, ...Object.keys(s.targets)]) {
    if (symbol in targets) continue
    const t = s.targets[symbol]
    targets[symbol] = t
      ? {
          target_weight_pct: str(t.target_weight_pct),
          cut_loss_pct: str(t.cut_loss_pct),
          trailing_drop_pct: str(t.trailing_drop_pct),
          add_step_pct: str(t.add_step_pct),
          add_max_steps: str(t.add_max_steps),
        }
      : emptySymbol()
  }
  return { global: globalToForm(s.global), crypto: cryptoToForm(s.crypto), targets }
}

/** The `AM_RULES_*` defaults as form text; symbol overrides are cleared (rows stay, empty). */
export function defaultsToForm(s: RuleSettings, symbols: string[]): RuleForm {
  const targets: Record<string, SymbolForm> = {}
  for (const symbol of [...symbols, ...Object.keys(s.targets)]) targets[symbol] = emptySymbol()
  return { global: globalToForm(s.defaults.global), crypto: cryptoToForm(s.defaults.crypto), targets }
}

function requiredText(label: string, v: string): string {
  const t = v.trim()
  if (!t) throw new Error(`${label}: 값을 입력하세요`)
  return t
}

function intField(label: string, v: string): number {
  const t = requiredText(label, v)
  if (!/^-?\d+$/.test(t)) throw new Error(`${label}: 정수를 입력하세요`)
  return Number(t)
}

function optionalText(v: string): string | null {
  const t = v.trim()
  return t ? t : null
}

function optionalInt(label: string, v: string): number | null {
  const t = v.trim()
  if (!t) return null
  if (!/^-?\d+$/.test(t)) throw new Error(`${label}: 정수를 입력하세요`)
  return Number(t)
}

/**
 * The request body. Percentages stay strings for the backend's exact-decimal parsing and its
 * range checks (it answers 422 naming the field); only emptiness and integer shape are checked
 * here, with a Korean message. A crypto field left blank means "use the global value"; a symbol
 * row with every field blank is sent empty and dropped by the backend.
 */
export function formToPayload(f: RuleForm): RuleSettingsInput {
  const g = f.global
  const global: RuleSettingsInput['global'] = {
    cut_loss_pct: requiredText(GLOBAL_LABELS.cut_loss_pct, g.cut_loss_pct),
    trailing_lookback_days: intField(GLOBAL_LABELS.trailing_lookback_days, g.trailing_lookback_days),
    trailing_drop_pct: requiredText(GLOBAL_LABELS.trailing_drop_pct, g.trailing_drop_pct),
    below_ma_days: intField(GLOBAL_LABELS.below_ma_days, g.below_ma_days),
    ma_long: intField(GLOBAL_LABELS.ma_long, g.ma_long),
    ma_short: intField(GLOBAL_LABELS.ma_short, g.ma_short),
    add_step_pct: requiredText(GLOBAL_LABELS.add_step_pct, g.add_step_pct),
    add_max_steps: intField(GLOBAL_LABELS.add_max_steps, g.add_max_steps),
    add_requires_above_ma_short: g.add_requires_above_ma_short,
    target_weight_gap_pt: requiredText(GLOBAL_LABELS.target_weight_gap_pt, g.target_weight_gap_pt),
    max_risk_pct: requiredText(GLOBAL_LABELS.max_risk_pct, g.max_risk_pct),
  }
  const crypto = {
    cut_loss_pct: optionalText(f.crypto.cut_loss_pct),
    trailing_drop_pct: optionalText(f.crypto.trailing_drop_pct),
    add_step_pct: optionalText(f.crypto.add_step_pct),
  }
  const targets: RuleSettingsInput['targets'] = {}
  for (const [symbol, t] of Object.entries(f.targets)) {
    targets[symbol] = {
      target_weight_pct: optionalText(t.target_weight_pct),
      cut_loss_pct: optionalText(t.cut_loss_pct),
      trailing_drop_pct: optionalText(t.trailing_drop_pct),
      add_step_pct: optionalText(t.add_step_pct),
      add_max_steps: optionalInt(`${symbol} ${SYMBOL_LABELS.add_max_steps}`, t.add_max_steps),
    }
  }
  return { global, crypto, targets }
}
