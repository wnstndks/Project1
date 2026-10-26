import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { useMoney } from '../lib/currency'
import { changeMark, formatPct, signed } from '../lib/format'

export function Card({ title, actions, children, className = '' }: {
  title?: string
  actions?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`rounded-2xl bg-surface p-6 ${className}`}>
      {(title || actions) && (
        // On phones the actions (period chips, toggles) drop under the title instead of squeezing it.
        <header className="mb-4 flex flex-wrap items-center justify-between gap-3">
          {title && <h2 className="text-[17px] font-bold text-ink">{title}</h2>}
          {actions && <div className="flex min-w-0 basis-full justify-start sm:basis-auto sm:justify-end">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  )
}

/**
 * Gains red, losses blue (Korean convention, `changeMark`). Sign and arrow carry the direction too.
 * `value` must already be in the selected currency (see useMoney().pick).
 * `pctOnly` shows just the arrow and percentage (compact list rows) and takes its direction from `pct`.
 * `digits` is the percentage precision (2 by default; 1 for forecast moves).
 * `format` overrides the selected-currency formatter when the caller already holds the one its
 * chart uses (tooltips), so the figure and the axis never disagree.
 */
export function PnL({ value, pct, pctOnly = false, digits = 2, className = '', format: formatOverride }: {
  value: number
  pct?: number
  pctOnly?: boolean
  digits?: number
  className?: string
  format?: (v: number) => string
}) {
  const money = useMoney()
  const format = formatOverride ?? money.format
  const direction = pctOnly ? (pct ?? 0) : value
  const { tone, arrow } = changeMark(direction)
  return (
    <span className={`whitespace-nowrap ${tone} ${className}`}>
      {arrow && <span aria-hidden="true" className="mr-0.5 text-[0.75em]">{arrow}</span>}
      {pctOnly ? (
        formatPct(pct ?? 0, true, digits)
      ) : (
        <>
          {signed(value, format)}
          {pct !== undefined && <span className="ml-1">({formatPct(pct, true, digits)})</span>}
        </>
      )}
    </span>
  )
}

/** Borderless white tile for stat grids on the gray page. Inside a card use InfoRow instead. */
export function StatTile({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="rounded-2xl bg-surface p-5">
      <div className="text-[13px] text-muted">{label}</div>
      <div className="mt-1 text-lg font-bold">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-ink-2">{sub}</div>}
    </div>
  )
}

/** Label on the left, value on the right: the key-value line inside cards. Wrap rows in a <dl>. */
export function InfoRow({ label, value }: { label: ReactNode; value: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2 text-[15px]">
      <dt className="text-ink-2">{label}</dt>
      <dd className="num text-right font-semibold">{value}</dd>
    </div>
  )
}

/**
 * Toss-style list row: avatar, title and subtitle on the left, value and sub-value on the right.
 * With `to` the whole row is a link and `chevron` shows it opens something.
 * `middle` sits between the title and the value on wide screens and drops to its own line
 * (spread edge to edge, indented past the avatar) on phones. `footer` is a full-width line under
 * everything, also indented past the avatar.
 */
export function ListRow({ to, avatar, title, subtitle, middle, value, subValue, footer, chevron = false }: {
  to?: string
  avatar?: ReactNode
  title: ReactNode
  subtitle?: ReactNode
  middle?: ReactNode
  value?: ReactNode
  subValue?: ReactNode
  footer?: ReactNode
  chevron?: boolean
}) {
  // Avatar is size-10 and the row gap is 3 (12px): 52px lines wrapped lines up with the title.
  const indent = avatar ? 'pl-[52px]' : ''
  const body = (
    <>
      {avatar}
      <div className="min-w-0 flex-1">
        <div className="truncate text-[15px] font-semibold text-ink">{title}</div>
        {subtitle && <div className="num mt-0.5 truncate text-[13px] text-muted">{subtitle}</div>}
      </div>
      {middle && (
        <div
          className={`order-last flex w-full items-center justify-between gap-3 ${indent} sm:order-none sm:w-auto sm:justify-start sm:pl-0`}
        >
          {middle}
        </div>
      )}
      {(value || subValue) && (
        <div className="num shrink-0 text-right">
          {value && <div className="text-[15px] font-semibold text-ink">{value}</div>}
          {subValue && <div className="mt-0.5 text-[13px]">{subValue}</div>}
        </div>
      )}
      {chevron && (
        <svg aria-hidden="true" viewBox="0 0 20 20" className="size-4 shrink-0 text-muted">
          <path
            d="M7.5 5l5 5-5 5"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      )}
      {footer && <div className={`order-last w-full ${indent}`}>{footer}</div>}
    </>
  )
  const cls = '-mx-3 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl px-3 py-3'
  return to ? (
    <Link to={to} className={`${cls} hover:bg-hover focus-visible:outline-2 focus-visible:outline-accent`}>
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  )
}

/**
 * Folded section on native <details>, so it opens with Enter/Space and is announced as expandable.
 * Children stay mounted while closed: their queries still run (the forecast log relies on that).
 * `card` makes it its own white card with a 17px title; otherwise it is an inline "자세히" toggle.
 */
export function Disclosure({ summary, children, card = false }: {
  summary: ReactNode
  children: ReactNode
  card?: boolean
}) {
  return (
    <details className={`group ${card ? 'rounded-2xl bg-surface' : ''}`}>
      <summary
        className={`flex cursor-pointer list-none items-center justify-between gap-3 rounded-2xl focus-visible:outline-2 focus-visible:outline-accent [&::-webkit-details-marker]:hidden ${
          card ? 'p-6 text-[17px] font-bold text-ink' : 'py-1 text-[15px] font-medium text-ink-2'
        }`}
      >
        {summary}
        <svg
          aria-hidden="true"
          viewBox="0 0 20 20"
          className="size-5 shrink-0 text-muted transition-transform group-open:rotate-180"
        >
          <path
            d="M5 7.5l5 5 5-5"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </summary>
      <div className={card ? 'px-6 pb-6' : 'pt-2'}>{children}</div>
    </details>
  )
}

/** Gray placeholder block while data loads. */
export function Skeleton({ className = '' }: { className?: string }) {
  return <div aria-hidden="true" className={`animate-pulse rounded-xl bg-fill ${className}`} />
}

/**
 * Legend and tooltip key for a chart series: a short solid or dashed line, or with `fill` a
 * translucent block for an area/band.
 */
export function Swatch({ color, dashed = false, fill = false }: { color: string; dashed?: boolean; fill?: boolean }) {
  if (fill) return <span className="inline-block h-3 w-4 rounded-sm" style={{ background: color, opacity: 0.35 }} />
  return (
    <span
      className="inline-block w-4 border-t-2"
      style={{ borderColor: color, borderStyle: dashed ? 'dashed' : 'solid' }}
    />
  )
}

/**
 * Pill tabs: gray track with a white chip on the selected option. `fullWidth` spreads options evenly.
 * A long option list scrolls sideways on phones instead of wrapping or overflowing the card.
 */
export function SegmentedControl<T extends string>({ options, value, onChange, label, fullWidth = false }: {
  options: { value: T; label: string }[]
  value: T
  onChange: (v: T) => void
  label: string
  fullWidth?: boolean
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className={`${fullWidth ? 'flex w-full' : 'inline-flex max-w-full overflow-x-auto'} rounded-full bg-fill p-1`}
      onKeyDown={(e) => {
        // Radio-group keyboard pattern: arrows move the selection, focus follows.
        const step = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? -1 : 0
        if (!step) return
        e.preventDefault()
        const i = options.findIndex((o) => o.value === value)
        const next = options[(i + step + options.length) % options.length]
        onChange(next.value)
        const buttons = e.currentTarget.querySelectorAll<HTMLButtonElement>('[role="radio"]')
        buttons[(i + step + options.length) % options.length]?.focus()
      }}
    >
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          tabIndex={o.value === value ? 0 : -1}
          onClick={() => onChange(o.value)}
          className={`shrink-0 rounded-full py-1.5 text-[13px] font-semibold whitespace-nowrap transition-colors focus-visible:outline-2 focus-visible:outline-accent ${
            fullWidth ? 'flex-1 px-1' : 'px-3'
          } ${o.value === value ? 'bg-chip text-ink shadow-sm' : 'text-ink-2 hover:text-ink'}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

/** Legend key for a line series: a short solid or dashed stroke in the series color. */
export function LineSwatch({ color, dash, width = 1.5 }: { color: string; dash?: string; width?: number }) {
  return (
    <svg aria-hidden="true" width="20" height="8" className="shrink-0">
      <line x1="0" y1="4" x2="20" y2="4" stroke={color} strokeWidth={width} strokeDasharray={dash} />
    </svg>
  )
}

/** Legend key for volume bars: an up-day and a down-day bar. */
export function VolumeSwatch() {
  return (
    <svg aria-hidden="true" width="20" height="8" className="shrink-0">
      <rect x="2" y="2" width="6" height="6" fill="var(--gain-mark)" fillOpacity={0.6} />
      <rect x="12" y="0" width="6" height="8" fill="var(--loss-mark)" fillOpacity={0.6} />
    </svg>
  )
}

/** Legend key for a forecast band with its dashed median line. */
export function BandSwatch({ color = 'var(--series-2)' }: { color?: string }) {
  return (
    <svg aria-hidden="true" width="20" height="8" className="shrink-0">
      <rect x="0" y="0" width="20" height="8" fill={color} fillOpacity={0.18} />
      <line x1="0" y1="4" x2="20" y2="4" stroke={color} strokeWidth={2} strokeDasharray="4 3" />
    </svg>
  )
}

/** Legend key for candles: one up and one down candle. */
export function CandleSwatch() {
  return (
    <svg aria-hidden="true" width="20" height="10" className="shrink-0">
      <line x1="5" y1="0" x2="5" y2="10" stroke="var(--gain-mark)" strokeWidth={1} />
      <rect x="2.5" y="2" width="5" height="5" fill="var(--gain-mark)" />
      <line x1="15" y1="0" x2="15" y2="10" stroke="var(--loss-mark)" strokeWidth={1} />
      <rect x="12.5" y="3" width="5" height="5" fill="var(--loss-mark)" />
    </svg>
  )
}

/** The legend under a chart: one key per drawn series, in drawing order. */
export function ChartLegend({ items, className = 'mt-3' }: {
  items: { label: string; swatch: ReactNode }[]
  className?: string
}) {
  return (
    <ul className={`flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-ink-2 ${className}`} aria-label="범례">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-1.5">
          {item.swatch}
          {item.label}
        </li>
      ))}
    </ul>
  )
}

export function ErrorBox({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : String(error)
  return (
    <div role="alert" className="rounded-2xl border border-danger/40 bg-surface px-5 py-4 text-sm text-danger">
      {message}
    </div>
  )
}

export function Muted({ children }: { children: ReactNode }) {
  return <p className="py-8 text-center text-sm text-muted">{children}</p>
}
