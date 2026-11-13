/**
 * Wording and number formats for company fundamentals (DECISIONS.md D-036).
 *
 * These are published figures with a source and a date. They are not a signal, a rule check, a
 * policy check or advice, and nothing here judges a figure: no "저평가", "고평가", "싸다", "비싸다",
 * "좋다", "나쁘다", no "추천", "사세요", "파세요", "오를", "예상 수익", no gain/loss colour and no ▲▼
 * (a loss or a shrinking revenue is written with its sign in the neutral ink). Nothing here
 * computes a figure either: every number comes from `/api/fundamentals/*` as it is, and this
 * module only turns it into labels, one-line meanings and display strings. The source name and
 * the disclaimer travel with the data (`source_ko`, `disclaimer_ko`); everything else the screen
 * says about a figure is here.
 */
import type { Fundamentals, FundamentalsNote, FundamentalsStatement } from '../api/client'
import { displaySymbol } from './format'

/** Judging and advice words the fundamentals screens never use (checked by the phrase test). */
export const FUNDAMENTALS_BANNED_RE =
  /저평가|고평가|비싸|싸다|싸요|쌉니다|좋다|좋아|좋은|좋습|나쁘|나쁜|나빠|추천|사세요|파세요|오를|예상 수익|반드시|확실히|무조건|틀림없이/

export const FUNDAMENTALS_TITLE_KO = '기업 재무'
export const FUNDAMENTALS_INTRO_KO = '회사가 공개한 재무 숫자예요. 예측이나 매매 신호가 아닙니다.'
export const UNSUPPORTED_KO = '재무제표가 없는 자산이에요 (코인·ETF 등).'
export const STALE_LABEL_KO = '마지막으로 받은 값'
export const STALE_NOTE_KO = '새 값을 받지 못해 마지막으로 받은 값을 보여 줘요.'
export const NO_FIGURES_KO = '지금은 재무 숫자를 받지 못했어요.'
/** A yield of exactly zero: the provider's "no dividend was paid", said in words. */
export const NO_DIVIDEND_KO = '배당 없음'
export const SUMMARY_LABEL_KO = '사업 설명 (영문 원문)'
export const STATEMENT_TITLE_KO = '매출·영업이익·순이익'
export const NO_STATEMENT_KO = '이 기간의 손익계산서를 받지 못했어요.'
export const HELD_TITLE_KO = '보유 주식 재무 한눈에'
export const HELD_UNSUPPORTED_LABEL_KO = '재무제표가 없는 자산 (ETF 등)'
export const LOSS_SHORT_KO = '적자'
/** Home row mark beside a PER whose company's latest operating income is negative. */
export const OPERATING_LOSS_SHORT_KO = '영업적자'
/** Home row marks beside a missing operating margin, so the dash does not read as a failed fetch. */
export const NO_OPERATING_INCOME_SHORT_KO = '항목 없음'
export const ZERO_REVENUE_SHORT_KO = '매출 0'

/** A figure the provider did not give. */
export const MISSING = '–'

export type StatementPeriod = 'annual' | 'quarterly'
export const STATEMENT_PERIOD_OPTIONS: { value: StatementPeriod; label: string }[] = [
  { value: 'annual', label: '연간' },
  { value: 'quarterly', label: '분기' },
]
export const STATEMENT_PERIOD_HEADER_KO: Record<StatementPeriod, string> = {
  annual: '회계연도 끝',
  quarterly: '분기 끝',
}
export const STATEMENT_COLUMNS_KO = { revenue: '매출', operating_income: '영업이익', net_income: '순이익' } as const

export type MetricKey =
  | 'market_cap'
  | 'per_trailing'
  | 'per_forward'
  | 'pbr'
  | 'psr'
  | 'eps_trailing'
  | 'operating_margin_pct'
  | 'net_margin_pct'
  | 'roe_pct'
  | 'revenue_growth_pct'
  | 'earnings_growth_pct'
  | 'debt_to_equity_pct'
  | 'dividend_yield_pct'

/**
 * Label and one-line meaning of each figure, in everyday words. The margins and growth rates
 * name their period because the provider's differ: the operating margin is the latest quarter's,
 * the net margin the last twelve months', growth is the latest quarter against a year before.
 */
