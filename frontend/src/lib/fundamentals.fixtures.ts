/** Test data for the fundamentals screens. Synthetic companies only (public repo): round numbers. */
import type { Fundamentals } from '../api/client'

export const DISCLAIMER_KO =
  '공개된 재무 숫자이며 투자 조언이 아닙니다. 이 숫자만으로 매수·매도를 판단할 수 없습니다. 업종마다 기준이 다릅니다.'

/** A profitable company reporting in dollars. */
export const AAA: Fundamentals = {
  symbol: 'AAA',
  supported: true,
  as_of: '2026-11-11',
  stale: false,
  error: null,
  currency: 'USD',
  name: 'AAA Inc.',
  sector: 'Technology',
  industry: 'Software - Application',
  summary: 'AAA Inc. is a synthetic company used for offline demos and tests.',
  market_cap: 3.4e12,
  per_trailing: 28.44,
  per_forward: 24.1,
  pbr: 45.12,
  psr: 8.7,
  eps_trailing: 6.42,
  eps_forward: 7.5,
  book_value_per_share: 4.05,
  dividend_yield_pct: 0.43,
  operating_margin_pct: 31.2,
  net_margin_pct: 24.3,
  roe_pct: 151.9,
  revenue_growth_pct: 6.1,
  earnings_growth_pct: -3.4,
  debt_to_equity_pct: 154.5,
  annual: [
    { period_end: '2025-09-30', revenue: 4.161e11, operating_income: 1.331e11, net_income: 1.12e11 },
    { period_end: '2024-09-30', revenue: 3.91e11, operating_income: 1.232e11, net_income: 9.37e10 },
  ],
  quarterly: [{ period_end: '2026-06-30', revenue: 9.4e10, operating_income: 2.82e10, net_income: 2.34e10 }],
  notes: [],
  source_ko: 'Yahoo Finance',
  disclaimer_ko: DISCLAIMER_KO,
}

/** A company that lost money over the last twelve months: no PER, negative margins, no dividend. */
export const LOSS: Fundamentals = {
  ...AAA,
  symbol: 'BBB',
  name: 'BBB Inc.',
  per_trailing: null,
  per_forward: null,
  eps_trailing: -1.234,
  eps_forward: -0.5,
  dividend_yield_pct: 0,
  operating_margin_pct: -18.26,
  net_margin_pct: -12.5,
  roe_pct: -30.04,
  revenue_growth_pct: -7.25,
  earnings_growth_pct: null,
  annual: [{ period_end: '2025-12-31', revenue: 2e10, operating_income: -3.1e9, net_income: -2.5e9 }],
  quarterly: [],
  notes: ['per_negative_earnings', 'per_forward_negative_earnings'],
}

/**
 * A PER like any other (twelve-month net income is positive) while the latest quarter's
 * operating income is negative: the response points at it with a note.
 */
export const OP_LOSS: Fundamentals = {
  ...AAA,
  symbol: 'EEE',
  name: 'EEE Inc.',
  per_trailing: 20.1,
  operating_margin_pct: -35.2,
  quarterly: [{ period_end: '2026-06-30', revenue: 9.4e10, operating_income: -3.31e10, net_income: 1.2e10 }],
  notes: ['operating_loss_net_profit'],
}

/**
 * Net income above operating income over twelve months (gains outside the business): the net
 * margin is larger than the operating margin, and the response points at it with a note.
 */
export const NON_OPERATING: Fundamentals = {
  ...AAA,
  symbol: 'GGG',
  name: 'GGG Inc.',
  operating_margin_pct: 31.2,
  net_margin_pct: 52.4,
  quarterly: [
    { period_end: '2026-06-30', revenue: 9.4e10, operating_income: 2.93e10, net_income: 4.93e10 },
    { period_end: '2026-03-31', revenue: 9.0e10, operating_income: 2.8e10, net_income: 4.7e10 },
    { period_end: '2025-12-31', revenue: 8.8e10, operating_income: 2.7e10, net_income: 4.6e10 },
    { period_end: '2025-09-30', revenue: 8.5e10, operating_income: 2.6e10, net_income: 4.5e10 },
  ],
  notes: ['net_income_above_operating_income'],
}

/** A bank: its income statement has no operating income line, so there is no operating margin. */
export const BANK: Fundamentals = {
  ...AAA,
  symbol: 'FFF',
  name: 'FFF Bancorp',
  sector: 'Financial Services',
  industry: 'Banks - Diversified',
  operating_margin_pct: null,
  annual: [{ period_end: '2025-12-31', revenue: 1.8e11, operating_income: null, net_income: 5.7e10 }],
  quarterly: [{ period_end: '2026-09-30', revenue: 4.6e10, operating_income: null, net_income: 1.4e10 }],
  notes: ['operating_income_not_reported'],
}

/** An ADR: statements in TWD, so the figures that mix the two currencies are left out. */
export const ADR: Fundamentals = {
  ...AAA,
  symbol: 'CCC',
  name: 'CCC Co.',
  currency: 'TWD',
  market_cap: null,
  pbr: null,
  psr: null,
  eps_trailing: null,
  eps_forward: null,
  book_value_per_share: null,
  annual: [{ period_end: '2025-12-31', revenue: 2.9e12, operating_income: 1.3e12, net_income: 1.1e12 }],
  notes: ['currency_mismatch'],
}

const NO_FIGURES = {
  currency: null,
  name: null,
  sector: null,
  industry: null,
  summary: null,
  market_cap: null,
  per_trailing: null,
  per_forward: null,
  pbr: null,
  psr: null,
  eps_trailing: null,
  eps_forward: null,
  book_value_per_share: null,
  dividend_yield_pct: null,
  operating_margin_pct: null,
  net_margin_pct: null,
  roe_pct: null,
  revenue_growth_pct: null,
  earnings_growth_pct: null,
  debt_to_equity_pct: null,
  annual: [],
  quarterly: [],
  notes: [],
  source_ko: 'Yahoo Finance',
  disclaimer_ko: DISCLAIMER_KO,
} satisfies Partial<Fundamentals>

/** A coin: no statements, answered without a lookup. */
export const COIN: Fundamentals = {
  ...NO_FIGURES,
  symbol: 'BTC-USD',
  supported: false,
  as_of: null,
  stale: false,
  error: null,
}

/** An ETF: the provider looked it up and found no statements. */
export const ETF: Fundamentals = { ...COIN, symbol: 'SPY', as_of: '2026-11-11' }

/** A stock whose first lookup failed: nothing stored, the error says why. */
export const FAILED: Fundamentals = {
  ...NO_FIGURES,
  symbol: 'DDD',
  supported: true,
  as_of: null,
  stale: true,
  error: 'yfinance info failed for DDD: timeout',
}
