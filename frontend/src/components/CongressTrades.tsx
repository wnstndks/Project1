import { Link } from 'react-router-dom'

import type { CongressStatus, CongressTrade } from '../api/client'
import { useCongressStatus, useCongressTrades, useSyncCongress } from '../api/hooks'
import { amountRange, distinctMembers, groupBySymbol, memberLine, sideLabel, type SymbolGroup } from '../lib/congress'
import { displaySymbol, formatDate } from '../lib/format'
import { Card, Disclosure, ErrorBox, Skeleton } from './ui'

/** How far back both the Compare card and the asset-detail line look. */
export const CONGRESS_DAYS = 180
/** Trades shown per ticker before the "더 보기" fold. */
const SHOWN = 3

const TITLE = '내 종목을 최근 거래한 미국 하원 의원'

/**
 * Compare-page card: House members' STOCK Act filings that name one of my tickers, grouped per
 * ticker, newest first. The backend's `coverage_note` (delay, amount bands, no Senate, not advice)
 * is shown as sent. Buys and sells are neutral badges: these are public filings, not signals, so
 * no gain/loss colour or ▲▼. `symbols` undefined means my holdings are still loading.
 */
export function CongressTrades({ symbols, days = CONGRESS_DAYS }: { symbols: string[] | undefined; days?: number }) {
  const list = symbols ?? []
  const trades = useCongressTrades(list, days)
  // With nothing to ask about, the trades query is off; the status still gives the caveats.
  const status = useCongressStatus(symbols !== undefined && list.length === 0)
  const sync = useSyncCongress()

  const info: CongressStatus | undefined = trades.data?.status ?? status.data
  const syncing = trades.data?.syncing === true || sync.isPending
  const canSync = info !== undefined && info.docs_pending > 0

  const body = () => {
    if (symbols === undefined) return <Skeleton className="h-24" />
    if (list.length === 0) {
      if (status.error) return <ErrorBox error={status.error} />
      return <p className="py-4 text-[15px] text-ink-2">보유한 주식이 없어 보여 줄 거래가 없습니다.</p>
    }
    if (trades.error) return <ErrorBox error={trades.error} />
    if (!trades.data) return <Skeleton className="h-24" />
    if (trades.data.trades.length === 0) {
      if (!trades.data.syncing)
        return (
          <p className="py-4 text-[15px] text-ink-2">
            최근 {days}일 안에 내 종목을 거래한 하원 의원 공시가 없습니다.
          </p>
        )
      return (
        <div>
          <Skeleton className="h-24" />
          <p role="status" className="mt-3 text-sm text-ink-2">
            공시 문서를 받는 중입니다. 받는 대로 자동으로 채워집니다.
          </p>
        </div>
      )
    }
    return (
      <>
        {trades.data.syncing && (
          <p role="status" className="mb-3 text-sm text-ink-2">
            공시 문서를 더 받는 중입니다. 받는 대로 자동으로 채워집니다.
          </p>
        )}
        <div className="divide-y divide-line">
          {groupBySymbol(trades.data.trades).map((g) => (
            <SymbolSection key={g.symbol} group={g} />
          ))}
        </div>
      </>
    )
  }

  return (
    <Card
      title={TITLE}
      actions={
        canSync && (
          <button
            type="button"
            onClick={() => sync.mutate()}
            disabled={syncing}
            className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium hover:bg-hover disabled:opacity-50"
          >
            지금 받기
          </button>
        )
      }
    >
      {info && <StatusLines status={info} />}
      {body()}
    </Card>
  )
}

