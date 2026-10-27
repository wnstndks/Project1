import { useState, type FormEvent, type ReactNode } from 'react'
import { Link } from 'react-router-dom'

import type {
  CoachDiagnosis,
  CoachFlag,
  CoachPatterns,
  CoachPolicy,
  CoachPolicyInput,
  CoachRebalance,
  CoachReview,
  RuleCheckAll,
} from '../api/client'
import {
  useCoachDiagnosis,
  useCoachPatterns,
  useCoachPolicy,
  useCoachRebalance,
  useCoachReview,
  useResetKillSwitch,
  useRuleCheck,
  useUpdateCoachPolicy,
} from '../api/hooks'
import { CorrelationHeatmap } from '../components/CorrelationHeatmap'
import { Field } from '../components/FormField'
import { Card, Disclosure, ErrorBox, InfoRow, PnL, Skeleton, StatTile } from '../components/ui'
import {
  actualCurveNote,
  betaPhrase,
  CASH_LABELS_KO,
  CASH_NOTE_KO,
  CASH_STALE_NOTE_KO,
  CHECKLIST_STATE_KO,
  COACH_FOOTER_KO,
  COACH_INTRO_KO,
  DEFAULTS_NOTE_KO,
  defaultsToForm,
  drawdownPhrase,
  EMPTY_NOTE_KO,
  FLAGS_NOT_COUNTED_KO,
  formToPolicyPayload,
  inLossChecklist,
  KILL_SWITCH_RESET_CONFIRM_KO,
  killSwitchChip,
  lagPhrase,
  liveTradingChip,
  monthLabel,
  patternPhrase,
  POLICY_LABELS_KO,
  POLICY_PCT_KEYS,
  policyToForm,
  preBuyChecklist,
  rebalanceActionPhrase,
  requiredReturnPhrase,
  reviewViolationsLabel,
  riskWindow,
  signedKrw,
  swingPhrase,
  TARGET_KEYS,
  targetSum,
  violationTone,
  windowSpanPhrase,
  type CashForm,
  type ChecklistItem,
  type CoachForm,
  type PolicyForm,
} from '../lib/coach'
import { displaySymbol, formatDate, formatKrw, formatKrwShort, formatPct } from '../lib/format'

/**
 * The portfolio coach (D-033): the user's investment policy and where the holdings stand
 * against it. The coach is not a forecast, not a stock pick and not advice, and nothing here
 * places an order. Past-window figures (volatility, drawdown, correlation, beta) carry their
 * window and never a gain/loss colour; only money actually realized (the monthly review's
 * P&L, dividends and benchmark excess) is coloured the Korean way, and even that only while
 * no mis-priced trade sits inside the month's figures. The "if sold" P&L of the rebalance
 * table is an assumption and shows its sign only.
 */
export function Coach() {
  const policy = useCoachPolicy()
  const update = useUpdateCoachPolicy()
  const rules = useRuleCheck()

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">포트폴리오 코치</h1>
        <p className="mt-2 max-w-3xl text-sm text-ink-2">{COACH_INTRO_KO}</p>
        <StatusStrip rules={rules.data} />
      </header>

      {policy.error ? (
        <ErrorBox error={policy.error} />
      ) : !policy.data ? (
        <Skeleton className="h-96" />
      ) : (
        <PolicyFormCard
          // Remount on every save so the form shows exactly what was stored.
          key={policy.data.updated_at ?? 'defaults'}
          data={policy.data}
          onSave={(body) => update.mutateAsync(body)}
          pending={update.isPending}
          saved={update.isSuccess ? update.data : undefined}
          error={update.error}
        />
      )}

      <DiagnosisSection rules={rules.data} />
      <RebalanceSection />
      <PatternsSection />
      <ReviewSection />

      <p className="text-xs text-muted">{COACH_FOOTER_KO}</p>
    </div>
  )
}

