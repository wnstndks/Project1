import { useState } from 'react'
import { Link } from 'react-router-dom'

import type { Guru, GuruCompare } from '../api/client'
import { useBenchmark, useGuruCompare, useGuruHoldings, useHoldings, usePortfolioHistory, useSyncGurus } from '../api/hooks'
import { BenchmarkChart } from '../components/BenchmarkChart'
import { GuruOverlap } from '../components/GuruOverlap'
import { Card, ErrorBox, Muted, SegmentedControl, Skeleton } from '../components/ui'
import {
  BENCHMARK_ORDER,
  benchmarkLabel,
  benchmarkStyle,
  DEFAULT_BENCHMARKS,
  toggleBenchmark,
} from '../lib/benchmarks'
import { displaySymbol } from '../lib/format'
import { isLoaded, needsSecUserAgent, pct, sourceLabel } from '../lib/gurus'
import { MIN_HISTORY_DAYS, historySpanDays } from '../lib/history'
import { RANGE_OPTIONS, rangeStart, type RangeKey } from '../lib/ranges'

const SEC_HINT =
  "backend/.env에 AM_SEC_USER_AGENT를 '앱이름 이메일' 형식으로 넣으면 버핏 등 13F 투자자도 보여요."

/**
 * Compare page: my value against benchmarks fed with my own cash flows, which of my tickers each
 * well-known investor holds, and one investor's top positions. Limits of the sources are stated up
 * front; nothing here is investment advice.
 */
export function Compare() {
  return (
    <div className="space-y-6">
      <header>
        <Link to="/" className="text-xs text-muted hover:underline">← 홈</Link>
        <h1 className="mt-2 text-2xl font-bold">유명 투자자와 비교</h1>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-ink-2">
          캐시 우드는 ARK 액티브 ETF의 보유 종목이지 개인 계좌가 아닙니다. 버핏 등 다른 투자자는 SEC 13F 보고서로,
          분기 말 뒤 최대 45일 지연되고 미국 상장 롱 포지션만 담겨 현금·공매도·옵션은 빠져 있습니다. 공개 자료를 그대로
          옮긴 참고 정보이며 투자 조언이 아닙니다.
        </p>
      </header>
      <BenchmarkSection />
      <OverlapSection />
      <HoldingsSection />
    </div>
  )
}