/** The coverage note as sent, then one line of sync facts: index date, unreadable scans, backlog. */
function StatusLines({ status }: { status: CongressStatus }) {
  const facts: string[] = []
  if (status.index_modified) facts.push(`색인 갱신 ${formatDate(status.index_modified)}`)
  if (status.docs_no_text > 0) facts.push(`${status.docs_no_text}건은 스캔 문서라 읽지 못했습니다`)
  // Batch size and count are backend settings; the screen only says that a backlog remains.
  if (status.docs_pending > 0) facts.push(`${status.docs_pending}건 더 받는 중`)
  return (
    <div className="mb-4 space-y-1">
      <p className="text-xs leading-relaxed text-ink-2">{status.coverage_note}</p>
      {facts.length > 0 && <p className="num text-xs text-muted">{facts.join(' · ')}</p>}
      {status.stale && (
        <p className="text-xs text-muted">마지막으로 받은 지 오래되어 최근 공시가 빠져 있을 수 있습니다.</p>
      )}
      {status.error && <p className="text-xs text-danger">최근 갱신 실패: {status.error}</p>}
    </div>
  )
}

/** One ticker: header with the trade count, the newest trades, the rest behind "더 보기". */
function SymbolSection({ group }: { group: SymbolGroup }) {
  const head = group.trades.slice(0, SHOWN)
  const rest = group.trades.slice(SHOWN)
  return (
    <section className="py-3 first:pt-0 last:pb-0" aria-label={`${displaySymbol(group.symbol)} 하원 의원 거래`}>
      <header className="flex flex-wrap items-baseline gap-x-2">
        <Link to={`/assets/${encodeURIComponent(group.symbol)}`} className="text-[15px] font-bold text-ink hover:underline">
          {displaySymbol(group.symbol)}
        </Link>
        <span className="truncate text-xs text-muted">{group.name}</span>
        <span className="num text-xs text-muted">
          · 의원 {distinctMembers(group.trades)}명 · {group.trades.length}건
        </span>
      </header>
      <ul className="mt-1">
        {/* A filing can list the same trade twice (two lots); the index keeps keys unique. */}
        {head.map((t, i) => (
          <TradeRow key={`${t.doc_id}:${t.transaction_date}:${t.member}:${t.side}:${t.amount_low}:${i}`} trade={t} />
        ))}
      </ul>
      {rest.length > 0 && (
        <Disclosure summary={`더 보기 (${rest.length}건)`}>
          <ul>
            {rest.map((t, i) => (
              <TradeRow key={`${t.doc_id}:${t.transaction_date}:${t.member}:${t.side}:${t.amount_low}:${SHOWN + i}`} trade={t} />
            ))}
          </ul>
        </Disclosure>
      )}
    </section>
  )
}

function TradeRow({ trade }: { trade: CongressTrade }) {
  return (
    <li className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 py-1.5 text-[14px]">
      {/* Neutral badge on purpose: a filing is not a gain or a loss, so no gain/loss colour or ▲▼. */}
      <span className="rounded-md bg-fill px-1.5 py-0.5 text-[11px] font-semibold text-ink">{sideLabel(trade.side)}</span>
      <span className="font-medium text-ink">{memberLine(trade)}</span>
      <span className="num text-ink-2">{amountRange(trade.amount_low, trade.amount_high)}</span>
      <span className="num text-xs text-muted">
        거래 {formatDate(trade.transaction_date)} · 공시 {formatDate(trade.filing_date)}
      </span>
      <a
        href={trade.doc_url}
        target="_blank"
        rel="noopener noreferrer"
        className="text-xs text-accent hover:underline"
        aria-label={`${trade.member} 공시 원문 (새 탭)`}
      >
        원문
      </a>
    </li>
  )
}

/**
 * One line for the asset page: how many House members traded this symbol recently, linking to the
 * Compare card. Nothing while loading, with no trades, or without a symbol.
 */
export function CongressMention({ symbol, days = CONGRESS_DAYS }: { symbol: string; days?: number }) {
  const trades = useCongressTrades(symbol ? [symbol] : [], days)
  const members = trades.data ? distinctMembers(trades.data.trades) : 0
  if (!symbol || members === 0) return null
  return (
    <p className="mt-1 text-sm text-ink-2">
      <Link to="/compare#congress" className="num text-ink hover:underline">
        최근 {days}일 이 종목을 거래한 하원 의원 {members}명
      </Link>
    </p>
  )
}
