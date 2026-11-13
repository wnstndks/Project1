import { describe, expect, it } from 'vitest'

import {
  currencyMismatchNote,
  FUNDAMENTALS_BANNED_RE,
  FUNDAMENTALS_INTRO_KO,
  FUNDAMENTALS_TITLE_KO,
  HELD_TITLE_KO,
  HELD_UNSUPPORTED_LABEL_KO,
  heldRows,
  heldSourceLine,
  LOSS_SHORT_KO,
  METRICS_KO,
  metricSections,
  NO_DIVIDEND_KO,
  NO_FIGURES_KO,
  NO_OPERATING_INCOME_SHORT_KO,
  NO_STATEMENT_KO,
  NOTE_TEXT_KO,
  OPERATING_LOSS_SHORT_KO,
  profileLine,
  SECTION_TITLES_KO,
  sourceLine,
  STALE_LABEL_KO,
  STALE_NOTE_KO,
  STATEMENT_COLUMNS_KO,
  STATEMENT_PERIOD_HEADER_KO,
  STATEMENT_PERIOD_OPTIONS,
  STATEMENT_TITLE_KO,
  statementLines,
  statementUnitNote,
  SUMMARY_LABEL_KO,
  UNSUPPORTED_KO,
  ZERO_REVENUE_SHORT_KO,
} from './fundamentals'
import { AAA, ADR, BANK, DISCLAIMER_KO, FAILED, LOSS, NON_OPERATING, OP_LOSS } from './fundamentals.fixtures'

/** The coach's advice words (D-033), which the fundamentals wording must not use either. */
const ADVICE_RE = /추천|사세요|파세요|오를|예상 수익/

const fixed = [
  FUNDAMENTALS_TITLE_KO,
  FUNDAMENTALS_INTRO_KO,
  UNSUPPORTED_KO,
  STALE_LABEL_KO,
  STALE_NOTE_KO,
  NO_FIGURES_KO,
  NO_DIVIDEND_KO,
  SUMMARY_LABEL_KO,
  STATEMENT_TITLE_KO,
  NO_STATEMENT_KO,
  HELD_TITLE_KO,
  HELD_UNSUPPORTED_LABEL_KO,
  LOSS_SHORT_KO,
  OPERATING_LOSS_SHORT_KO,
  NO_OPERATING_INCOME_SHORT_KO,
  ZERO_REVENUE_SHORT_KO,
  ...Object.values(METRICS_KO).flatMap((m) => [m.label, m.meaning]),
  ...Object.values(SECTION_TITLES_KO),
  ...Object.values(NOTE_TEXT_KO),
  ...Object.values(STATEMENT_COLUMNS_KO),
  ...Object.values(STATEMENT_PERIOD_HEADER_KO),
  ...STATEMENT_PERIOD_OPTIONS.map((o) => o.label),
]

const generated = [
  ...[
    AAA,
    LOSS,
    OP_LOSS,
    { ...OP_LOSS, notes: ['operating_loss_net_profit_annual' as const] },
    BANK,
    { ...BANK, notes: ['zero_revenue_quarter' as const] },
    NON_OPERATING,
    { ...NON_OPERATING, notes: ['net_income_above_operating_income_annual' as const] },
    ADR,
    FAILED,
  ].flatMap((d) => [
    ...metricSections(d).flatMap((s) => [s.title, ...s.rows.flatMap((r) => [r.label, r.meaning, r.value, r.note ?? ''])]),
    ...statementLines(d.annual).flatMap((l) => Object.values(l)),
    ...statementLines(d.quarterly).flatMap((l) => Object.values(l)),
    statementUnitNote(d.currency),
    currencyMismatchNote(d.currency),
    sourceLine(d),
    sourceLine({ ...d, stale: true }),
    profileLine(d),
  ]),
  ...heldRows([AAA, LOSS, OP_LOSS, BANK, { ...BANK, notes: ['zero_revenue_quarter'] }, ADR, FAILED]).flatMap((r) =>
    r.cells.flatMap((c) => [c.label, c.value]),
  ),
  heldSourceLine({ source_ko: 'Yahoo Finance', as_of: '2026-11-11', items: [AAA, { ...LOSS, stale: true }] }),
]