export const METRICS_KO: Record<MetricKey, { label: string; meaning: string }> = {
  market_cap: { label: '시가총액', meaning: '주가 × 발행 주식 수' },
  per_trailing: { label: 'PER', meaning: '주가가 1주당 순이익의 몇 배인지 (최근 12개월 이익)' },
  per_forward: { label: '예상 PER', meaning: '증권가 추정 이익 기준(추정)' },
  pbr: { label: 'PBR', meaning: '주가가 1주당 순자산의 몇 배인지' },
  psr: { label: 'PSR', meaning: '시가총액이 최근 12개월 매출의 몇 배인지' },
  eps_trailing: { label: 'EPS', meaning: '1주당 순이익 (최근 12개월)' },
  operating_margin_pct: { label: '영업이익률', meaning: '매출 100원 중 영업으로 남긴 돈 (최근 분기)' },
  net_margin_pct: { label: '순이익률', meaning: '매출 100원 중 세금까지 내고 남긴 돈 (최근 12개월)' },
  roe_pct: { label: 'ROE', meaning: '자기 돈으로 1년에 번 비율' },
  revenue_growth_pct: { label: '매출 성장률', meaning: '최근 분기 매출, 1년 전 같은 분기 대비' },
  earnings_growth_pct: { label: '이익 성장률', meaning: '최근 분기 이익, 1년 전 같은 분기 대비' },
  debt_to_equity_pct: { label: '부채비율', meaning: '빌린 돈이 자기 돈의 몇 %인지' },
  dividend_yield_pct: { label: '배당수익률', meaning: '1년 배당금이 주가의 몇 %인지' },
}

export const SECTION_TITLES_KO = { value: '가치', profit: '수익성·성장', safety: '안정성·배당' } as const

/**
 * What the API's note codes say beside a figure: why it is missing, or what else the response
 * shows that the figure alone does not. The operating-loss notes restate two figures (operating
 * income of the named period, twelve-month net income); they give no cause and no verdict.
 */
export const NOTE_TEXT_KO: Record<Exclude<FundamentalsNote, 'currency_mismatch'>, string> = {
  per_negative_earnings: '적자라 PER을 계산할 수 없어요',
  per_forward_negative_earnings: '추정 이익이 적자라 예상 PER을 계산할 수 없어요',
  operating_loss_net_profit:
    '최근 분기 영업이익은 적자인데 최근 12개월 순이익은 흑자예요. PER은 순이익 기준이니 영업이익도 함께 보세요.',
  operating_loss_net_profit_annual:
    '최근 회계연도 영업이익은 적자인데 최근 12개월 순이익은 흑자예요. PER은 순이익 기준이니 영업이익도 함께 보세요.',
  operating_income_not_reported: '이 회사 손익계산서에는 영업이익 항목이 없어 영업이익률을 계산하지 않았어요',
  zero_revenue_quarter: '최근 분기 매출이 0이라 영업이익률을 계산할 수 없어요',
  // Net income is operating income plus everything outside the business, minus tax: the second
  // sentence is that definition, not a guess at a cause.
  net_income_above_operating_income:
    '최근 12개월 순이익이 영업이익보다 커요. 순이익에는 영업 외 손익이 더해져 있어요.',
  net_income_above_operating_income_annual:
    '최근 회계연도 순이익이 영업이익보다 커요. 순이익에는 영업 외 손익이 더해져 있어요.',
}

/** The notes that sit on the PER line, in the order they are looked for (at most one applies). */
const PER_NOTES = ['per_negative_earnings', 'operating_loss_net_profit', 'operating_loss_net_profit_annual'] as const
/** The notes that sit on the operating margin line (at most one applies). */
const OPERATING_MARGIN_NOTES = ['operating_income_not_reported', 'zero_revenue_quarter'] as const
/** The notes that sit on the net margin line (at most one applies). Not marked on the home row. */
const NET_MARGIN_NOTES = ['net_income_above_operating_income', 'net_income_above_operating_income_annual'] as const

/** Card-level line for an ADR: statements in one currency, the quote in another. */
export function currencyMismatchNote(currency: string | null | undefined): string {
  return `재무제표 통화(${currency ?? '미확인'})와 거래 통화가 달라 일부 지표는 계산하지 않았어요`
}

// --- numbers ---------------------------------------------------------------------------------------

const present = (v: number | null | undefined): v is number => v !== null && v !== undefined && Number.isFinite(v)

const minus = (v: number) => (v < 0 ? '−' : '')

const fixed = (v: number, digits: number) =>
  v.toLocaleString('ko-KR', { minimumFractionDigits: digits, maximumFractionDigits: digits })

const parse = (text: string) => Number(text.replace(/,/g, ''))

/** Three significant figures below 100 (`1.50`, `12.3`), whole numbers from there (`3,912`). */
function threeFigures(q: number): string {
  const two = fixed(q, 2)
  if (parse(two) < 10) return two
  const one = fixed(q, 1)
  return parse(one) < 100 ? one : fixed(q, 0)
}

const UNITS: [number, string][] = [
  [1e12, '조'],
  [1e8, '억'],
  [1e4, '만'],
]

/**
 * A large amount in Korean units, without the currency: `12.3조`, `3,912억`, `1,234만`, `950`.
 * A value that rounds up to 10,000 of a unit moves to the next one (9,999.6억 is `1.00조`, not
 * `10,000억`).
 */
