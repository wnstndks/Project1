import { useId } from 'react'

/**
 * Labelled text input for settings forms (rules, coach policy). The value is always the text
 * the user typed: numbers are sent as strings so the backend parses exact decimals and
 * answers 422 naming the field when a range is off.
 */
export const inputClass =
  'num w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-accent'

export function Field({ label, value, onChange, placeholder, integer = false, type = 'text', hint }: {
  label: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  integer?: boolean
  /** `date` renders the browser's date picker; the value stays an ISO string. */
  type?: 'text' | 'date'
  /** Shown under the input and linked with aria-describedby; not part of the label name. */
  hint?: string
}) {
  const hintId = useId()
  return (
    <div className="text-sm">
      <label className="block">
        <span className="text-ink-2">{label}</span>
        <input
          type={type}
          inputMode={type === 'date' ? undefined : integer ? 'numeric' : 'decimal'}
          className={`mt-1 ${inputClass}`}
          value={value}
          placeholder={placeholder}
          aria-describedby={hint ? hintId : undefined}
          onChange={(e) => onChange(e.target.value)}
        />
      </label>
      {hint && (
        <span id={hintId} className="mt-1 block text-xs text-muted">
          {hint}
        </span>
      )}
    </div>
  )
}
