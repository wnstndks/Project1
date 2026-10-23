import { formatDate, formatPct, isoDate } from './format'

export const HORIZON_LABEL: Record<string, string> = { '1d': '1일', '1w': '1주', '1m': '1개월' }

export type Horizon = '1d' | '1w' | '1m'

/** Plain-language time phrase: coins trade every day, so a stock's "1d" is the next session. */
export function horizonPhrase(h: Horizon, coin: boolean): string {
  if (h === '1d') return coin ? '내일' : '다음 거래일'
  if (h === '1w') return '1주 뒤'
  return '1개월 뒤'
}

/**
 * A forecast whose target date is already behind today's local date (ISSUE-039): the provider
 * has not delivered the latest bar yet, so the "next session" line is really waiting to be scored.
 */
export function isPastTarget(targetDate: string, today = new Date()): boolean {
  return targetDate.slice(0, 10) < isoDate(today)
}

/** "채점 대기 (10.21 마감 기준)": what to call a horizon line whose target date has passed. */
export function pendingPhrase(targetDate: string, today = new Date()): string {
  return `채점 대기 (${formatDate(targetDate, 'short', today)} 마감 기준)`
}

/**
 * The one wording for the 10~90% band's coverage. Every "10번 중 8번" on screen comes from
 * here so the legends, sentences and footnotes cannot drift apart.
 */
export const COVERAGE_PHRASE = '10번 중 8번'

/** The 10~90% band in everyday words: the outcome lands inside it about 8 times in 10. */
export function rangePhrase(low: string, high: string): string {
  return `대체로 ${low}~${high} 사이 (${COVERAGE_PHRASE})`
}

/** Legend/label form of the band without values. */
export function bandLabel(): string {
  return `대체로 이 사이 (${COVERAGE_PHRASE})`
}

/** The median as a point estimate, never with P&L color: "1,537만원 안팎". */
export function midPhrase(value: string): string {
  return `${value} 안팎`
}

/** Legend for the median line: it is the half-way point, not a target. */
export function midLegend(): string {
  return '예상 중간값(절반 지점)'
}

/** Legend for the p10~p90 band. */
export function bandLegend(): string {
  return `${COVERAGE_PHRASE} 범위`
}

/** What "coverage" means, with the caveat that crashes break the band more often than 2 in 10. */
export function coverageNote(): string {
  return '약 80%(10번 중 8번꼴, 급락장에서는 더 자주 벗어남)'
}

/** Label for the 5% tail (expected shortfall) without the statistics vocabulary. */
export function badCasePhrase(): string {
  return '운 나쁜 경우 (20번 중 1번꼴)'
}

/** Explains the expected-shortfall number: the average of the worst 5% of outcomes. */
export function esPhrase(): string {
  return '가장 나쁜 5% 상황의 평균 손실 (20번 중 1번은 이 정도 또는 그 이상)'
}

/** The 10% and 90% quantiles as single outcomes (long-range simulation tiles and tables). */
export function tailPhrase(side: 'bad' | 'good'): string {
  return side === 'bad' ? '운 나쁜 경우 (10번 중 1번)' : '운 좋은 경우 (10번 중 1번)'
}

/** `−3.6%~+4.5%`: the 10% and 90% quantile prices as moves from `base`, one decimal. */
export function pctRange(p10: number, p90: number, base: number): string {
  const pct = (v: number) => formatPct(base ? ((v - base) / base) * 100 : 0, true, 1)
  return `${pct(p10)}~${pct(p90)}`
}

type WeekRatios = {
  horizons: { horizon: string; low_ratio: number; high_ratio: number; p_up: number; direction_reason: string }[]
}

/**
 * The home list's one-line hint: "1주 변동 범위 대체로 −3.6%~+4.5% 사이 (10번 중 8번) · 참고용", the
 * one-week 10~90% band from `/api/forecasts/held` as moves from today's price. The probability of a
 * rise is added only where the live direction verdict is an edge; otherwise it is no better than
 * the base rate and does not belong on the home page.
 */
export function weekRangeHint(forecast: WeekRatios | undefined): string | undefined {
  const week = forecast?.horizons.find((x) => x.horizon === '1w')
  if (!week) return undefined
  const pct = (ratio: number) => formatPct((ratio - 1) * 100, true, 1)
  const parts = [`1주 변동 범위 ${rangePhrase(pct(week.low_ratio), pct(week.high_ratio))}`]
  if (week.direction_reason === 'edge') parts.push(`오를 확률 ${Math.round(week.p_up * 100)}%`)
  parts.push('참고용')
  return parts.join(' · ')
}

export type EdgeTone = 'good' | 'pending' | 'none'

/** The live verdict reasons the backend sends (forecast.report.live_edge_at). */
export type EdgeReason = 'edge' | 'forward_test_pending' | 'not_significant' | 'no_data'

type Verdict = { direction_reason: string; range_reason: string }

