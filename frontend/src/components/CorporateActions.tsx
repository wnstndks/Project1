import { useConfirmAllDividends, useCorporateActions, useSetActionStatus } from '../api/hooks'
import { formatQty, formatUsd } from '../lib/format'
import { ErrorBox, Muted } from './ui'

/** Splits and dividends found for held stocks; confirmed ones change the ledger. */
export function CorporateActions() {
  const actions = useCorporateActions()
  const setStatus = useSetActionStatus()
  const confirmAll = useConfirmAllDividends()

  if (actions.error) return <ErrorBox error={actions.error} />
  if (!actions.data) return <Muted>배당·분할 내역을 확인하는 중…</Muted>
  if (actions.data.length === 0) return <Muted>보유 기간 중 배당이나 액면분할이 없습니다.</Muted>

  const pending = actions.data.filter((a) => a.status === 'detected')
  const done = actions.data.filter((a) => a.status !== 'detected')

  return (
    <div className="space-y-4">
      {pending.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-ink-2">
            확인이 필요한 이벤트가 {pending.length}건 있습니다. 반영하면 보유 수량(분할)이나 배당 수익(세후)이
            장부에 더해집니다.
          </p>
          {pending.some((a) => a.kind === 'dividend') && (
            <button
              type="button"
              className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium hover:bg-hover disabled:opacity-50"
              disabled={confirmAll.isPending}
              onClick={() => confirmAll.mutate()}
            >
              배당 {pending.filter((a) => a.kind === 'dividend').length}건 모두 반영
            </button>
          )}
        </div>
      )}
      {confirmAll.error && <ErrorBox error={confirmAll.error} />}
      {setStatus.error && <ErrorBox error={setStatus.error} />}
      <div className="-mx-5 overflow-x-auto">
        <table className="num w-full min-w-[640px] text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs text-muted">
              <th className="px-5 py-2 font-medium">기준일</th>
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
                <td className="px-3 py-2.5">
                  {a.kind === 'split'
                    ? `액면분할 1→${formatQty(a.value)}`
                    : `배당 주당 ${formatUsd(a.value)}`}
                </td>
                <td className="px-3 py-2.5 text-right text-ink-2">
                  {a.kind === 'split'
                    ? `${formatQty(a.shares_before)}주 → ${formatQty(a.effect)}주`
                    : `${formatQty(a.shares_before)}주 · 세후 약 ${formatUsd(a.effect)}`}
                </td>
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
      <p className="text-xs text-muted">
        배당은 미국 원천징수 15%를 뺀 금액으로, 원화는 기준일 환율로 계산합니다(실제 지급일·환전 환율과 다를 수
        있음). 데이터 출처: Yahoo Finance.
      </p>
    </div>
  )
}
