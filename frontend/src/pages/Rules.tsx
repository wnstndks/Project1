import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import type { Holding, RuleCheckAll, RuleSettings } from '../api/client'
import { useHoldings, useRuleCheck, useRuleSettings, useUpdateRuleSettings, useUsdKrw } from '../api/hooks'
import { RuleStatusChip } from '../components/RuleStatusChip'
import { Card, ErrorBox, Muted, Skeleton } from '../components/ui'
import { displaySymbol, formatKrwShort, formatPct } from '../lib/format'
import {
  addPricePhrase,
  CRYPTO_KEYS,
  CRYPTO_LABELS,
  defaultsToForm,
  formatInCurrency,
  formToPayload,
  GLOBAL_INT_KEYS,
  GLOBAL_LABELS,
  GLOBAL_PCT_KEYS,
  PRICE_BASIS_KO,
  RULES_FOOTNOTE_KO,
  settingsToForm,
  SYMBOL_LABELS,
  SYMBOL_PCT_KEYS,
  type CryptoKey,
  type RuleForm,
  type SymbolForm,
} from '../lib/rules'

const inputClass =
  'num w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-accent'
const cellInputClass =
  'num w-24 rounded-lg border border-line bg-surface px-2 py-1.5 text-sm outline-none focus:border-accent'

/**
 * Settings for the buy-more / stop-loss rule checks. The form keeps every number as the text the
 * user typed and the backend validates ranges (422 names the field). Real trading is shown as
 * read-only state: `AM_LIVE_TRADING` can only be changed in the server's environment.
 */
export function Rules() {
  const settings = useRuleSettings()
  const holdings = useHoldings()
  const update = useUpdateRuleSettings()

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">추매·손절 규칙</h1>
        <p className="mt-2 max-w-3xl text-sm text-ink-2">
          보유 종목마다 내가 정한 손절·추매 규칙을 점검해 <strong>매도 검토 / 추매 검토 / 관망</strong>과 발동 가격을 보여
          줍니다. 이것은 예측이 아니라 규칙의 결과이고, 예측 모델의 매매 신호는 현재 &lsquo;우위 없음&rsquo;입니다. 어떤 종목이든
          비중 상한·킬스위치에 걸리면 추매 검토를 내지 않습니다.
        </p>
        {settings.data && <LiveTradingState on={settings.data.live_trading} />}
      </header>

      {settings.error ? (
        <ErrorBox error={settings.error} />
      ) : holdings.error ? (
        <ErrorBox error={holdings.error} />
      ) : !settings.data || !holdings.data ? (
        <Skeleton className="h-96" />
      ) : (
        <RulesForm
          // Remount on every save so the form shows exactly what was stored.
          key={settings.data.updated_at ?? 'defaults'}
          settings={settings.data}
          holdings={holdings.data}
          onSave={(body) => update.mutateAsync(body)}
          pending={update.isPending}
          saved={update.isSuccess ? update.data : undefined}
          error={update.error}
        />
      )}

      <PreviewCard />

      <p className="text-xs text-muted">{RULES_FOOTNOTE_KO}</p>
    </div>
  )
}

/** Read-only: nothing on this screen turns real trading on. */
function LiveTradingState({ on }: { on: boolean }) {
  return (
    <p className="mt-3 flex flex-wrap items-center gap-2 text-sm">
      <span
        className={`rounded-md px-2 py-0.5 text-xs font-semibold ${on ? 'bg-danger/10 text-danger' : 'bg-fill text-ink-2'}`}
      >
        {on ? '실매매 켜짐' : '실매매 꺼짐'}
      </span>
      <span className="text-muted">
        {on
          ? '주문이 실제로 나갈 수 있는 상태입니다.'
          : '모의투자 기록만 남깁니다. 이 화면에서는 켤 수 없고 서버 설정(AM_LIVE_TRADING)으로만 바뀝니다.'}
      </span>
    </p>
  )
}