/** Section 1: the same won flows into each benchmark. Needs a week of history to say anything. */
function BenchmarkSection() {
  const full = usePortfolioHistory(undefined)
  const days = full.data ? historySpanDays(full.data) : undefined
  const enough = days !== undefined && days >= MIN_HISTORY_DAYS
  const [range, setRange] = useState<RangeKey>('1Y')
  const [selected, setSelected] = useState<string[]>(DEFAULT_BENCHMARKS)
  // All five come in one request (the server caches each symbol); toggling is then instant.
  const benchmark = useBenchmark(BENCHMARK_ORDER, rangeStart(range), enough)

  return (
    <Card
      title="같은 날 같은 돈을 넣었다면"
      actions={enough && <SegmentedControl label="기간" options={RANGE_OPTIONS} value={range} onChange={setRange} />}
    >
      {full.error ? (
        <ErrorBox error={full.error} />
      ) : days === undefined ? (
        <Skeleton className="h-64" />
      ) : !enough ? (
        <p className="py-4 text-[15px] leading-relaxed text-ink-2">
          거래일이 쌓이면 비교할 수 있어요 —{' '}
          <Link to="/transactions" className="text-accent underline">
            가져온 거래의 매수일
          </Link>
          을 실제 날짜로 고치면 바로 보여요.
        </p>
      ) : (
        <>
          <div role="group" aria-label="벤치마크" className="mb-3 flex flex-wrap gap-1.5">
            {BENCHMARK_ORDER.map((symbol) => {
              const on = selected.includes(symbol)
              const style = benchmarkStyle(symbol)
              return (
                <button
                  key={symbol}
                  type="button"
                  aria-pressed={on}
                  onClick={() => setSelected((prev) => toggleBenchmark(prev, symbol))}
                  className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px] font-medium transition-colors focus-visible:outline-2 focus-visible:outline-accent ${
                    on ? 'bg-accent-soft text-accent' : 'bg-fill text-ink-2 hover:text-ink'
                  }`}
                >
                  <span
                    aria-hidden="true"
                    className="inline-block w-3 border-t-2"
                    style={{
                      borderColor: on ? `var(${style.cssVar})` : 'var(--axis)',
                      borderStyle: style.dash ? 'dashed' : 'solid',
                    }}
                  />
                  {benchmarkLabel(symbol)}
                </button>
              )
            })}
          </div>
          {benchmark.error ? (
            <ErrorBox error={benchmark.error} />
          ) : benchmark.data ? (
            <div className={benchmark.isPlaceholderData ? 'opacity-50 transition-opacity' : ''}>
              <BenchmarkChart data={benchmark.data} selected={selected} />
            </div>
          ) : (
            <Skeleton className="h-64" />
          )}
          <p className="mt-3 text-xs text-muted">
            내 매수·매도 날짜와 금액을 그대로 그 종목에 넣었다고 가정한 비교입니다. 수수료·세금은 뺐고, 과거 성과는
            미래를 보장하지 않습니다. 투자 조언이 아닙니다.
          </p>
        </>
      )}
    </Card>
  )
}

/** Section 2: one card per investor with their overlap with my holdings. */
function OverlapSection() {
  const compare = useGuruCompare()
  const sync = useSyncGurus()
  if (compare.error)
    return (
      <Card title="유명 투자자와 겹치는 종목">
        <ErrorBox error={compare.error} />
      </Card>
    )
  if (!compare.data)
    return (
      <Card title="유명 투자자와 겹치는 종목">
        <Skeleton className="h-40" />
      </Card>
    )
  const { syncing, gurus } = compare.data
  const secMissing = gurus.filter((g) => needsSecUserAgent(g.guru))
  const shown = gurus.filter((g) => !needsSecUserAgent(g.guru))
  return (
    <Card
      title="유명 투자자와 겹치는 종목"
      actions={
        <button
          type="button"
          onClick={() => sync.mutate()}
          disabled={syncing || sync.isPending}
          className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium hover:bg-hover disabled:opacity-50"
        >
          다시 불러오기
        </button>
      }
    >
      {syncing && (
        <p role="status" className="mb-3 text-sm text-ink-2">
          처음 불러오는 중(수십 초)… 받는 대로 자동으로 채워집니다.
        </p>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        {shown.map((g) => (
          <GuruCard key={g.guru.id} item={g} />
        ))}
      </div>
      {secMissing.length > 0 && (
        <p className="mt-4 text-xs text-muted">
          {SEC_HINT} <span>({secMissing.map((g) => g.guru.name_ko).join(', ')})</span>
        </p>
      )}
    </Card>
  )
}

function GuruCard({ item }: { item: GuruCompare }) {
  const { guru, overlaps, top_missing } = item
  const loaded = isLoaded(guru)
  return (
    <section className="rounded-xl border border-line p-4">
      <GuruHeader guru={guru} />
      <div className="mt-3">
        {guru.error && !loaded ? (
          <p className="text-sm text-danger">{guru.error}</p>
        ) : !loaded ? (
          <p className="text-sm text-muted">아직 자료가 없습니다.</p>
        ) : (
          <GuruOverlap name={guru.name_ko} overlaps={overlaps} missing={top_missing} />
        )}
      </div>
    </section>
  )
}

/** Name, source, snapshot date and the standing caveats for one investor. */
function GuruHeader({ guru }: { guru: Guru }) {
  const loaded = isLoaded(guru)
  return (
    <header>
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <h3 className="text-[15px] font-bold text-ink">{guru.name_ko}</h3>
        <span className="text-xs text-muted">{guru.name_en}</span>
        {guru.stale && loaded && (
          <span className="rounded-md bg-fill px-1.5 py-0.5 text-[11px] font-semibold text-ink-2">오래된 자료</span>
        )}
      </div>
      <div className="num mt-0.5 text-xs text-muted">
        {sourceLabel(guru.source)}
        {guru.as_of && ` · 기준일 ${guru.as_of}`}
        {loaded && ` · ${guru.holdings_count}종목`}
      </div>
      <p className="mt-1 text-xs text-ink-2">{guru.note}</p>
      {guru.sync_note && <p className="mt-1 text-xs text-muted">{guru.sync_note}</p>}
      {guru.error && loaded && <p className="mt-1 text-xs text-danger">최근 갱신 실패: {guru.error}</p>}
    </header>
  )
}

/** Section 3: pick an investor, see their twenty largest positions. */
function HoldingsSection() {
  const compare = useGuruCompare()
  const mine = useHoldings()
  const [picked, setPicked] = useState<string | undefined>(undefined)
  const candidates = (compare.data?.gurus ?? []).map((g) => g.guru).filter((g) => !needsSecUserAgent(g))
  const current = picked ?? candidates.find((g) => isLoaded(g))?.id ?? candidates[0]?.id
  const holdings = useGuruHoldings(current, 20)
  const held = new Set((mine.data ?? []).map((h) => h.symbol.toUpperCase()))

  return (
    <Card title="투자자별 상위 20종목">
      {candidates.length === 0 ? (
        <Muted>{compare.data ? '보여 줄 투자자가 없습니다.' : '불러오는 중…'}</Muted>
      ) : (
        <>
          <div role="group" aria-label="투자자 선택" className="mb-4 flex flex-wrap gap-1.5">
            {candidates.map((g) => {
              const on = g.id === current
              return (
                <button
                  key={g.id}
                  type="button"
                  aria-pressed={on}
                  onClick={() => setPicked(g.id)}
                  className={`rounded-full px-3 py-1 text-[13px] font-medium transition-colors focus-visible:outline-2 focus-visible:outline-accent ${
                    on ? 'bg-accent-soft text-accent' : 'bg-fill text-ink-2 hover:text-ink'
                  }`}
                >
                  {g.name_ko}
                </button>
              )
            })}
          </div>
          {holdings.error ? (
            <ErrorBox error={holdings.error} />
          ) : !holdings.data ? (
            <Skeleton className="h-40" />
          ) : (
            <div className={holdings.isPlaceholderData ? 'opacity-50 transition-opacity' : ''}>
              <GuruHeader guru={holdings.data.guru} />
              {holdings.data.holdings.length === 0 ? (
                <p className="mt-3 text-sm text-muted">
                  {compare.data?.syncing ? '처음 불러오는 중(수십 초)…' : '아직 자료가 없습니다.'}
                </p>
              ) : (
                <>
                  <table className="mt-3 w-full text-sm">
                    <thead>
                      <tr className="text-left text-xs text-muted">
                        <th scope="col" className="py-1.5 pr-2 font-medium">종목</th>
                        <th scope="col" className="py-1.5 pr-2 font-medium">이름</th>
                        <th scope="col" className="py-1.5 text-right font-medium">비중</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line">
                      {holdings.data.holdings.map((h, i) => {
                        const own = h.symbol !== null && held.has(h.symbol.toUpperCase())
                        return (
                          <tr key={`${h.symbol ?? h.cusip ?? ''}:${i}`}>
                            <td className="py-2 pr-2 font-semibold text-ink">
                              {h.symbol ? (
                                <Link to={`/assets/${encodeURIComponent(h.symbol)}`} className="hover:underline">
                                  {displaySymbol(h.symbol)}
                                </Link>
                              ) : (
                                <span className="font-normal text-muted">—</span>
                              )}
                              {own && (
                                <span className="ml-1.5 rounded-md bg-accent-soft px-1.5 py-0.5 text-[11px] font-semibold text-accent">
                                  보유 중
                                </span>
                              )}
                            </td>
                            <td className="py-2 pr-2 text-ink-2">{h.name}</td>
                            <td className="num py-2 text-right">{pct(h.weight_pct)}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                  <p className="mt-2 text-xs text-muted">
                    전체 {holdings.data.total}종목 중 상위 {holdings.data.holdings.length}개. 티커가 없는 행은 비상장·현금
                    등으로 이름만 표시합니다. 투자 조언이 아닙니다.
                  </p>
                </>
              )}
            </div>
          )}
        </>
      )}
    </Card>
  )
}