/**
 * Kill switch and real-trading state from the rule check (same query as the rules page). The
 * reset button exists only while the switch is tripped and asks twice, inline: no modal, no
 * `window.confirm`. Hidden while the check loads or fails; the page still works without it.
 */
function StatusStrip({ rules }: { rules: RuleCheckAll | undefined }) {
  const reset = useResetKillSwitch()
  const [confirming, setConfirming] = useState(false)
  if (!rules) return null
  const kill = rules.kill_switch
  const killChip = killSwitchChip(kill.tripped)
  const live = liveTradingChip(rules.live_trading)

  return (
    <div className="mt-3 space-y-2 text-sm">
      <p className="flex flex-wrap items-center gap-2">
        <span className={`rounded-md px-2 py-0.5 text-xs font-semibold ${killChip.className}`}>{killChip.label}</span>
        {kill.tripped && (
          <span className="text-muted">
            {kill.detail || kill.reason_code}
            {kill.since && <span className="num"> · {new Date(kill.since + 'Z').toLocaleString('ko-KR')}부터</span>}
          </span>
        )}
        {kill.tripped && !confirming && (
          <button
            type="button"
            onClick={() => setConfirming(true)}
            className="rounded-lg border border-line px-3 py-1 text-xs font-medium hover:bg-hover"
          >
            해제
          </button>
        )}
        {kill.tripped && confirming && (
          <span role="group" aria-label="킬스위치 해제 확인" className="flex flex-wrap items-center gap-2">
            <span className="text-ink-2">{KILL_SWITCH_RESET_CONFIRM_KO}</span>
            <button
              type="button"
              disabled={reset.isPending}
              onClick={() => reset.mutate(undefined, { onSettled: () => setConfirming(false) })}
              className="rounded-lg bg-ink px-3 py-1 text-xs font-medium text-surface disabled:opacity-50"
            >
              {reset.isPending ? '해제 중…' : '해제 확인'}
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="rounded-lg border border-line px-3 py-1 text-xs font-medium hover:bg-hover"
            >
              취소
            </button>
          </span>
        )}
      </p>
      <p className="flex flex-wrap items-center gap-2">
        <span className={`rounded-md px-2 py-0.5 text-xs font-semibold ${live.className}`}>{live.label}</span>
        <span className="text-muted">{live.description}</span>
      </p>
      {reset.error ? <ErrorBox error={reset.error} /> : null}
    </div>
  )
}

// --- policy -----------------------------------------------------------------------------------------

