import { useState } from 'react'
import { Link } from 'react-router-dom'

import type { AssetType, Transaction, TransactionInput } from '../api/client'
import {
  useCreateTransaction,
  useDeleteTransaction,
  useTransactions,
  useUpdateTransaction,
} from '../api/hooks'
import { TransactionForm } from '../components/TransactionForm'
import { Card, ErrorBox, Muted, SegmentedControl } from '../components/ui'
import { useMoney } from '../lib/currency'
import { displaySymbol, formatQty } from '../lib/format'

type Filter = 'all' | AssetType

export function Transactions() {
  const transactions = useTransactions()
  const create = useCreateTransaction()
  const update = useUpdateTransaction()
  const remove = useDeleteTransaction()
  const [editing, setEditing] = useState<Transaction | null>(null)
  const [filter, setFilter] = useState<Filter>('all')
  const [confirmId, setConfirmId] = useState<number | null>(null)
  const { currency, format } = useMoney()
  // KRW amounts use the rate on each trade's own date, not today's.
  const money = (t: Transaction, usd: number) =>
    format(currency === 'KRW' && t.usd_krw ? usd * t.usd_krw : usd)

  const save = async (data: TransactionInput) => {
    if (editing) {
      await update.mutateAsync({ id: editing.id, data })
      setEditing(null)
    } else {
      await create.mutateAsync(data)
    }
  }
  const active = editing ? update : create

  const rows = (transactions.data ?? []).filter((t) => filter === 'all' || t.asset_type === filter)

  return (
    <div className="space-y-6">
      <Card title={editing ? `거래 수정 #${editing.id}` : '거래 추가'}>
        <TransactionForm
          key={editing?.id ?? 'new'}
          editing={editing}
          onSubmit={(data) => save(data).catch(() => undefined)}
          onCancel={() => {
            setEditing(null)
            update.reset()
          }}
          pending={active.isPending}
          error={active.error}
        />
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
                    <td className="px-5 py-2.5 text-ink-2">{t.trade_date}</td>
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
                    <td className="px-3 py-2.5 text-right">{money(t, t.price)}</td>
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
                            className="mr-3 text-ink-2 hover:underline"
                            onClick={() => {
                              setEditing(t)
                              window.scrollTo({ top: 0, behavior: 'smooth' })
                            }}
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
        )}
      </Card>
    </div>
  )
}