// `forward_test_pending` is sent only when the walk-forward tests passed and the forward paper
// test is still running (ISSUE-037), so the label may say both halves.
const REASON_LABEL: Record<EdgeReason, { label: string; tone: EdgeTone }> = {
  edge: { label: '검증 통과', tone: 'good' },
  forward_test_pending: { label: '과거 검증 통과 · 실전 검증 대기', tone: 'pending' },
  not_significant: { label: '우위 없음', tone: 'none' },
  no_data: { label: '데이터 부족', tone: 'none' },
}

/** Label and tone for one live reason. Unknown reasons are shown as no edge, never as a pass. */
export function reasonLabel(reason: string): { label: string; tone: EdgeTone } {
  return REASON_LABEL[reason as EdgeReason] ?? REASON_LABEL.not_significant
}

export type EdgeChip = { axis: '방향' | '범위'; label: string; tone: EdgeTone }

/**
 * Two chips per verdict, direction and range separately. A range that passed cannot be
 * folded into one "검증 통과" badge when the direction has no edge, so each axis speaks for itself.
 */
export function edgeLabels(h: Verdict): EdgeChip[] {
  return [
    { axis: '방향', ...reasonLabel(h.direction_reason) },
    { axis: '범위', ...reasonLabel(h.range_reason) },
  ]
}

// Best to worst. "우위 없음" is the definitive negative and ranks below "데이터 부족", so a horizon
// that was tested and failed always wins over one that could not be tested.
const REASON_RANK: Record<EdgeReason, number> = {
  edge: 0,
  forward_test_pending: 1,
  no_data: 2,
  not_significant: 3,
}

function rank(reason: string): number {
  return REASON_RANK[reason as EdgeReason] ?? REASON_RANK.not_significant
}

/**
 * The most conservative reason per axis across the horizons, for one badge that covers all
 * three periods. Returns undefined for an empty list.
 */
export function worstHorizonVerdict(horizons: Verdict[]): Verdict | undefined {
  if (horizons.length === 0) return undefined
  const worst = (key: keyof Verdict) =>
    horizons.map((h) => h[key]).reduce((a, b) => (rank(b) > rank(a) ? b : a))
  return { direction_reason: worst('direction_reason'), range_reason: worst('range_reason') }
}

/** `/api/forecasts/status`'s `live`: asset class → horizon → { direction, range } reasons. */
export type LiveVerdicts = Record<string, Record<string, { direction: string; range: string }>>

const CLASS_LABEL: Record<string, string> = { stock: '주식', crypto: '코인' }

type Cell = { cls: string; horizon: string; kind: 'direction' | 'range'; reason: string }

function cells(live: LiveVerdicts | null | undefined): Cell[] {
  const out: Cell[] = []
  for (const [cls, byHorizon] of Object.entries(live ?? {})) {
    if (!byHorizon || typeof byHorizon !== 'object') continue
    for (const [horizon, v] of Object.entries(byHorizon)) {
      if (!v || typeof v !== 'object') continue
      out.push({ cls, horizon, kind: 'direction', reason: String(v.direction) })
      out.push({ cls, horizon, kind: 'range', reason: String(v.range) })
    }
  }
  return out
}

/** "주식 1일·코인 1주" */
function where(list: Cell[]): string {
  return list.map((c) => `${CLASS_LABEL[c.cls] ?? c.cls} ${HORIZON_LABEL[c.horizon] ?? c.horizon}`).join('·')
}

/**
 * One honest sentence on the trained model from the live verdicts (the same judgement the
 * symbol page's chips use). The baselines are statistical (share of up days, EWMA volatility),
 * so the text never claims a comparison with "the market".
 */
export function modelStatusSentence(live: LiveVerdicts | null | undefined): string {
  const all = cells(live)
  if (all.length === 0) return '아직 검증 결과가 없어 우위를 확인할 수 없습니다. 참고만 하세요.'
  const dirEdge = all.filter((c) => c.kind === 'direction' && c.reason === 'edge')
  const rangeEdge = all.filter((c) => c.kind === 'range' && c.reason === 'edge')
  const rangePending = all.some((c) => c.kind === 'range' && c.reason === 'forward_test_pending')

  const direction =
    dirEdge.length === 0
      ? '오를지 내릴지는 단순 기준선(과거에 오른 날 비율)보다 잘 맞히지 못합니다.'
      : `오를지 내릴지는 ${where(dirEdge)}에서 기준선(과거에 오른 날 비율)보다 잘 맞혔고, 그 밖에는 우위 없음입니다.`
  const range =
    rangeEdge.length > 0
      ? `가격 범위의 폭은 ${where(rangeEdge)}에서 조금 더 정확했습니다.`
      : rangePending
        ? '가격 범위의 폭은 과거 검증은 통과했지만 아직 실전 검증 전입니다.'
        : '가격 범위도 단순 추정과 차이가 없습니다.'
  return `${direction} ${range} 참고만 하세요.`
}