function PolicyFormCard({ data, onSave, pending, saved, error }: {
  data: CoachPolicy
  onSave: (body: CoachPolicyInput) => Promise<unknown>
  pending: boolean
  saved?: CoachPolicy
  error: unknown
}) {
  const [form, setForm] = useState<CoachForm>(() => policyToForm(data))
  const [formError, setFormError] = useState<string | null>(null)
  const [resetHint, setResetHint] = useState(false)

  const setPolicy = (key: keyof PolicyForm, value: string) =>
    setForm((f) => ({ ...f, policy: { ...f.policy, [key]: value } }))
  const setCash = (key: keyof CashForm, value: string) => setForm((f) => ({ ...f, cash: { ...f.cash, [key]: value } }))

  const sum = targetSum(form.policy)
  const sumOk = sum !== null && Math.abs(sum - 100) <= 1e-6

  async function submit(e: FormEvent) {
    e.preventDefault()
    setFormError(null)
    setResetHint(false)
    let body: CoachPolicyInput
    try {
      body = formToPolicyPayload(form)
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

  /** Fills the form with the settings defaults; nothing is stored until 저장. */
  function resetToDefaults() {
    setForm(defaultsToForm(data))
    setFormError(null)
    setResetHint(true)
  }

  return (
    <form onSubmit={submit} className="space-y-6">
      {!data.policy_set && (
        <p role="status" className="rounded-lg border border-line bg-surface px-4 py-3 text-sm text-ink-2">
          {DEFAULTS_NOTE_KO}
        </p>
      )}

      <Card title="목표">
        <div className="grid gap-4 sm:grid-cols-3">
          <Field
            label={POLICY_LABELS_KO.goal_manwon}
            value={form.policy.goal_manwon}
            onChange={(v) => setPolicy('goal_manwon', v)}
            placeholder="비우면 목표 없음"
            hint="1000 = 1,000만원"
          />
          <Field label={POLICY_LABELS_KO.goal_date} type="date" value={form.policy.goal_date} onChange={(v) => setPolicy('goal_date', v)} />
          <Field
            label={POLICY_LABELS_KO.monthly_manwon}
            value={form.policy.monthly_manwon}
            onChange={(v) => setPolicy('monthly_manwon', v)}
            placeholder="0"
          />
        </div>
        <p className="mt-4 text-xs text-muted">
          목표는 달성에 필요한 연수익률을 산수로 계산하는 데만 씁니다. 그 숫자는 예측이 아닙니다.
        </p>
      </Card>

      <Card title="한도">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {POLICY_PCT_KEYS.map((key) => (
            <Field key={key} label={POLICY_LABELS_KO[key]} value={form.policy[key]} onChange={(v) => setPolicy(key, v)} />
          ))}
        </div>
        <p className="mt-4 text-xs text-muted">
          낙폭은 총자산이 고점에서 얼마나 내려가도 견딜 수 있는지, 손절 합산은 모든 손절선이 한 번에 닿았을 때 잃는 금액의
          총자산 비율입니다. 모의투자의 리스크 한도(AM_RISK_*)는 여기서 바뀌지 않습니다.
        </p>
      </Card>

      <Card title="자산군 목표 비중">
        <div className="grid gap-4 sm:grid-cols-3">
          {TARGET_KEYS.map((key) => (
            <Field key={key} label={POLICY_LABELS_KO[key]} value={form.policy[key]} onChange={(v) => setPolicy(key, v)} />
          ))}
        </div>
        <p className={`num mt-3 text-sm ${sumOk ? 'text-ink-2' : 'text-danger'}`} aria-live="polite">
          합 {sum === null ? '—' : `${Math.round(sum * 1e6) / 1e6}%`} {sumOk ? '' : '(100이어야 합니다)'}
        </p>
        <p className="mt-2 text-xs text-muted">
          종목별 목표 비중은{' '}
          <Link to="/rules" className="underline">
            규칙 페이지에서
          </Link>{' '}
          정합니다. 코치는 그 값을 그대로 읽고 새 종목을 끼워 넣지 않습니다.
        </p>
      </Card>

      <Card title="현금 잔고">
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label={CASH_LABELS_KO.krw} value={form.cash.krw} onChange={(v) => setCash('krw', v)} placeholder="0" />
          <Field label={CASH_LABELS_KO.usd} value={form.cash.usd} onChange={(v) => setCash('usd', v)} placeholder="0" />
          <Field label={CASH_LABELS_KO.as_of} type="date" value={form.cash.as_of} onChange={(v) => setCash('as_of', v)} />
        </div>
        <p className="mt-4 text-xs text-muted">{CASH_NOTE_KO}</p>
        {data.cash_stale && <p className="mt-1 text-xs text-danger">{CASH_STALE_NOTE_KO}</p>}
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
          {data.updated_at && (
            <span className="num text-xs text-muted">마지막 저장 {new Date(data.updated_at + 'Z').toLocaleString('ko-KR')}</span>
          )}
        </div>
        {formError && <ErrorBox error={formError} />}
        {error ? <ErrorBox error={error} /> : null}
        {saved && (
          <div role="status" className="rounded-lg border border-line bg-surface px-4 py-3 text-sm">
            <p className="font-medium">저장했습니다.</p>
            {saved.warnings.length > 0 ? (
              <ul className="mt-1 list-inside list-disc text-ink-2">
                {saved.warnings.map((w) => <li key={w}>{w}</li>)}
              </ul>
            ) : (
              <p className="mt-1 text-muted">눈여겨볼 점은 없습니다.</p>
            )}
          </div>
        )}
      </div>
    </form>
  )
}

// --- diagnosis --------------------------------------------------------------------------------------

/** Loading, error and "nothing held" states shared by the check sections. */
function SectionState({ title, error, loading, empty, children }: {
  title: string
  error: unknown
  loading: boolean
  empty: boolean
  children: ReactNode
}) {
  return (
    <Card title={title}>
      {error ? (
        <ErrorBox error={error} />
      ) : loading ? (
        <Skeleton className="h-40" />
      ) : empty ? (
        <p className="text-sm text-muted">{EMPTY_NOTE_KO}</p>
      ) : (
        children
      )}
    </Card>
  )
}

function Caveats({ items }: { items: string[] }) {
  if (items.length === 0) return null
  return (
    <ul className="mt-4 space-y-1 text-xs text-muted">
      {items.map((c) => <li key={c}>{c}</li>)}
    </ul>
  )
}

function DiagnosisSection({ rules }: { rules: RuleCheckAll | undefined }) {
  const diagnosis = useCoachDiagnosis()
  const d = diagnosis.data
  return (
    <>
      <SectionState title="진단" error={diagnosis.error} loading={!d} empty={d?.empty ?? false}>
        {d && <DiagnosisBody d={d} />}
      </SectionState>
      {d && !d.empty && <ChecklistSection d={d} rules={rules} />}
    </>
  )
}

function DiagnosisBody({ d }: { d: CoachDiagnosis }) {
  const exposure = d.exposure!
  const concentration = d.concentration!
  const swing = swingPhrase(riskWindow(d, '1y'))
  const drawdown = drawdownPhrase(riskWindow(d, '3y'), Number(d.policy.drawdown_tolerance_pct))
  const warns = d.violations.filter((v) => v.severity === 'warn')
  const infos = d.violations.filter((v) => v.severity !== 'warn')
  const goal = requiredReturnPhrase(d)
  const actual = d.risk.actual
  return (
    <div className="space-y-5">
      <p className="text-sm text-ink-2">
        {d.policy_set ? '내가 저장한 정책' : '아직 저장하지 않은 기본 정책'} 기준, {formatDate(d.as_of, 'long')} 점검.
      </p>
      <div className="-mx-6 grid gap-3 bg-page px-6 py-3 sm:grid-cols-2 lg:grid-cols-3">
        <StatTile
          label="총자산"
          value={formatKrwShort(d.equity_krw)}
          sub={
            d.cash_krw === null
              ? `현금 미입력 · 투자금만 ${formatKrwShort(d.invested_krw)}`
              : `현금 ${formatKrwShort(d.cash_krw)} 포함 · 투자금 ${formatKrwShort(d.invested_krw)}`
          }
        />
        <StatTile
          label="실질 종목 수"
          value={`${concentration.effective_n.toFixed(1)}개`}
          sub={`보유 ${concentration.count}종목 · 가장 큰 ${concentration.top1_symbol ? displaySymbol(concentration.top1_symbol) : '—'} ${concentration.top1_pct.toFixed(0)}% (투자금 기준)`}
        />
        <StatTile
          label="코인 비중"
          value={`${exposure.crypto_pct.toFixed(1)}%`}
          sub={`상한 ${Number(d.policy.max_crypto_weight_pct)}% · 주식 ${exposure.stock_pct.toFixed(1)}%${
            exposure.cash_pct !== null ? ` · 현금 ${exposure.cash_pct.toFixed(1)}%` : ''
          }`}
        />
        <StatTile label="달러 비중" value={`${exposure.usd_pct.toFixed(1)}%`} sub="환율 변동이 원화 숫자 안에 들어 있어요" />
        <StatTile label="1년에 보통 이만큼 오르내렸어요" value={swing.value} sub={swing.text} />
        <StatTile label="지금 구성으로 지난 3년을 지났다면 가장 깊은 하락" value={drawdown.value} sub={drawdown.text} />
      </div>

      {goal && <p className="text-sm text-ink-2">{goal}</p>}

      <div>
        <h3 className="text-sm font-semibold">정책 위반 {warns.length}건</h3>
        {d.violations.length === 0 ? (
          <p className="mt-1 text-sm text-muted">내 정책을 벗어난 항목이 없어요.</p>
        ) : (
          <ul className="mt-2 space-y-2">
            {[...warns, ...infos].map((v) => (
              <li key={`${v.code}-${v.subject ?? ''}`} className="flex flex-wrap items-start gap-2 text-sm">
                <span className={`shrink-0 rounded-md px-2 py-0.5 text-xs font-semibold ${violationTone(v.severity)}`}>
                  {v.severity === 'warn' ? '위반' : '참고'} · {v.label_ko}
                </span>
                <span className="text-ink-2">{v.detail}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <Disclosure summary="같이 움직이는 정도 (상관)">
        {d.correlation ? (
          <CorrelationHeatmap
            symbols={d.correlation.symbols}
            matrix={d.correlation.matrix}
            method={d.correlation.method}
            rows={d.correlation.rows}
          />
        ) : (
          <p className="text-sm text-muted">상관을 계산하지 못했어요.</p>
        )}
        {d.correlation && d.correlation.excluded.length > 0 && (
          <p className="mt-2 text-xs text-muted">이력이 짧아 뺀 종목: {d.correlation.excluded.map(displaySymbol).join(', ')}</p>
        )}
      </Disclosure>

      <Disclosure summary="기준 지수와 함께 움직인 정도 (베타)">
        {d.betas.length === 0 ? (
          <p className="text-sm text-muted">비교할 종목이 없어요 (기준 지수 자체이거나 보유가 없음).</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {d.betas.map((b) => (
              <li key={b.symbol}>
                <span className="font-semibold">{displaySymbol(b.symbol)}</span>
                <span className="ml-2 text-ink-2">{betaPhrase(b)}</span>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-2 text-xs text-muted">거래 통화 기준(주식은 SPY, 달러 코인은 BTC, 원화 코인은 업비트 BTC)이라 환율이 섞이지 않아요.</p>
      </Disclosure>

      <Disclosure summary="실제 추이의 낙폭 (입금을 뺀 기준)">
        {actual ? (
          <dl className="num">
            <InfoRow label={`${formatDate(actual.since, 'long')}부터 가장 깊은 하락`} value={`−${actual.twr_max_drawdown_pct.toFixed(1)}%`} />
            <InfoRow label="지금 고점 대비" value={`−${actual.current_drawdown_pct.toFixed(1)}%`} />
            <InfoRow label={`하루 −${actual.limit_daily_loss_pct}% 넘게 빠진 날 (최근 1년)`} value={`${actual.daily_loss_breaches_1y}일`} />
            <InfoRow label={`낙폭 −${actual.limit_drawdown_pct}% 넘긴 횟수 (최근 1년)`} value={`${actual.drawdown_breaches_1y}회`} />
          </dl>
        ) : (
          <p className="text-sm text-muted">{actualCurveNote(d)}</p>
        )}
      </Disclosure>

      <Caveats items={d.caveats} />
    </div>
  )
}

// --- checklists --------------------------------------------------------------------------------------

const STATE_TONE: Record<ChecklistItem['state'], string> = {
  ok: 'bg-fill text-ink-2',
  warn: 'bg-danger/10 text-danger',
  info: 'bg-accent-soft text-accent',
}

function Checklist({ title, items }: { title: string; items: ChecklistItem[] }) {
  return (
    <div>
      <h3 className="text-sm font-semibold">{title}</h3>
      <ul className="mt-2 space-y-2">
        {items.map((i) => (
          <li key={i.label} className="flex flex-wrap items-start gap-2 text-sm">
            <span className={`shrink-0 rounded-md px-2 py-0.5 text-xs font-semibold ${STATE_TONE[i.state]}`}>
              {CHECKLIST_STATE_KO[i.state]} · {i.label}
            </span>
            <span className="text-ink-2">{i.detail}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function ChecklistSection({ d, rules }: { d: CoachDiagnosis; rules: RuleCheckAll | undefined }) {
  return (
    <Card title="체크리스트">
      <div className="grid gap-6 lg:grid-cols-2">
        <Checklist title="사기 전에" items={preBuyChecklist(d, rules)} />
        <Checklist title="손실 중일 때" items={inLossChecklist(d, rules)} />
      </div>
      <p className="mt-4 text-xs text-muted">내 정책과 규칙 점검에서 조합한 확인 목록이에요. 무엇을 살지 말지는 정하지 않습니다.</p>
    </Card>
  )
}

// --- rebalancing -------------------------------------------------------------------------------------

function RebalanceSection() {
  const rebalance = useCoachRebalance()
  const r = rebalance.data
  return (
    <SectionState title="정책대로라면" error={rebalance.error} loading={!r} empty={r?.empty ?? false}>
      {r && <RebalanceBody r={r} />}
    </SectionState>
  )
}

function RebalanceBody({ r }: { r: CoachRebalance }) {
  const orders = new Map(r.orders.map((o) => [o.symbol, o]))
  return (
    <div>
      <p className="text-sm text-ink-2">{r.headline_ko}</p>
      <p className="mt-1 text-xs text-muted">
        허용 오차 ±{r.band_pt}%p 안의 차이는 그대로 둡니다. 자산군 목표 주식 {fmtPct(r.class_targets.stock)} · 코인{' '}
        {fmtPct(r.class_targets.crypto)} · 현금 {r.class_targets.cash === null || r.class_targets.cash === undefined ? '확인 불가' : fmtPct(r.class_targets.cash)}
        {r.unallocated_pct > 0 && ` · 보유가 없어 배분하지 못한 목표 ${r.unallocated_pct.toFixed(0)}%`}
      </p>
      <div className="-mx-6 mt-3 overflow-x-auto">
        <table className="num w-full min-w-[760px] text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs text-muted">
              <th className="px-6 py-2 font-medium">종목</th>
              <th className="px-3 py-2 text-right font-medium">지금</th>
              <th className="px-3 py-2 text-right font-medium">목표</th>
              <th className="px-3 py-2 text-right font-medium">차이</th>
              <th className="px-3 py-2 font-medium">정책대로라면</th>
              <th className="px-3 py-2 font-medium">막힌 이유</th>
              <th className="px-3 py-2 pr-6 text-right font-medium">매도 시 실현손익</th>
            </tr>
          </thead>
          <tbody>
            {r.targets.map((t) => {
              const o = orders.get(t.symbol)
              return (
                <tr key={t.symbol} className="border-b border-line last:border-0">
                  <td className="px-6 py-2.5">
                    <Link to={`/assets/${encodeURIComponent(t.symbol)}`} className="font-semibold hover:underline">
                      {displaySymbol(t.symbol)}
                    </Link>
                    {t.capped && <span className="ml-1.5 text-xs text-muted">상한 적용</span>}
                  </td>
                  <td className="px-3 py-2.5 text-right">{t.current_pct.toFixed(1)}%</td>
                  <td className="px-3 py-2.5 text-right">{t.target_pct.toFixed(1)}%</td>
                  <td className="px-3 py-2.5 text-right">{formatPct(t.drift_pt, true, 1).replace('%', '%p')}</td>
                  <td className="px-3 py-2.5">{o ? rebalanceActionPhrase(o) : <span className="text-muted">그대로</span>}</td>
                  <td className="px-3 py-2.5 text-xs text-ink-2">{o && o.labels.length > 0 ? o.labels.join(', ') : '—'}</td>
                  <td className="px-3 py-2.5 pr-6 text-right">
                    {o && o.realized_pnl_krw_if_sold !== null ? (
                      // An assumption ("if sold"), so the sign only: no gain/loss colour, no arrow.
                      <span>{signedKrw(o.realized_pnl_krw_if_sold)}</span>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {r.after && (
        <p className="num mt-3 text-xs text-muted">
          모두 반영하면: {r.after.weights.map((w) => `${displaySymbol(w.symbol)} ${w.weight_pct.toFixed(1)}%`).join(' · ')}
          {r.after.cash_pct !== null && r.after.cash_pct !== undefined
            ? ` · 현금 ${r.after.cash_pct.toFixed(1)}%`
            : ` · 남는 매도 대금 ${formatKrwShort(r.after.cash_krw)}`}
        </p>
      )}
      <Caveats items={[...r.notes, r.disclaimer_ko]} />
    </div>
  )
}

const fmtPct = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${v.toFixed(0)}%`)

// --- habits in the trade log --------------------------------------------------------------------------

function FlagList({ flags }: { flags: CoachFlag[] }) {
  return (
    <ul className="num space-y-1 text-sm">
      {flags.map((f) => (
        <li key={f.trade_id}>
          <span className="text-muted">{formatDate(f.date)}</span>
          <span className="ml-2 font-semibold">{displaySymbol(f.symbol)}</span>
          <span className="ml-2 text-ink-2">{f.detail}</span>
        </li>
      ))}
    </ul>
  )
}

function PatternsSection() {
  const patterns = useCoachPatterns()
  const p = patterns.data
  return (
    <SectionState title="습관 점검" error={patterns.error} loading={!p} empty={p?.empty ?? false}>
      {p && <PatternsBody p={p} />}
    </SectionState>
  )
}

function PatternsBody({ p }: { p: CoachPatterns }) {
  const busiest = [...p.monthly].sort((a, b) => b.total - a.total)[0]
  return (
    <div className="space-y-3">
      <p className="num text-sm text-ink-2">
        {windowSpanPhrase(p.window_start, p.window_end)} 거래 {p.trades_considered}건을 봤어요
        {p.trades_without_bars > 0 && ` (시세가 없어 건너뛴 매수 ${p.trades_without_bars}건)`}.
        {busiest && busiest.total > 0 && ` 가장 많이 거래한 달은 ${monthLabel(busiest.month)} ${busiest.total}건.`}
      </p>
      <ul className="space-y-2">
        {p.patterns.map((pattern) => (
          <li key={pattern.code} className="text-sm">
            <span className={`rounded-md px-2 py-0.5 text-xs font-semibold ${pattern.count > 0 ? 'bg-danger/10 text-danger' : 'bg-fill text-ink-2'}`}>
              {patternPhrase(pattern)}
            </span>
            <span className="ml-2 text-xs text-muted">{pattern.detail}</span>
            {pattern.trades.length > 0 && (
              <div className="mt-1 pl-1">
                <Disclosure summary={`거래 ${pattern.trades.length}건 보기`}>
                  <FlagList flags={pattern.trades} />
                </Disclosure>
              </div>
            )}
            {pattern.months.length > 0 && (
              <p className="mt-1 text-xs text-ink-2">{pattern.months.map(monthLabel).join(', ')}</p>
            )}
          </li>
        ))}
        <li className="text-sm">
          <span className={`rounded-md px-2 py-0.5 text-xs font-semibold ${p.rule_lag.length > 0 ? 'bg-danger/10 text-danger' : 'bg-fill text-ink-2'}`}>
            손절선 아래 보유 지속 {p.rule_lag.length}종목
          </span>
          {p.rule_lag.length > 0 && (
            <ul className="num mt-1 space-y-1 text-sm text-ink-2">
              {p.rule_lag.map((l) => <li key={l.symbol}>{lagPhrase(l)}</li>)}
            </ul>
          )}
        </li>
      </ul>
      <Caveats items={p.caveats} />
    </div>
  )
}

// --- monthly review ------------------------------------------------------------------------------------

function ReviewSection() {
  const [month, setMonth] = useState<string | undefined>(undefined)
  const review = useCoachReview(month)
  const r = review.data
  return (
    <Card
      title="월간 리뷰"
      actions={
        r && r.months_available.length > 0 ? (
          <label className="text-sm">
            <span className="sr-only">달 선택</span>
            <select
              aria-label="달 선택"
              value={month ?? r.month}
              onChange={(e) => setMonth(e.target.value)}
              className="rounded-lg border border-line bg-surface px-3 py-1.5 text-sm"
            >
              {r.months_available.map((m) => (
                <option key={m} value={m}>
                  {monthLabel(m)}
                </option>
              ))}
            </select>
          </label>
        ) : undefined
      }
    >
      {review.error ? (
        <ErrorBox error={review.error} />
      ) : !r ? (
        <Skeleton className="h-40" />
      ) : r.empty ? (
        <p className="text-sm text-muted">거래 기록이 없어 돌아볼 달이 없어요.</p>
      ) : (
        <div className={review.isFetching ? 'opacity-50 transition-opacity' : ''}>
          <ReviewBody r={r} />
        </div>
      )}
    </Card>
  )
}

function ReviewBody({ r }: { r: CoachReview }) {
  // With a mis-priced trade inside the month's figures the deposit/market split is distorted
  // (the first caveat says so): those amounts show their sign only, no gain/loss colour.
  const doubtful = r.suspicious_trades > 0
  const result = (v: number) => (doubtful ? <span>{signedKrw(v)}</span> : <PnL value={v} format={formatKrw} />)
  return (
    <div className="space-y-4">
      <p className="num text-sm text-ink-2">
        {monthLabel(r.month)} ({formatDate(r.start)} 종가 → {formatDate(r.end)} 종가). 거래 {r.trades.buys + r.trades.sells}건 (매수{' '}
        {r.trades.buys} · 매도 {r.trades.sells}) · {reviewViolationsLabel(r.violations_now)}.
      </p>
      <dl className="num">
        <InfoRow label="시작 자산" value={r.start_value_krw === 0 ? '없음 (보유 전)' : formatKrw(r.start_value_krw)} />
        <InfoRow label="끝 자산" value={formatKrw(r.end_value_krw)} />
        <InfoRow label="변화" value={formatKrw(r.change_krw)} />
        <InfoRow label="= 넣은 돈 (매수 − 매도)" value={formatKrw(r.contributions_krw)} />
        <InfoRow label="+ 시장 손익" value={result(r.market_pnl_krw)} />
        <InfoRow label="실현손익" value={<PnL value={r.realized_pnl_krw} format={formatKrw} />} />
        <InfoRow label="배당 (원천징수 후)" value={<PnL value={r.dividends_krw} format={formatKrw} />} />
      </dl>
      <div>
        <h3 className="text-sm font-semibold">같은 날 같은 돈을 넣었다면</h3>
        <dl className="num">
          {r.benchmarks.map((b) => (
            <InfoRow
              key={b.symbol}
              label={`${b.name_ko} 대비`}
              value={
                <span>
                  {result(b.excess_krw)}
                  <span className="ml-1 text-xs text-muted">(그쪽 변화 {formatKrw(b.change_krw)})</span>
                </span>
              }
            />
          ))}
        </dl>
      </div>
      <div>
        {r.flags_counted ? (
          <>
            <h3 className="text-sm font-semibold">습관 점검에 걸린 거래 {r.flagged_trades.length}건</h3>
            {r.flagged_trades.length > 0 ? (
              <div className="mt-2">
                <FlagList flags={r.flagged_trades} />
              </div>
            ) : (
              <p className="mt-1 text-sm text-muted">이 달에는 없어요.</p>
            )}
          </>
        ) : (
          <>
            <h3 className="text-sm font-semibold">습관 점검에 걸린 거래 집계 안 함</h3>
            <p className="mt-1 text-sm text-muted">{FLAGS_NOT_COUNTED_KO}</p>
          </>
        )}
      </div>
      <Caveats items={r.caveats} />
    </div>
  )
}
