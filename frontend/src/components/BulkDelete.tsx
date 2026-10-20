import { useState } from 'react'

import type { Transaction } from '../api/client'
import { useDeleteAllTransactions } from '../api/hooks'
import { ErrorBox } from './ui'

/** Matches the note the backend puts on screenshot imports. */
const IMPORT_NOTE = '스크린샷 가져오기'

type Scope = 'all' | 'imports'

/** Clear the ledger, or only what a screenshot import added, after an explicit confirmation. */
export function BulkDelete({ transactions }: { transactions: Transaction[] }) {
  const [pending, setPending] = useState<Scope | null>(null)
  const remove = useDeleteAllTransactions()
  const imported = transactions.filter((t) => t.note === IMPORT_NOTE).length
  const count = pending === 'imports' ? imported : transactions.length

  const button = 'rounded-lg border border-line px-3 py-1.5 text-xs font-medium hover:bg-hover disabled:opacity-50'
  return (
    <div className="mb-4 space-y-2">
      {pending ? (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-line px-4 py-3 text-sm">
          <span>
            {pending === 'imports' ? '스크린샷으로 가져온' : '모든'} 거래 {count}건을 삭제할까요? 되돌릴 수 없습니다.
          </span>
          <button
            type="button"
            className={`${button} text-loss`}
            disabled={remove.isPending}
            onClick={() => remove.mutate(pending, { onSuccess: () => setPending(null) })}
          >
            {remove.isPending ? '삭제 중…' : `${count}건 삭제`}
          </button>
          <button type="button" className={button} onClick={() => setPending(null)}>
            취소
          </button>
        </div>
      ) : (
        <div className="flex flex-wrap justify-end gap-2">
          {imported > 0 && (
            <button type="button" className={button} onClick={() => setPending('imports')}>
              가져온 거래만 삭제 ({imported})
            </button>
          )}
          <button type="button" className={button} onClick={() => setPending('all')}>
            전체 삭제
          </button>
        </div>
      )}
      {remove.error && <ErrorBox error={remove.error} />}
    </div>
  )
}
