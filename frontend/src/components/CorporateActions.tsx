import { useState } from 'react'
import type { CorporateAction } from '../api/client'
import { useConfirmAllDividends, useCorporateActions, useSetActionStatus, useSetWithholding } from '../api/hooks'
import { formatQty, formatUsd } from '../lib/format'
import { splitShares } from '../lib/split'
import { ErrorBox, Muted } from './ui'

function describe(a: CorporateAction): string {
  if (a.kind === 'dividend') return `배당 주당 ${formatUsd(a.value)}`
  const { from, to } = splitShares(a.value)
  return `${to >= from ? '액면분할' : '액면병합(역분할)'} ${formatQty(from)}주→${formatQty(to)}주`
}

const percent = (rate: number) => `${+(rate * 100).toFixed(2)}%`

/** Splits and dividends found for held stocks; confirmed ones change the ledger. */
export function CorporateActions() {
  const actions = useCorporateActions()
  const setStatus = useSetActionStatus()
  const confirmAll = useConfirmAllDividends()
  const setWithholding = useSetWithholding()
  const [editing, setEditing] = useState<{ symbol: string; value: string } | null>(null)

  if (actions.error) return <ErrorBox error={actions.error} />
  if (!actions.data) return <Muted>배당·분할 내역을 확인하는 중…</Muted>
  if (actions.data.length === 0) return <Muted>보유 기간 중 배당이나 액면분할이 없습니다.</Muted>

  const pending = actions.data.filter((a) => a.status === 'detected')
  const done = actions.data.filter((a) => a.status !== 'detected')
  const pendingDividends = pending.filter((a) => a.kind === 'dividend')
  const pendingTotal = pendingDividends.reduce((sum, a) => sum + a.effect, 0)

  const saveWithholding = () => {
    if (!editing) return
    const pct = Number(editing.value)
    if (!Number.isFinite(pct) || pct < 0 || pct >= 100) return
    setWithholding.mutate(
      { symbol: editing.symbol, rate: String(pct / 100) },
      { onSuccess: () => setEditing(null) },
    )
  }

  const effect = (a: CorporateAction) => {
    if (a.kind === 'split') {
      if (a.shares_before === 0) return '보유 없음 · 차트 가격 보정용'
      const fractional = !Number.isInteger(a.effect) && Number.isInteger(a.shares_before)
      return (
        <>
          {formatQty(a.shares_before)}주 → {formatQty(a.effect)}주
          {fractional && (
            <span className="block text-xs text-muted">
              소수점 {formatQty(a.effect - Math.floor(a.effect))}주는 증권사가 현금으로 정산할 수 있음
            </span>
          )}
        </>
      )
    }
    if (editing?.symbol === a.symbol) {
      return (
        <span className="inline-flex items-center gap-1">
          {formatQty(a.shares_before)}주 · 원천징수
          <input
            autoFocus
            inputMode="decimal"
            aria-label={`${a.symbol} 원천징수율(%)`}
            className="w-14 rounded border border-line bg-surface px-1 py-0.5 text-right"
            value={editing.value}
            onChange={(e) => setEditing({ symbol: a.symbol, value: e.target.value })}
            onKeyDown={(e) => {
              if (e.key === 'Enter') saveWithholding()
              if (e.key === 'Escape') setEditing(null)
            }}
          />
          %
          <button type="button" className="font-medium text-accent hover:underline" onClick={saveWithholding}>
            저장
          </button>
        </span>
      )
    }
    return (
      <>
        {formatQty(a.shares_before)}주 ·{' '}
        <button
          type="button"
          className="underline decoration-dotted hover:text-ink"
          title="해외 ADR 등 원천징수율이 다른 종목은 눌러서 바꾸세요"
          onClick={() => setEditing({ symbol: a.symbol, value: String(+(a.withholding * 100).toFixed(2)) })}
        >
          원천징수 {percent(a.withholding)}
        </button>{' '}
        차감 후 약 {formatUsd(a.effect)}
      </>
    )
  }

  return (
    <div className="space-y-4">
      {pending.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-ink-2">
            확인이 필요한 이벤트가 {pending.length}건 있습니다. 반영하면 보유 수량(분할)이나 배당 수익이 장부에
            더해집니다.
          </p>
          {pendingDividends.length > 0 && (
            <button
              type="button"
              className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium hover:bg-hover disabled:opacity-50"
              disabled={confirmAll.isPending}
              onClick={() => confirmAll.mutate()}
            >
              배당 {pendingDividends.length}건 모두 반영 (약 {formatUsd(pendingTotal)})
            </button>
          )}
        </div>
      )}
      {confirmAll.error && <ErrorBox error={confirmAll.error} />}
      {setStatus.error && <ErrorBox error={setStatus.error} />}
      {setWithholding.error && <ErrorBox error={setWithholding.error} />}
      <div className="-mx-5 overflow-x-auto">
        <table className="num w-full min-w-[720px] text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs text-muted">
              <th className="px-5 py-2 font-medium">배당락일·적용일</th>
              <th className="px-3 py-2 font-medium">종목</th>
              <th className="px-3 py-2 font-medium">내용</th>
              <th className="px-3 py-2 text-right font-medium">영향</th>
              <th className="px-5 py-2 text-right font-medium" aria-label="작업" />
            </tr>
          </thead>
          <tbody>
            {[...pending, ...done].map((a) => (
              <tr key={a.id} className="border-b border-line last:border-0">
                <td className="px-5 py-2.5 text-ink-2">{a.ex_date}</td>
                <td className="px-3 py-2.5 font-semibold">{a.symbol}</td>
                <td className="px-3 py-2.5">{describe(a)}</td>
                <td className="px-3 py-2.5 text-right text-ink-2">{effect(a)}</td>
                <td className="px-5 py-2.5 text-right whitespace-nowrap">
                  {a.status === 'detected' ? (
                    <>
                      <button
                        type="button"
                        className="mr-3 font-medium text-accent hover:underline disabled:opacity-50"
                        disabled={setStatus.isPending}
                        onClick={() => setStatus.mutate({ id: a.id, status: 'confirmed' })}
                      >
                        반영
                      </button>
                      <button
                        type="button"
                        className="text-ink-2 hover:underline disabled:opacity-50"
                        disabled={setStatus.isPending}
                        title={
                          a.kind === 'split'
                            ? '분할 전 거래를 이미 분할 후 수량·가격으로 입력했다면 무시하세요'
                            : undefined
                        }
                        onClick={() => setStatus.mutate({ id: a.id, status: 'ignored' })}
                      >
                        무시
                      </button>
                    </>
                  ) : (
                    <span className="text-xs text-muted">{a.status === 'confirmed' ? '반영됨' : '무시함'}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="list-disc space-y-1 pl-4 text-xs text-muted">
        <li>
          배당은 배당락일 기준 보유 수량으로 계산하고 미국 원천징수(기본 15%)만 뺀 금액입니다. 실제 입금은 지급일에,
          지급일 환율로 이뤄지며 연 2천만 원을 넘으면 금융소득종합과세가 더해질 수 있습니다.
        </li>
        <li>
          분할 주식은 국내 증권사 계좌에 며칠 늦게 들어올 수 있습니다. 분할 전 거래를 이미 분할 후 수량·가격으로
          입력했다면 반영하지 말고 무시하세요.
        </li>
        <li>데이터 출처: Yahoo Finance.</li>
      </ul>
    </div>
  )
}