function RulesForm({ settings, holdings, onSave, pending, saved, error }: {
  settings: RuleSettings
  holdings: Holding[]
  onSave: (body: ReturnType<typeof formToPayload>) => Promise<unknown>
  pending: boolean
  saved?: RuleSettings
  error: unknown
}) {
  const symbols = holdings.map((h) => h.symbol)
  const assetType = new Map(holdings.map((h) => [h.symbol, h.asset_type]))
  const [form, setForm] = useState<RuleForm>(() => settingsToForm(settings, symbols))
  const [formError, setFormError] = useState<string | null>(null)
  const [resetHint, setResetHint] = useState(false)

  const setGlobal = (key: keyof RuleForm['global'], value: string | boolean) =>
    setForm((f) => ({ ...f, global: { ...f.global, [key]: value } }))
  const setCrypto = (key: CryptoKey, value: string) => setForm((f) => ({ ...f, crypto: { ...f.crypto, [key]: value } }))
  const setTarget = (symbol: string, key: keyof SymbolForm, value: string) =>
    setForm((f) => ({ ...f, targets: { ...f.targets, [symbol]: { ...f.targets[symbol], [key]: value } } }))

  async function submit(e: FormEvent) {
    e.preventDefault()
    setFormError(null)
    setResetHint(false)
    let body
    try {
      body = formToPayload(form)
    } catch (err) {
      setFormError(err instanceof Error ? err.message : String(err))
      return
    }
    try {
      await onSave(body)
    } catch {
      // The parent renders the backend's message.
    }
  }

  /** Fills the form with the `AM_RULES_*` defaults; nothing is stored until 저장. */
  function resetToDefaults() {
    setForm(defaultsToForm(settings, symbols))
    setFormError(null)
    setResetHint(true)
  }

  /** The value a blank crypto or symbol field falls back to, for placeholders. */
  const fallback = (symbol: string | null, key: 'cut_loss_pct' | 'trailing_drop_pct' | 'add_step_pct'): string => {
    const crypto = symbol !== null && assetType.get(symbol) === 'crypto'
    const c = form.crypto[key].trim()
    return crypto && c ? c : form.global[key]
  }

  return (
    <form onSubmit={submit} className="space-y-6">
      <Card title="전역 규칙">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {GLOBAL_PCT_KEYS.map((key) => (
            <Field key={key} label={GLOBAL_LABELS[key]} value={form.global[key]} onChange={(v) => setGlobal(key, v)} />
          ))}
          {GLOBAL_INT_KEYS.map((key) => (
            <Field key={key} label={GLOBAL_LABELS[key]} value={form.global[key]} onChange={(v) => setGlobal(key, v)} integer />
          ))}
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.global.add_requires_above_ma_short}
              onChange={(e) => setGlobal('add_requires_above_ma_short', e.target.checked)}
              className="size-4 accent-[var(--accent)]"
            />
            <span className="text-ink-2">{GLOBAL_LABELS.add_requires_above_ma_short}</span>
          </label>
        </div>
        <p className="mt-4 text-xs text-muted">
          손절 조건(평균단가 대비, 고점 대비, 장기선 아래 연속)은 하나라도 맞으면 매도 검토입니다. 추매는 분할매수(단계 가격 이하,
          단기선 위) 또는 목표 비중 미달이 맞고 한도에 걸리지 않을 때 추매 검토입니다. {PRICE_BASIS_KO} 일수는 모두 확정 봉 수로
          셉니다(코인은 달력일, 주식은 거래일).
        </p>
      </Card>

      <Card title="코인 자산군">
        <div className="grid gap-4 sm:grid-cols-3">
          {CRYPTO_KEYS.map((key) => (
            <Field
              key={key}
              label={CRYPTO_LABELS[key]}
              value={form.crypto[key]}
              onChange={(v) => setCrypto(key, v)}
              placeholder={`비우면 전역값 ${form.global[key] || '—'}`}
            />
          ))}
        </div>
        <p className="mt-4 text-xs text-muted">
          코인은 주식보다 변동이 커서 손절·추적 손절·추매 단계 폭을 따로 둡니다. 비우면 전역값을 씁니다. 종목별 값이 있으면 그것이
          우선합니다.
        </p>
      </Card>

      <Card title="종목별 규칙">
        {Object.keys(form.targets).length === 0 ? (
          <Muted>보유 종목이 없습니다. 종목을 보유하면 여기에서 목표 비중과 손절 폭을 따로 정할 수 있습니다.</Muted>
        ) : (
          <div className="-mx-6 overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs text-muted">
                  <th className="px-6 py-2 font-medium">종목</th>
                  {SYMBOL_PCT_KEYS.map((key) => (
                    <th key={key} className="px-3 py-2 font-medium">{SYMBOL_LABELS[key]}</th>
                  ))}
                  <th className="px-3 py-2 pr-6 font-medium">{SYMBOL_LABELS.add_max_steps}</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(form.targets).map(([symbol, t]) => (
                  <tr key={symbol} className="border-b border-line last:border-0">
                    <td className="px-6 py-2">
                      <span className="font-semibold">{displaySymbol(symbol)}</span>
                      {!assetType.has(symbol) && <span className="ml-1.5 text-xs text-muted">보유 없음</span>}
                    </td>
                    <td className="px-3 py-2">
                      <input
                        aria-label={`${displaySymbol(symbol)} ${SYMBOL_LABELS.target_weight_pct}`}
                        inputMode="decimal"
                        className={cellInputClass}
                        value={t.target_weight_pct}
                        placeholder="없음"
                        onChange={(e) => setTarget(symbol, 'target_weight_pct', e.target.value)}
                      />
                    </td>
                    {(['cut_loss_pct', 'trailing_drop_pct', 'add_step_pct'] as const).map((key) => (
                      <td key={key} className="px-3 py-2">
                        <input
                          aria-label={`${displaySymbol(symbol)} ${SYMBOL_LABELS[key]}`}
                          inputMode="decimal"
                          className={cellInputClass}
                          value={t[key]}
                          placeholder={fallback(symbol, key)}
                          onChange={(e) => setTarget(symbol, key, e.target.value)}
                        />
                      </td>
                    ))}
                    <td className="px-3 py-2 pr-6">
                      <input
                        aria-label={`${displaySymbol(symbol)} ${SYMBOL_LABELS.add_max_steps}`}
                        inputMode="numeric"
                        className={cellInputClass}
                        value={t.add_max_steps}
                        placeholder={form.global.add_max_steps}
                        onChange={(e) => setTarget(symbol, 'add_max_steps', e.target.value)}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-4 text-xs text-muted">
          비우면 자산군·전역값을 씁니다. 목표 비중은 종목별로만 정하며, 비우면 목표 비중 규칙은 그 종목에 적용되지 않습니다.
        </p>
      </Card>

      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={pending}
            className="rounded-lg bg-ink px-4 py-2 text-sm font-medium text-surface disabled:opacity-50"
          >
            {pending ? '저장 중…' : '저장'}
          </button>
          <button
            type="button"
            onClick={resetToDefaults}
            className="rounded-lg border border-line px-4 py-2 text-sm font-medium hover:bg-hover"
          >
            기본값으로 되돌리기
          </button>
          {resetHint && <span className="text-xs text-muted">기본값을 채웠습니다. 저장을 눌러야 적용됩니다.</span>}
          {settings.updated_at && (
            <span className="num text-xs text-muted">마지막 저장 {new Date(settings.updated_at + 'Z').toLocaleString('ko-KR')}</span>
          )}
        </div>
        {formError && <ErrorBox error={formError} />}
        {error ? <ErrorBox error={error} /> : null}
        {saved && (
          <div role="status" className="rounded-lg border border-line bg-surface px-4 py-3 text-sm">
            <p className="font-medium">저장했습니다.</p>
            {(saved.warnings ?? []).length > 0 ? (
              <ul className="mt-1 list-inside list-disc text-ink-2">
                {(saved.warnings ?? []).map((w) => <li key={w}>{w}</li>)}
              </ul>
            ) : (
              <p className="mt-1 text-muted">규칙끼리 모순되는 조합은 없습니다.</p>
            )}
          </div>
        )}
      </div>
    </form>
  )
}

function Field({ label, value, onChange, placeholder, integer = false }: {
  label: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  integer?: boolean
}) {
  return (
    <label className="block text-sm">
      <span className="text-ink-2">{label}</span>
      <input
        inputMode={integer ? 'numeric' : 'decimal'}
        className={`mt-1 ${inputClass}`}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  )
}

/** What the saved rules say right now, one row per holding; refreshes after every save. */
function PreviewCard() {
  const check = useRuleCheck()
  const fx = useUsdKrw().data?.price
  return (
    <Card title="지금 점검 결과">
      {check.error ? (
        <ErrorBox error={check.error} />
      ) : !check.data ? (
        <Skeleton className="h-32" />
      ) : (
        <div className={check.isFetching ? 'opacity-50 transition-opacity' : ''}>
          <PreviewTable data={check.data} fx={fx} />
        </div>
      )}
    </Card>
  )
}

function PreviewTable({ data, fx }: { data: RuleCheckAll; fx?: number }) {
  if (data.checks.length === 0 && data.skipped.length === 0) return <Muted>보유 중인 종목이 없습니다.</Muted>
  const lossKrw = (amount: number, currency: string): string | undefined =>
    currency === 'KRW' ? formatKrwShort(amount) : fx !== undefined ? formatKrwShort(amount * fx) : undefined
  return (
    <>
      <div className="-mx-6 overflow-x-auto">
        <table className="num w-full min-w-[720px] text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs text-muted">
              <th className="px-6 py-2 font-medium">종목</th>
              <th className="px-3 py-2 font-medium">상태</th>
              <th className="px-3 py-2 text-right font-medium">손절 검토 가격</th>
              <th className="px-3 py-2 text-right font-medium">다음 추매가</th>
              <th className="px-3 py-2 text-right font-medium">거리 (손절 · 추매)</th>
              <th className="px-3 py-2 pr-6 text-right font-medium">손절 시 손실</th>
            </tr>
          </thead>
          <tbody>
            {data.checks.map((c) => {
              const loss = lossKrw(c.levels.risk_amount, c.currency)
              return (
                <tr key={c.symbol} className="border-b border-line last:border-0">
                  <td className="px-6 py-2.5">
                    <Link to={`/assets/${encodeURIComponent(c.symbol)}`} className="font-semibold hover:underline">
                      {displaySymbol(c.symbol)}
                    </Link>
                  </td>
                  <td className="px-3 py-2.5">
                    <span className="flex flex-wrap items-center gap-1.5">
                      <RuleStatusChip status={c.status} label={c.chip_ko} />
                      {c.label_ko !== c.chip_ko && <span className="text-xs text-ink-2">{c.label_ko}</span>}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-right">{formatInCurrency(c.levels.cut_price, c.currency)}</td>
                  <td className="px-3 py-2.5 text-right">
                    {c.levels.add_price !== null ? (
                      formatInCurrency(c.levels.add_price, c.currency)
                    ) : (
                      <span className="text-xs text-muted">{addPricePhrase(c)}</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-right whitespace-nowrap">
                    {formatPct(c.cut_distance_pct, true, 1)}
                    <span className="mx-1 text-muted">·</span>
                    {c.add_distance_pct !== null ? formatPct(c.add_distance_pct, true, 1) : '—'}
                  </td>
                  <td className="px-3 py-2.5 pr-6 text-right whitespace-nowrap">
                    약 {loss ?? formatInCurrency(c.levels.risk_amount, c.currency)}
                    {c.risk_pct_equity !== null && (
                      <span className="ml-1 text-xs text-muted">({c.risk_pct_equity.toFixed(1)}%)</span>
                    )}
                  </td>
                </tr>
              )
            })}
            {data.skipped.map((s) => (
              <tr key={s.symbol} className="border-b border-line last:border-0">
                <td className="px-6 py-2.5 font-semibold">{displaySymbol(s.symbol)}</td>
                <td className="px-3 py-2.5 text-xs text-danger" colSpan={5}>
                  점검하지 못했습니다: {s.reason}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 space-y-1 text-xs text-muted">
        {typeof data.total_risk_pct_equity === 'number' && (
          <p className="num">모든 손절이 걸리면 총자산의 {data.total_risk_pct_equity.toFixed(1)}%를 잃습니다.</p>
        )}
        {data.kill_switch.tripped && (
          <p className="text-danger">킬스위치 발동 중: 추매 검토를 내지 않습니다 ({data.kill_switch.detail}).</p>
        )}
        {data.settings_notes.map((n) => <p key={n}>{n}</p>)}
        <p>
          {PRICE_BASIS_KO} 거리는 거래 통화 기준(주식 달러, 업비트 코인 원화)입니다. 손절 시 손실은 오늘 환율로 환산한 원화입니다.
          {' '}점검 시각 {new Date(data.checked_at + 'Z').toLocaleString('ko-KR')}.
        </p>
      </div>
    </>
  )
}
