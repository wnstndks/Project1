import { useState, type FormEvent, type ReactNode } from 'react'

import { api, type AssetType, type Side, type Transaction, type TransactionInput } from '../api/client'
import { useSupportedCrypto } from '../api/hooks'
import { daysAgo, displaySymbol, isoDate } from '../lib/format'
import { ErrorBox, SegmentedControl } from './ui'

type FormState = {
  asset_type: AssetType
  symbol: string
  side: Side
  trade_date: string
  quantity: string
  price: string
  fee: string
  note: string
}

const empty = (): FormState => ({
  asset_type: 'stock',
  symbol: '',
  side: 'buy',
  trade_date: isoDate(new Date()),
  quantity: '',
  price: '',
  fee: '0',
  note: '',
})

const fromTransaction = (t: Transaction): FormState => ({
  asset_type: t.asset_type,
  symbol: t.symbol,
  side: t.side,
  trade_date: t.trade_date,
  quantity: String(t.quantity),
  price: String(t.price),
  fee: String(t.fee),
  note: t.note ?? '',
})

const inputClass =
  'w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-accent'

export function TransactionForm({ editing, onSubmit, onCancel, pending, error }: {
  editing: Transaction | null
  onSubmit: (data: TransactionInput) => Promise<unknown>
  onCancel: () => void
  pending: boolean
  error: unknown
}) {
  const crypto = useSupportedCrypto()
  const [today] = useState(() => isoDate(new Date()))
  // Remount (via `key` in the parent) resets the form when the edited row changes.
  const [form, setForm] = useState<FormState>(() => (editing ? fromTransaction(editing) : empty()))
  const [priceHint, setPriceHint] = useState<string | null>(null)
  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((f) => ({ ...f, [key]: value }))

  async function fillClosePrice() {
    if (!form.symbol) return
    setPriceHint('불러오는 중…')
    try {
      // Look back a week so a weekend or holiday still finds the previous close.
      const start = daysAgo(7, new Date(`${form.trade_date}T00:00:00`))
      const bars = await api.history(form.symbol, start, form.trade_date)
      const last = bars.at(-1)
      if (!last) throw new Error('해당 기간 시세가 없습니다')
      set('price', String(Number(last.close.toFixed(last.close < 10 ? 4 : 2))))
      setPriceHint(`${last.date} 종가`)
    } catch (e) {
      setPriceHint(e instanceof Error ? e.message : '종가를 불러오지 못했습니다')
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    // Numbers stay strings so the backend parses them as exact decimals.
    await onSubmit({
      asset_type: form.asset_type,
      symbol: form.symbol,
      side: form.side,
      trade_date: form.trade_date,
      quantity: form.quantity,
      price: form.price,
      fee: form.fee || '0',
      note: form.note || null,
    })
    if (!editing) setForm((f) => ({ ...empty(), asset_type: f.asset_type, trade_date: f.trade_date }))
    setPriceHint(null)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="flex flex-wrap gap-3">
        <SegmentedControl
          label="자산 유형"
          value={form.asset_type}
          onChange={(v) => setForm((f) => ({ ...f, asset_type: v, symbol: '' }))}
          options={[
            { value: 'stock', label: '주식' },
            { value: 'crypto', label: '코인' },
          ]}
        />
        <SegmentedControl
          label="매수/매도"
          value={form.side}
          onChange={(v) => set('side', v)}
          options={[
            { value: 'buy', label: '매수' },
            { value: 'sell', label: '매도' },
          ]}
        />
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Field label="종목">
          {form.asset_type === 'crypto' ? (
            <select
              required
              className={inputClass}
              value={form.symbol}
              onChange={(e) => set('symbol', e.target.value)}
            >
              <option value="">선택</option>
              {crypto.data?.map((c) => (
                <option key={c.symbol} value={c.symbol}>
                  {displaySymbol(c.symbol)} · {c.name}
                </option>
              ))}
            </select>
          ) : (
            <input
              required
              className={`${inputClass} uppercase`}
              placeholder="AAPL"
              value={form.symbol}
              onChange={(e) => set('symbol', e.target.value.toUpperCase())}
            />
          )}
        </Field>
        <Field label="거래일">
          <input
            required
            type="date"
            className={inputClass}
            max={today}
            value={form.trade_date}
            onChange={(e) => set('trade_date', e.target.value)}
          />
        </Field>
        <Field label="수량">
          <input
            required
            inputMode="decimal"
            className={`${inputClass} num`}
            placeholder={form.asset_type === 'crypto' ? '0.05' : '10'}
            value={form.quantity}
            onChange={(e) => set('quantity', e.target.value)}
          />
        </Field>
        <Field
          label="단가 (USD)"
          hint={
            <button
              type="button"
              onClick={fillClosePrice}
              disabled={!form.symbol}
              className="text-accent hover:underline disabled:text-muted disabled:no-underline"
            >
              {priceHint ?? '해당일 종가 넣기'}
            </button>
          }
        >
          <input
            required
            inputMode="decimal"
            className={`${inputClass} num`}
            value={form.price}
            onChange={(e) => set('price', e.target.value)}
          />
        </Field>
        <Field label="수수료 (USD)">
          <input
            inputMode="decimal"
            className={`${inputClass} num`}
            value={form.fee}
            onChange={(e) => set('fee', e.target.value)}
          />
        </Field>
        <Field label="메모" className="sm:col-span-2 lg:col-span-3">
          <input
            className={inputClass}
            maxLength={200}
            value={form.note}
            onChange={(e) => set('note', e.target.value)}
          />
        </Field>
      </div>

      {error ? <ErrorBox error={error} /> : null}

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={pending}
          className="rounded-lg bg-ink px-4 py-2 text-sm font-medium text-surface disabled:opacity-50"
        >
          {editing ? '수정 저장' : '거래 추가'}
        </button>
        {editing && (
          <button type="button" onClick={onCancel} className="rounded-lg px-4 py-2 text-sm text-ink-2 hover:bg-hover">
            취소
          </button>
        )}
      </div>
    </form>
  )
}

function Field({ label, hint, className = '', children }: {
  label: string
  hint?: ReactNode
  className?: string
  children: ReactNode
}) {
  return (
    <label className={`block ${className}`}>
      <span className="mb-1 flex items-center justify-between text-xs text-muted">
        {label}
        {hint && <span className="text-xs">{hint}</span>}
      </span>
      {children}
    </label>
  )
}