export function formatBigAmount(v: number | null | undefined): string {
  if (!present(v)) return MISSING
  const abs = Math.abs(v)
  for (let i = 0; i < UNITS.length; i++) {
    const [size, unit] = UNITS[i]
    if (abs < size) continue
    const carried = i > 0 && parse(fixed(abs / size, 0)) >= 10_000
    return carried
      ? `${minus(v)}${threeFigures(abs / UNITS[i - 1][0])}${UNITS[i - 1][1]}`
      : `${minus(v)}${threeFigures(abs / size)}${unit}`
  }
  const whole = Math.round(abs)
  if (whole >= 10_000) return `${minus(v)}${threeFigures(whole / 1e4)}만`
  return `${whole === 0 ? '' : minus(v)}${fixed(whole, 0)}`
}

/** The statement currency as a word: 달러 for USD, the code for anything else, nothing if unknown. */
export function currencyWord(currency: string | null | undefined): string {
  if (!currency) return ''
  return currency === 'USD' ? '달러' : currency
}

/** `1,234억 달러`, `12.3조 달러`, `4,500억 TWD`. The amount is in the statement currency. */
export function formatBigMoney(v: number | null | undefined, currency: string | null | undefined): string {
  if (!present(v)) return MISSING
  const word = currencyWord(currency)
  return word ? `${formatBigAmount(v)} ${word}` : formatBigAmount(v)
}

/** A multiple: `0.85배`, `7.42배`, `28.4배`, `1,234배`. */
export function formatMultiple(v: number | null | undefined): string {
  if (!present(v)) return MISSING
  const abs = Math.abs(v)
  return `${minus(v)}${fixed(abs, abs >= 1000 ? 0 : abs >= 10 ? 1 : 2)}배`
}

/**
 * A percent already on the 0-100 scale: `18.2%`, `−3.4%`. `signed` adds the plus for growth
 * rates (`+6.1%`). The sign is the only cue: no colour, no arrow.
 */
export function formatPercent(v: number | null | undefined, { signed = false, digits = 1 } = {}): string {
  if (!present(v)) return MISSING
  const text = fixed(Math.abs(v), digits)
  const zero = Number(text.replace(/,/g, '')) === 0
  const sign = zero ? '' : v < 0 ? '−' : signed ? '+' : ''
  return `${sign}${text}%`
}

/** A per-share amount: `$6.42`, `−$1.23`, `39.20 TWD`. */
export function formatPerShare(v: number | null | undefined, currency: string | null | undefined): string {
  if (!present(v)) return MISSING
  const text = fixed(Math.abs(v), 2)
  if (currency === 'USD') return `${minus(v)}$${text}`
  return currency ? `${minus(v)}${text} ${currency}` : `${minus(v)}${text}`
}

/** The month a period ended: `2025.09`. */
export function periodLabel(iso: string): string {
  const m = /^(\d{4})-(\d{2})/.exec(iso)
  return m ? `${m[1]}.${m[2]}` : iso
}

// --- sentences and rows ------------------------------------------------------------------------------

/** What the amounts in the statement table are counted in. */
export function statementUnitNote(currency: string | null | undefined): string {
  if (!currency) return '금액의 통화를 확인하지 못했어요.'
  return currency === 'USD' ? '금액은 미국 달러(USD) 기준이에요.' : `금액은 재무제표 통화(${currency}) 기준이에요.`
}

/** `Yahoo Finance · 2026-11-11 기준`, with `· 마지막으로 받은 값` when the refresh failed or is overdue. */
export function sourceLine(d: Pick<Fundamentals, 'source_ko' | 'as_of' | 'stale'>): string {
  const parts = [d.source_ko]
  if (d.as_of) parts.push(`${d.as_of} 기준`)
  if (d.stale) parts.push(STALE_LABEL_KO)
  return parts.join(' · ')
}

/**
 * The home summary's source line: the oldest fetch date among the listed stocks, and a word when
 * some rows show figures kept from before a failed refresh.
 */
export function heldSourceLine(d: {
  source_ko: string
  as_of: string | null
  items: Pick<Fundamentals, 'supported' | 'stale' | 'as_of'>[]
}): string {
  const parts = [d.source_ko]
  if (d.as_of) parts.push(`${d.as_of} 기준`)
  if (d.items.some((i) => i.supported && i.stale && i.as_of !== null)) parts.push(`일부는 ${STALE_LABEL_KO}`)
  return parts.join(' · ')
}

/** `AAA Inc. · Technology · Software - Application`; the parts the provider did not give are left out. */
export function profileLine(d: Pick<Fundamentals, 'name' | 'sector' | 'industry'>): string {
  return [d.name, d.sector, d.industry].filter(Boolean).join(' · ')
}