describe('fundamentals wording', () => {
  it('never judges a figure and never gives advice, in any fixed text', () => {
    expect(fixed.length).toBeGreaterThan(40)
    for (const s of fixed) {
      expect(s, s).not.toMatch(FUNDAMENTALS_BANNED_RE)
      expect(s, s).not.toMatch(ADVICE_RE)
      expect(s, s).not.toMatch(/[▲▼]/)
    }
  })

  it('never judges a figure in any generated row, cell or sentence, for a profit, a loss and an ADR', () => {
    expect(generated.length).toBeGreaterThan(100)
    for (const s of generated) {
      expect(s, s).not.toMatch(FUNDAMENTALS_BANNED_RE)
      expect(s, s).not.toMatch(ADVICE_RE)
      expect(s, s).not.toMatch(/[▲▼]/)
    }
  })

  it('lets the disclaimer through and catches a verdict', () => {
    // The server's disclaimer says the figures cannot decide a trade; that is not a verdict.
    expect(DISCLAIMER_KO).not.toMatch(FUNDAMENTALS_BANNED_RE)
    expect(DISCLAIMER_KO).toContain('투자 조언이 아닙니다')
    expect(DISCLAIMER_KO).toContain('이 숫자만으로 매수·매도를 판단할 수 없습니다')
    for (const verdict of [
      '저평가 구간',
      '고평가',
      '싸다',
      '지금 싸요',
      '비싸다',
      '비싼 편은 아니지만 비싸요',
      '좋다',
      '실적이 좋아요',
      '좋은 회사',
      '나쁘다',
      '나쁜 숫자',
      '추천',
      '사세요',
      '파세요',
      '더 오를',
      '예상 수익',
      '무조건',
    ]) {
      expect(verdict, verdict).toMatch(FUNDAMENTALS_BANNED_RE)
    }
  })

  it('says the plain-language meanings and the reasons the plan fixed', () => {
    expect(METRICS_KO.per_trailing.meaning).toContain('주가가 1주당 순이익의 몇 배인지')
    expect(METRICS_KO.pbr.meaning).toBe('주가가 1주당 순자산의 몇 배인지')
    expect(METRICS_KO.operating_margin_pct.meaning).toContain('매출 100원 중 영업으로 남긴 돈')
    expect(METRICS_KO.roe_pct.meaning).toBe('자기 돈으로 1년에 번 비율')
    expect(METRICS_KO.per_forward).toEqual({ label: '예상 PER', meaning: '증권가 추정 이익 기준(추정)' })
    expect(NOTE_TEXT_KO.per_negative_earnings).toBe('적자라 PER을 계산할 수 없어요')
    // The operating-loss notes name the two figures and their periods, and stop there: no cause.
    for (const [code, period] of [
      ['operating_loss_net_profit', '최근 분기'],
      ['operating_loss_net_profit_annual', '최근 회계연도'],
    ] as const) {
      expect(NOTE_TEXT_KO[code]).toContain(`${period} 영업이익은 적자`)
      expect(NOTE_TEXT_KO[code]).toContain('최근 12개월 순이익은 흑자')
      expect(NOTE_TEXT_KO[code]).not.toMatch(/때문|덕분|영업 외/)
    }
    // Net income above operating income: the period, the comparison, and what net income is by
    // definition. No "because", and nothing about whether that is welcome.
    for (const [code, period] of [
      ['net_income_above_operating_income', '최근 12개월'],
      ['net_income_above_operating_income_annual', '최근 회계연도'],
    ] as const) {
      expect(NOTE_TEXT_KO[code]).toBe(`${period} 순이익이 영업이익보다 커요. 순이익에는 영업 외 손익이 더해져 있어요.`)
      expect(NOTE_TEXT_KO[code]).not.toMatch(/때문|덕분|일회성|주의/)
    }
    // Every note code the API can send has a text (the ADR one is a card-level line).
    expect(Object.keys(NOTE_TEXT_KO)).toHaveLength(8)
    expect(UNSUPPORTED_KO).toBe('재무제표가 없는 자산이에요 (코인·ETF 등).')
    expect(STALE_LABEL_KO).toBe('마지막으로 받은 값')
  })
})
