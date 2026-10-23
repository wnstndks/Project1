import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import type { AssetType, Transaction, TransactionInput } from '../api/client'
import {
  useCreateTransaction,
  useDeleteTransaction,
  useHoldings,
  useTransactions,
  useUpdateTransaction,
} from '../api/hooks'
import { BulkDelete } from '../components/BulkDelete'
import { CorporateActions } from '../components/CorporateActions'
import { TransactionForm } from '../components/TransactionForm'
import { Card, ErrorBox, Muted, SegmentedControl } from '../components/ui'
import { useMoney } from '../lib/currency'
import { displaySymbol, formatDate, formatQty } from '../lib/format'
import { needsPriceCheck, PRICE_CHECK_REASON, priceCheckRows } from '../lib/transactionChecks'

type Filter = 'all' | AssetType

export function Transactions() {
  const transactions = useTransactions()
  const holdings = useHoldings()
  const create = useCreateTransaction()
  const update = useUpdateTransaction()
  const remove = useDeleteTransaction()
  const [editing, setEditing] = useState<Transaction | null>(null)
  const [filter, setFilter] = useState<Filter>('all')
  const [confirmId, setConfirmId] = useState<number | null>(null)
  const { currency, format } = useMoney()
  // Amounts are stored in the trade's own currency; the other one uses the rate on the
  // trade's own date, not today's.
  const money = (t: Transaction, amount: number) => {
    if (t.currency === currency || !t.usd_krw) return format(amount)
    return format(t.currency === 'KRW' ? amount / t.usd_krw : amount * t.usd_krw)
  }

  const save = async (data: TransactionInput) => {
    if (editing) {
      await update.mutateAsync({ id: editing.id, data })
      setEditing(null)
    } else {
      await create.mutateAsync(data)
    }
  }
  const active = editing ? update : create
  const edit = (t: Transaction) => {
    setEditing(t)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const rows = (transactions.data ?? []).filter((t) => filter === 'all' || t.asset_type === filter)
  // Prices 20x off today's price (screenshot misreads) get a badge; the user fixes them here.
  const flagged = new Set(rows.filter((t) => needsPriceCheck(t, holdings.data ?? [])).map((t) => t.id))
  // The same trades as a list above the table, so the fix is reachable on a phone without the wide table.
  const toCheck = priceCheckRows(transactions.data ?? [], holdings.data ?? [])

  // `/transactions?check=1` (from the home banner) lands on the check list once it has rendered.
  const [params] = useSearchParams()
  const wantCheck = params.get('check') === '1'
  const checkRef = useRef<HTMLDivElement>(null)
  const landed = useRef(false)
  useEffect(() => {
    if (!wantCheck || landed.current || toCheck.length === 0 || !checkRef.current) return
    landed.current = true
    checkRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' })
    checkRef.current.focus({ preventScroll: true })
  }, [wantCheck, toCheck.length])

  return (
    <div className="space-y-6">
      <Card title={editing ? `거래 수정 #${editing.id}` : '거래 추가'}>
        <TransactionForm
          key={editing?.id ?? 'new'}
          editing={editing}
          onSubmit={save}
          onCancel={() => {
            setEditing(null)
            update.reset()
          }}
          pending={active.isPending}
          error={active.error}
        />
      </Card>

      {toCheck.length > 0 && (
        <div ref={checkRef} tabIndex={-1} className="scroll-mt-4 rounded-2xl outline-none focus-visible:ring-2 focus-visible:ring-accent">
          <Card title={`단가 확인이 필요한 거래 ${toCheck.length}건`}>
            <p className="mb-2 text-sm text-ink-2">
              평균단가가 현재가와 20배 이상 다릅니다. 스크린샷에서 원화 금액이나 총액을 단가로 읽었을 수 있어요.
              수정을 눌러 실제 매수가와 매수일을 입력하세요.
            </p>
            <ul className="divide-y divide-line" aria-label="단가 확인 대상 거래">
              {toCheck.map((t) => (
                <li key={t.id} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 py-3">
                  <div className="min-w-0">
                    <Link to={`/assets/${t.symbol}`} className="text-[15px] font-semibold text-ink hover:underline">
                      {displaySymbol(t.symbol)}
                    </Link>
                    <div className="num text-[13px] text-muted">
                      {formatDate(t.trade_date, 'long')} · {t.side === 'buy' ? '매수' : '매도'} {formatQty(t.quantity)}
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="num text-[15px] font-semibold text-danger" title={PRICE_CHECK_REASON}>
                      {money(t, t.price)}
                    </span>
                    <button
                      type="button"
                      onClick={() => edit(t)}
                      className="rounded-lg bg-ink px-3 py-1.5 text-xs font-medium text-surface"
                    >
                      수정
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      )}

      <Card title="배당·액면분할">
        <CorporateActions />
      </Card>

      <Card
        title="거래 내역"
        actions={
          <SegmentedControl
            label="자산 유형 필터"
            value={filter}
            onChange={setFilter}
            options={[
              { value: 'all', label: '전체' },
              { value: 'stock', label: '주식' },
              { value: 'crypto', label: '코인' },
            ]}
          />
        }
      >
        {remove.error ? <div className="mb-3"><ErrorBox error={remove.error} /></div> : null}
        {transactions.error ? (
          <ErrorBox error={transactions.error} />
        ) : !transactions.data ? (
          <Muted>불러오는 중…</Muted>
        ) : rows.length === 0 ? (
          <Muted>거래 내역이 없습니다.</Muted>
        ) : (
          <>
          <BulkDelete transactions={transactions.data} />
          <div className="-mx-5 overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs text-muted">
                  <th className="px-5 py-2 font-medium">거래일</th>
                  <th className="px-3 py-2 font-medium">종목</th>
                  <th className="px-3 py-2 font-medium">구분</th>
                  <th className="px-3 py-2 text-right font-medium">수량</th>
                  <th className="px-3 py-2 text-right font-medium">단가</th>
                  <th className="px-3 py-2 text-right font-medium">금액</th>
                  <th className="px-3 py-2 text-right font-medium">수수료</th>
                  <th className="px-5 py-2 text-right font-medium" aria-label="작업" />
                </tr>
              </thead>
              <tbody className="num">
                {rows.map((t) => (
                  <tr key={t.id} className="border-b border-line last:border-0 hover:bg-hover">
                    <td className="px-5 py-2.5 whitespace-nowrap text-ink-2" title={t.trade_date}>
                      {formatDate(t.trade_date, 'short')}
                    </td>
                    <td className="px-3 py-2.5">
                      <Link to={`/assets/${t.symbol}`} className="font-semibold hover:underline">
                        {displaySymbol(t.symbol)}
                      </Link>
                      {t.note && <span className="ml-2 text-xs text-muted">{t.note}</span>}
                    </td>
                    <td className={`px-3 py-2.5 ${t.side === 'buy' ? 'text-gain' : 'text-loss'}`}>
                      {t.side === 'buy' ? '매수' : '매도'}
                    </td>
                    <td className="px-3 py-2.5 text-right">{formatQty(t.quantity)}</td>
                    <td className="px-3 py-2.5 text-right whitespace-nowrap">
                      {money(t, t.price)}
                      {flagged.has(t.id) && (
                        <span
                          className="ml-1.5 rounded-md bg-danger/10 px-1.5 py-0.5 text-[11px] font-semibold text-danger"
                          title={PRICE_CHECK_REASON}
                        >
                          단가 확인
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-right font-medium">{money(t, t.quantity * t.price)}</td>
                    <td className="px-3 py-2.5 text-right text-ink-2">{money(t, t.fee)}</td>
                    <td className="px-5 py-2.5 text-right whitespace-nowrap">
                      {confirmId === t.id ? (
                        <>
                          <button
                            className="mr-2 text-danger hover:underline"
                            onClick={() => remove.mutate(t.id, { onSettled: () => setConfirmId(null) })}
                          >
                            삭제 확인
                          </button>
                          <button className="text-ink-2 hover:underline" onClick={() => setConfirmId(null)}>
                            취소
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            className={`mr-3 hover:underline ${flagged.has(t.id) ? 'font-semibold text-accent' : 'text-ink-2'}`}
                            onClick={() => edit(t)}
                          >
                            수정
                          </button>
                          <button className="text-ink-2 hover:underline" onClick={() => setConfirmId(t.id)}>
                            삭제
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </>
        )}
      </Card>
    </div>
  )
}