export interface MetricRow {
  key: MetricKey
  label: string
  meaning: string
  value: string
  /** A line the response attaches to this figure: why it is missing, or what to read beside it. */
  note?: string
}

export interface MetricSection {
  title: string
  rows: MetricRow[]
}

/** The three groups of the card, each figure as a display string with its label and meaning. */
export function metricSections(d: Fundamentals): MetricSection[] {
  const noted = (code: keyof typeof NOTE_TEXT_KO) => (d.notes.includes(code) ? NOTE_TEXT_KO[code] : undefined)
  const row = (key: MetricKey, value: string, note?: string): MetricRow => ({ key, ...METRICS_KO[key], value, note })
  return [
    {
      title: SECTION_TITLES_KO.value,
      rows: [
        row('market_cap', formatBigMoney(d.market_cap, d.currency)),
        row('per_trailing', formatMultiple(d.per_trailing), PER_NOTES.map(noted).find(Boolean)),
        row('per_forward', formatMultiple(d.per_forward), noted('per_forward_negative_earnings')),
        row('pbr', formatMultiple(d.pbr)),
        row('psr', formatMultiple(d.psr)),
        row('eps_trailing', formatPerShare(d.eps_trailing, d.currency)),
      ],
    },
    {
      title: SECTION_TITLES_KO.profit,
      rows: [
        row('operating_margin_pct', formatPercent(d.operating_margin_pct), OPERATING_MARGIN_NOTES.map(noted).find(Boolean)),
        row('net_margin_pct', formatPercent(d.net_margin_pct), NET_MARGIN_NOTES.map(noted).find(Boolean)),
        row('roe_pct', formatPercent(d.roe_pct)),
        row('revenue_growth_pct', formatPercent(d.revenue_growth_pct, { signed: true })),
        row('earnings_growth_pct', formatPercent(d.earnings_growth_pct, { signed: true })),
      ],
    },
    {
      title: SECTION_TITLES_KO.safety,
      rows: [
        row('debt_to_equity_pct', formatPercent(d.debt_to_equity_pct)),
        row(
          'dividend_yield_pct',
          d.dividend_yield_pct === 0 ? NO_DIVIDEND_KO : formatPercent(d.dividend_yield_pct, { digits: 2 }),
        ),
      ],
    },
  ]
}

export interface StatementLine {
  period: string
  revenue: string
  operating_income: string
  net_income: string
}

/** The income statement rows as display strings, newest first as the API sends them. */
export function statementLines(rows: FundamentalsStatement[]): StatementLine[] {
  return rows.map((r) => ({
    period: periodLabel(r.period_end),
    revenue: formatBigAmount(r.revenue),
    operating_income: formatBigAmount(r.operating_income),
    net_income: formatBigAmount(r.net_income),
  }))
}

export interface HeldCell {
  label: string
  value: string
}

export interface HeldRow {
  symbol: string
  ticker: string
  name?: string
  cells: HeldCell[]
  /** Nothing to show for this stock: the refresh failed and no earlier figures are stored. */
  missing: boolean
}

/** Home summary: one line per held stock that has statements (PER, PBR, operating margin, revenue growth). */
export function heldRows(items: Fundamentals[]): HeldRow[] {
  return items
    .filter((d) => d.supported)
    .map((d) => {
      const ticker = displaySymbol(d.symbol)
      const per = formatMultiple(d.per_trailing)
      // A word, not a colour: the PER alone would not show either of these.
      const perMark = d.notes.includes('per_negative_earnings')
        ? LOSS_SHORT_KO
        : d.notes.includes('operating_loss_net_profit') || d.notes.includes('operating_loss_net_profit_annual')
          ? OPERATING_LOSS_SHORT_KO
          : undefined
      const margin = formatPercent(d.operating_margin_pct)
      const marginMark = d.notes.includes('operating_income_not_reported')
        ? NO_OPERATING_INCOME_SHORT_KO
        : d.notes.includes('zero_revenue_quarter')
          ? ZERO_REVENUE_SHORT_KO
          : undefined
      return {
        symbol: d.symbol,
        ticker,
        name: d.name && d.name !== d.symbol ? d.name : undefined,
        missing: d.as_of === null,
        cells: [
          { label: METRICS_KO.per_trailing.label, value: perMark ? `${per} (${perMark})` : per },
          { label: METRICS_KO.pbr.label, value: formatMultiple(d.pbr) },
          { label: METRICS_KO.operating_margin_pct.label, value: marginMark ? `${margin} (${marginMark})` : margin },
          { label: METRICS_KO.revenue_growth_pct.label, value: formatPercent(d.revenue_growth_pct, { signed: true }) },
        ],
      }
    })
}

/** Held stocks without statements (ETFs), as tickers for the footnote. */
export function heldUnsupported(items: Fundamentals[]): string[] {
  return items.filter((d) => !d.supported).map((d) => displaySymbol(d.symbol))
}
