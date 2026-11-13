import { describe, expect, it } from 'vitest'

import type { Fundamentals } from '../api/client'
import {
  currencyMismatchNote,
  currencyWord,
  formatBigAmount,
  formatBigMoney,
  formatMultiple,
  formatPercent,
  formatPerShare,
  heldRows,
  heldSourceLine,
  heldUnsupported,
  metricSections,
  MISSING,
  periodLabel,
  profileLine,
  sourceLine,
  statementLines,
  statementUnitNote,
} from './fundamentals'
import { AAA, ADR, BANK, ETF, FAILED, LOSS, NON_OPERATING, OP_LOSS } from './fundamentals.fixtures'

describe('big amounts in Korean units', () => {
  it('picks 조, 억 or 만 and keeps three figures below 100 of a unit', () => {
    expect(formatBigAmount(3.4e12)).toBe('3.40조')
    expect(formatBigAmount(1.23e13)).toBe('12.3조')
    expect(formatBigAmount(1.234e15)).toBe('1,234조')
    expect(formatBigAmount(3.912e11)).toBe('3,912억')
    expect(formatBigAmount(1.23e9)).toBe('12.3억')
    expect(formatBigAmount(1.5e8)).toBe('1.50억')
    expect(formatBigAmount(12_340_000)).toBe('1,234만')
    expect(formatBigAmount(12_340)).toBe('1.23만')
    expect(formatBigAmount(950)).toBe('950')
  })

  it('moves to the next unit when rounding reaches 10,000 and never prints 100.0', () => {
    expect(formatBigAmount(9.9996e11)).toBe('1.00조')
    expect(formatBigAmount(9.9996e7)).toBe('1.00억')
    expect(formatBigAmount(9999.6)).toBe('1.00만')
    expect(formatBigAmount(99.96e8)).toBe('100억')
    expect(formatBigAmount(9.996e8)).toBe('10.0억')
  })

  it('writes a loss with a real minus, zero without a sign, and a missing value as a dash', () => {
    expect(formatBigAmount(-2.5e9)).toBe('−25.0억')
    expect(formatBigAmount(-1.1e12)).toBe('−1.10조')
    expect(formatBigAmount(0)).toBe('0')
    expect(formatBigAmount(-0.4)).toBe('0')
    expect(formatBigAmount(null)).toBe(MISSING)
    expect(formatBigAmount(undefined)).toBe(MISSING)
    expect(formatBigAmount(Number.NaN)).toBe(MISSING)
    expect(formatBigAmount(Number.POSITIVE_INFINITY)).toBe(MISSING)
  })

  it('names the statement currency: 달러 for USD, the code otherwise, nothing when unknown', () => {
    expect(currencyWord('USD')).toBe('달러')
    expect(currencyWord('TWD')).toBe('TWD')
    expect(currencyWord(null)).toBe('')
    expect(formatBigMoney(3.4e12, 'USD')).toBe('3.40조 달러')
    expect(formatBigMoney(1.234e11, 'USD')).toBe('1,234억 달러')
    expect(formatBigMoney(4.5e11, 'TWD')).toBe('4,500억 TWD')
    expect(formatBigMoney(1e9, null)).toBe('10.0억')
    expect(formatBigMoney(null, 'USD')).toBe(MISSING)
  })
})

describe('multiples, percents and per-share amounts', () => {
  it('writes a multiple with 배', () => {
    expect(formatMultiple(0.85)).toBe('0.85배')
    expect(formatMultiple(7.416)).toBe('7.42배')
    expect(formatMultiple(28.44)).toBe('28.4배')
    expect(formatMultiple(1234.4)).toBe('1,234배')
    expect(formatMultiple(-3.2)).toBe('−3.20배')
    expect(formatMultiple(0)).toBe('0.00배')
    expect(formatMultiple(null)).toBe(MISSING)
    expect(formatMultiple(undefined)).toBe(MISSING)
  })

  it('writes a percent with its sign only; the plus is for growth rates', () => {
    expect(formatPercent(18.24)).toBe('18.2%')
    expect(formatPercent(151.9)).toBe('151.9%')
    expect(formatPercent(-3.44)).toBe('−3.4%')
    expect(formatPercent(6.1, { signed: true })).toBe('+6.1%')
    expect(formatPercent(-7.25, { signed: true })).toBe('−7.3%')
    expect(formatPercent(0, { signed: true })).toBe('0.0%')
    // Rounds to zero: no "−0.0%".
    expect(formatPercent(-0.04)).toBe('0.0%')
    expect(formatPercent(0.43, { digits: 2 })).toBe('0.43%')
    expect(formatPercent(1234.56)).toBe('1,234.6%')
    expect(formatPercent(null)).toBe(MISSING)
    expect(formatPercent(Number.NaN)).toBe(MISSING)
  })

  it('writes a per-share amount in the statement currency', () => {
    expect(formatPerShare(6.42, 'USD')).toBe('$6.42')
    expect(formatPerShare(-1.234, 'USD')).toBe('−$1.23')
    expect(formatPerShare(39.2, 'TWD')).toBe('39.20 TWD')
    expect(formatPerShare(6.42, null)).toBe('6.42')
    expect(formatPerShare(null, 'USD')).toBe(MISSING)
  })

  it('labels a period by the month it ended', () => {
    expect(periodLabel('2025-09-27')).toBe('2025.09')
    expect(periodLabel('2026-06-30')).toBe('2026.06')
    expect(periodLabel('nonsense')).toBe('nonsense')
  })
})

