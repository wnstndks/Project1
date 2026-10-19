import type { ReactNode } from 'react'

import { useMoney } from '../lib/currency'
import { formatPct, signed } from '../lib/format'

export function Card({ title, actions, children, className = '' }: {
  title?: string
  actions?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`rounded-xl border border-line bg-surface p-5 ${className}`}>
      {(title || actions) && (
        <header className="mb-4 flex items-center justify-between gap-3">
          {title && <h2 className="text-sm font-semibold text-ink-2">{title}</h2>}
          {actions}
        </header>
      )}
      {children}
    </section>
  )
}

/**
 * Gains red, losses blue (Korean convention). Sign and arrow carry the direction too.
 * `value` must already be in the selected currency (see useMoney().pick).
 */
export function PnL({ value, pct, className = '' }: { value: number; pct?: number; className?: string }) {
  const { format } = useMoney()
  const tone = value > 0 ? 'text-gain' : value < 0 ? 'text-loss' : 'text-ink-2'
  const arrow = value > 0 ? '▲' : value < 0 ? '▼' : ''
  return (
    <span className={`whitespace-nowrap ${tone} ${className}`}>
      {arrow && <span aria-hidden="true" className="mr-0.5 text-[0.75em]">{arrow}</span>}
      {signed(value, format)}
      {pct !== undefined && <span className="ml-1">({formatPct(pct)})</span>}
    </span>
  )
}

export function StatTile({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-1 text-xl font-semibold">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-ink-2">{sub}</div>}
    </div>
  )
}

export function SegmentedControl<T extends string>({ options, value, onChange, label }: {
  options: { value: T; label: string }[]
  value: T
  onChange: (v: T) => void
  label: string
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="inline-flex rounded-lg border border-line p-0.5"
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
          className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
            o.value === value ? 'bg-ink text-surface' : 'text-ink-2 hover:bg-hover'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function ErrorBox({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : String(error)
  return (
    <div role="alert" className="rounded-lg border border-danger/40 px-4 py-3 text-sm text-danger">
      {message}
    </div>
  )
}

export function Muted({ children }: { children: ReactNode }) {
  return <p className="py-8 text-center text-sm text-muted">{children}</p>
}
