import { useState } from 'react'

import type { Fundamentals } from '../api/client'
import { useFundamentals } from '../api/hooks'
import {
  currencyMismatchNote,
  FUNDAMENTALS_INTRO_KO,
  FUNDAMENTALS_TITLE_KO,
  metricSections,
  NO_FIGURES_KO,
  NO_STATEMENT_KO,
  profileLine,
  sourceLine,
  STALE_NOTE_KO,
  STATEMENT_COLUMNS_KO,
  STATEMENT_PERIOD_HEADER_KO,
  STATEMENT_PERIOD_OPTIONS,
  STATEMENT_TITLE_KO,
  statementLines,
  statementUnitNote,
  SUMMARY_LABEL_KO,
  UNSUPPORTED_KO,
  type MetricRow,
  type StatementPeriod,
} from '../lib/fundamentals'
import { Card, Disclosure, ErrorBox, InfoRow, SegmentedControl, Skeleton } from './ui'

/**
 * "기업 재무" on the asset page (D-036): published figures of the company with their source and
 * date. Facts only: every value is in the neutral ink with its sign, never a gain/loss colour, an
 * arrow or a verdict, and the card says the figures alone cannot decide a trade. An asset without
 * statements (a coin, an ETF) gets one line saying so.
 */
export function FundamentalsCard({ symbol }: { symbol: string }) {
  const query = useFundamentals(symbol)
  return (
    <Card title={FUNDAMENTALS_TITLE_KO}>
      {query.error ? <ErrorBox error={query.error} /> : !query.data ? <Loading /> : <Body d={query.data} />}
    </Card>
  )
}

function Loading() {
  return (
    <div className="space-y-3" aria-busy="true">
      <p role="status" className="sr-only">
        불러오는 중
      </p>
      <Skeleton className="h-4 w-56" />
      <Skeleton className="h-44" />
      <Skeleton className="h-28" />
    </div>
  )
}

function Body({ d }: { d: Fundamentals }) {
  if (!d.supported) return <p className="text-sm text-ink-2">{UNSUPPORTED_KO}</p>
  if (d.as_of === null) {
    return (
      <p className="text-sm text-ink-2">
        {NO_FIGURES_KO}
        {d.error && <span className="ml-1 text-xs text-muted">({d.error})</span>}
      </p>
    )
  }
  const profile = profileLine(d)
  return (
    <div className="space-y-5">
      <div>
        {profile && <p className="text-[15px] font-medium text-ink">{profile}</p>}
        <p className="mt-1 text-xs text-muted">{FUNDAMENTALS_INTRO_KO}</p>
      </div>
      {d.stale && (
        <p role="status" className="rounded-xl bg-fill px-3 py-2 text-xs text-ink-2">
          {STALE_NOTE_KO}
          {d.error && <span className="ml-1 text-muted">({d.error})</span>}
        </p>
      )}
      {d.notes.includes('currency_mismatch') && (
        <p className="rounded-xl bg-fill px-3 py-2 text-xs text-ink-2">{currencyMismatchNote(d.currency)}</p>
      )}
      {metricSections(d).map((section) => (
        <section key={section.title} aria-label={section.title}>
          <h3 className="text-[13px] font-semibold text-muted">{section.title}</h3>
          <dl className="mt-1 divide-y divide-line">
            {section.rows.map((row) => (
              <MetricLine key={row.key} row={row} />
            ))}
          </dl>
        </section>
      ))}
      <Statements d={d} />
      {d.summary && (
        <Disclosure summary={SUMMARY_LABEL_KO}>
          <p lang="en" className="text-sm leading-relaxed text-ink-2">
            {d.summary}
          </p>
        </Disclosure>
      )}
      <p className="text-xs text-muted">
        {sourceLine(d)}. {d.disclaimer_ko}
      </p>
    </div>
  )
}

/** Label with its one-line meaning (and the reason when the value is missing) left, value right. */
function MetricLine({ row }: { row: MetricRow }) {
  return (
    <InfoRow
      label={
        <>
          {row.label}
          <span className="mt-0.5 block text-xs text-muted">{row.meaning}</span>
          {row.note && <span className="mt-0.5 block text-xs text-ink-2">{row.note}</span>}
        </>
      }
      value={<span className="whitespace-nowrap text-ink">{row.value}</span>}
    />
  )
}

/** Revenue, operating income and net income by year or by quarter, newest first. */
function Statements({ d }: { d: Fundamentals }) {
  const [period, setPeriod] = useState<StatementPeriod>(d.annual.length > 0 ? 'annual' : 'quarterly')
  const lines = statementLines(d[period])
  const columns = Object.entries(STATEMENT_COLUMNS_KO) as [keyof typeof STATEMENT_COLUMNS_KO, string][]
  return (
    <section aria-label={STATEMENT_TITLE_KO}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-[13px] font-semibold text-muted">{STATEMENT_TITLE_KO}</h3>
        <SegmentedControl label="손익계산서 기간" options={STATEMENT_PERIOD_OPTIONS} value={period} onChange={setPeriod} />
      </div>
      {lines.length === 0 ? (
        <p className="mt-2 text-sm text-muted">{NO_STATEMENT_KO}</p>
      ) : (
        <>
          {/* Four short columns: fits a phone without a sideways scroll. The unit is under the table. */}
          <table className="num mt-2 w-full text-[13px]">
            <caption className="sr-only">{STATEMENT_TITLE_KO}</caption>
            <thead>
              <tr className="text-xs text-muted">
                <th scope="col" className="py-1.5 pr-2 text-left font-medium">
                  {STATEMENT_PERIOD_HEADER_KO[period]}
                </th>
                {columns.map(([key, label]) => (
                  <th key={key} scope="col" className="py-1.5 pl-2 text-right font-medium">
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {lines.map((line, i) => (
                <tr key={`${line.period}-${i}`}>
                  <th scope="row" className="py-2 pr-2 text-left font-medium whitespace-nowrap text-ink-2">
                    {line.period}
                  </th>
                  {columns.map(([key]) => (
                    <td key={key} className="py-2 pl-2 text-right font-semibold whitespace-nowrap text-ink">
                      {line[key]}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-muted">{statementUnitNote(d.currency)}</p>
        </>
      )}
    </section>
  )
}