describe('rows and sentences', () => {
  const value = (d: Fundamentals, key: string) =>
    metricSections(d)
      .flatMap((s) => s.rows)
      .find((r) => r.key === key)

  it('groups thirteen figures in three sections, each with a label and a meaning', () => {
    const sections = metricSections(AAA)
    expect(sections.map((s) => s.title)).toEqual(['가치', '수익성·성장', '안정성·배당'])
    expect(sections.map((s) => s.rows.map((r) => r.key))).toEqual([
      ['market_cap', 'per_trailing', 'per_forward', 'pbr', 'psr', 'eps_trailing'],
      ['operating_margin_pct', 'net_margin_pct', 'roe_pct', 'revenue_growth_pct', 'earnings_growth_pct'],
      ['debt_to_equity_pct', 'dividend_yield_pct'],
    ])
    for (const row of sections.flatMap((s) => s.rows)) {
      expect(row.label).not.toBe('')
      expect(row.meaning).not.toBe('')
    }
    expect(sections.flatMap((s) => s.rows).map((r) => r.value)).toEqual([
      '3.40조 달러',
      '28.4배',
      '24.1배',
      '45.1배',
      '8.70배',
      '$6.42',
      '31.2%',
      '24.3%',
      '151.9%',
      '+6.1%',
      '−3.4%',
      '154.5%',
      '0.43%',
    ])
  })

  it('says which period a margin or a growth rate is for', () => {
    expect(value(AAA, 'operating_margin_pct')?.meaning).toContain('최근 분기')
    expect(value(AAA, 'net_margin_pct')?.meaning).toContain('최근 12개월')
    expect(value(AAA, 'revenue_growth_pct')?.meaning).toBe('최근 분기 매출, 1년 전 같은 분기 대비')
    expect(value(AAA, 'per_forward')?.meaning).toBe('증권가 추정 이익 기준(추정)')
  })

  it('gives the reason beside a missing PER only when the response says why', () => {
    expect(value(LOSS, 'per_trailing')).toMatchObject({ value: MISSING, note: '적자라 PER을 계산할 수 없어요' })
    expect(value(LOSS, 'per_forward')).toMatchObject({
      value: MISSING,
      note: '추정 이익이 적자라 예상 PER을 계산할 수 없어요',
    })
    expect(value(LOSS, 'eps_trailing')?.value).toBe('−$1.23')
    expect(value(LOSS, 'operating_margin_pct')?.value).toBe('−18.3%')
    expect(value(LOSS, 'earnings_growth_pct')).toMatchObject({ value: MISSING, note: undefined })
    // A yield of exactly zero is said in words; an unknown one stays a dash.
    expect(value(LOSS, 'dividend_yield_pct')?.value).toBe('배당 없음')
    expect(value({ ...AAA, dividend_yield_pct: null }, 'dividend_yield_pct')?.value).toBe(MISSING)
    // Missing without a stated reason: a dash and nothing else.
    expect(value({ ...AAA, per_trailing: null }, 'per_trailing')).toMatchObject({ value: MISSING, note: undefined })
    expect(value(AAA, 'per_trailing')?.note).toBeUndefined()
  })

  it('puts the operating-loss note on the PER line, beside a PER that is there', () => {
    const quarter = value(OP_LOSS, 'per_trailing')
    expect(quarter?.value).toBe('20.1배')
    expect(quarter?.note).toBe(
      '최근 분기 영업이익은 적자인데 최근 12개월 순이익은 흑자예요. PER은 순이익 기준이니 영업이익도 함께 보세요.',
    )
    const annual = value({ ...OP_LOSS, notes: ['operating_loss_net_profit_annual'] }, 'per_trailing')
    expect(annual?.note).toBe(
      '최근 회계연도 영업이익은 적자인데 최근 12개월 순이익은 흑자예요. PER은 순이익 기준이니 영업이익도 함께 보세요.',
    )
    // The note belongs to the PER only; the other rows of the same company carry none.
    const others = metricSections(OP_LOSS)
      .flatMap((s) => s.rows)
      .filter((r) => r.key !== 'per_trailing')
    expect(others.every((r) => r.note === undefined)).toBe(true)
    expect(value(OP_LOSS, 'operating_margin_pct')?.value).toBe('−35.2%')
  })

  it('explains a missing operating margin only when the statements show the reason', () => {
    expect(value(BANK, 'operating_margin_pct')).toMatchObject({
      value: MISSING,
      note: '이 회사 손익계산서에는 영업이익 항목이 없어 영업이익률을 계산하지 않았어요',
    })
    expect(value({ ...BANK, notes: ['zero_revenue_quarter'] }, 'operating_margin_pct')).toMatchObject({
      value: MISSING,
      note: '최근 분기 매출이 0이라 영업이익률을 계산할 수 없어요',
    })
    expect(value({ ...BANK, notes: [] }, 'operating_margin_pct')).toMatchObject({ value: MISSING, note: undefined })
    // The statement column stays a dash; the other figures of a bank are shown as usual.
    expect(statementLines(BANK.quarterly)[0]).toEqual({
      period: '2026.09',
      revenue: '460억',
      operating_income: MISSING,
      net_income: '140억',
    })
    expect(value(BANK, 'net_margin_pct')?.value).toBe('24.3%')
    expect(value(BANK, 'per_trailing')?.note).toBeUndefined()
  })

  it('puts the "net income above operating income" note on the net margin line only', () => {
    const twelveMonths = value(NON_OPERATING, 'net_margin_pct')
    expect(twelveMonths?.value).toBe('52.4%')
    expect(twelveMonths?.note).toBe('최근 12개월 순이익이 영업이익보다 커요. 순이익에는 영업 외 손익이 더해져 있어요.')
    const year = value({ ...NON_OPERATING, notes: ['net_income_above_operating_income_annual'] }, 'net_margin_pct')
    expect(year?.note).toBe('최근 회계연도 순이익이 영업이익보다 커요. 순이익에는 영업 외 손익이 더해져 있어요.')
    // A margin above 100% is written as it is, with the same note.
    expect(value({ ...NON_OPERATING, net_margin_pct: 134.56 }, 'net_margin_pct')).toMatchObject({
      value: '134.6%',
      note: twelveMonths?.note,
    })
    const others = metricSections(NON_OPERATING)
      .flatMap((s) => s.rows)
      .filter((r) => r.key !== 'net_margin_pct')
    expect(others.every((r) => r.note === undefined)).toBe(true)
    expect(value(AAA, 'net_margin_pct')?.note).toBeUndefined()
    // The home row carries no mark for it: its four cells are the same as without the note.
    expect(heldRows([NON_OPERATING])[0].cells).toEqual(heldRows([{ ...NON_OPERATING, notes: [] }])[0].cells)
    // It can stand beside the PER-line note of a company whose newest quarter lost money.
    const both: Fundamentals = { ...NON_OPERATING, notes: ['operating_loss_net_profit', 'net_income_above_operating_income'] }
    expect(value(both, 'per_trailing')?.note).toMatch(/^최근 분기 영업이익은 적자인데/)
    expect(value(both, 'net_margin_pct')?.note).toMatch(/^최근 12개월 순이익이 영업이익보다 커요/)
  })

  it('leaves the mixed-currency figures of an ADR as dashes and says why once', () => {
    expect(value(ADR, 'market_cap')?.value).toBe(MISSING)
    expect(value(ADR, 'pbr')?.value).toBe(MISSING)
    expect(value(ADR, 'eps_trailing')?.value).toBe(MISSING)
    expect(value(ADR, 'per_trailing')?.value).toBe('28.4배')
    expect(currencyMismatchNote('TWD')).toBe('재무제표 통화(TWD)와 거래 통화가 달라 일부 지표는 계산하지 않았어요')
    expect(statementUnitNote('TWD')).toBe('금액은 재무제표 통화(TWD) 기준이에요.')
    expect(statementUnitNote('USD')).toBe('금액은 미국 달러(USD) 기준이에요.')
    expect(statementUnitNote(null)).toBe('금액의 통화를 확인하지 못했어요.')
  })

  it('turns statement rows into display strings, newest first as sent', () => {
    expect(statementLines(AAA.annual)).toEqual([
      { period: '2025.09', revenue: '4,161억', operating_income: '1,331억', net_income: '1,120억' },
      { period: '2024.09', revenue: '3,910억', operating_income: '1,232억', net_income: '937억' },
    ])
    expect(statementLines(LOSS.annual)[0]).toEqual({
      period: '2025.12',
      revenue: '200억',
      operating_income: '−31.0억',
      net_income: '−25.0억',
    })
    expect(statementLines([{ period_end: '2025-12-31', revenue: null, operating_income: null, net_income: 0 }])[0]).toEqual({
      period: '2025.12',
      revenue: MISSING,
      operating_income: MISSING,
      net_income: '0',
    })
    expect(statementLines([])).toEqual([])
  })

  it('writes the source with its date, and says when the value is the last one received', () => {
    expect(sourceLine(AAA)).toBe('Yahoo Finance · 2026-11-11 기준')
    expect(sourceLine({ ...AAA, stale: true })).toBe('Yahoo Finance · 2026-11-11 기준 · 마지막으로 받은 값')
    expect(sourceLine({ source_ko: 'Yahoo Finance', as_of: null, stale: false })).toBe('Yahoo Finance')
    expect(profileLine(AAA)).toBe('AAA Inc. · Technology · Software - Application')
    expect(profileLine({ name: null, sector: 'Technology', industry: null })).toBe('Technology')
    expect(profileLine({ name: null, sector: null, industry: null })).toBe('')
  })

  it('builds the home rows from the stocks that have statements and names the rest', () => {
    const items = [AAA, LOSS, ETF, { ...FAILED, name: 'DDD' }]
    const rows = heldRows(items)
    expect(rows.map((r) => r.symbol)).toEqual(['AAA', 'BBB', 'DDD'])
    expect(rows[0]).toMatchObject({ ticker: 'AAA', name: 'AAA Inc.', missing: false })
    expect(rows[0].cells).toEqual([
      { label: 'PER', value: '28.4배' },
      { label: 'PBR', value: '45.1배' },
      { label: '영업이익률', value: '31.2%' },
      { label: '매출 성장률', value: '+6.1%' },
    ])
    expect(rows[1].cells[0]).toEqual({ label: 'PER', value: '– (적자)' })
    // A PER beside an operating loss gets a word, in either of its two forms.
    expect(heldRows([OP_LOSS])[0].cells[0]).toEqual({ label: 'PER', value: '20.1배 (영업적자)' })
    expect(heldRows([{ ...OP_LOSS, notes: ['operating_loss_net_profit_annual'] }])[0].cells[0].value).toBe('20.1배 (영업적자)')
    // A missing operating margin with a known reason says it in a word; without one, a dash.
    expect(heldRows([BANK])[0].cells[2]).toEqual({ label: '영업이익률', value: '– (항목 없음)' })
    expect(heldRows([{ ...BANK, notes: ['zero_revenue_quarter'] }])[0].cells[2].value).toBe('– (매출 0)')
    expect(heldRows([{ ...BANK, notes: [] }])[0].cells[2].value).toBe(MISSING)
    expect(rows[1].cells[3]).toEqual({ label: '매출 성장률', value: '−7.3%' })
    // A name that only repeats the ticker is dropped; no stored figures marks the row.
    expect(rows[2]).toMatchObject({ name: undefined, missing: true })
    expect(heldUnsupported(items)).toEqual(['SPY'])
    expect(heldRows([])).toEqual([])
    expect(heldSourceLine({ source_ko: 'Yahoo Finance', as_of: '2026-11-10', items })).toBe('Yahoo Finance · 2026-11-10 기준')
    expect(heldSourceLine({ source_ko: 'Yahoo Finance', as_of: '2026-11-10', items: [AAA, { ...LOSS, stale: true }] })).toBe(
      'Yahoo Finance · 2026-11-10 기준 · 일부는 마지막으로 받은 값',
    )
    expect(heldSourceLine({ source_ko: 'Yahoo Finance', as_of: null, items: [] })).toBe('Yahoo Finance')
  })
})
