import { Link } from 'react-router-dom'

import { useBenchmark, useGuruCompare, usePortfolioHistory } from '../api/hooks'
import { latestPair } from '../lib/benchmarks'
import { useMoney } from '../lib/currency'
import { isLoaded, needsSecUserAgent, overlapCounts, overlapSentence } from '../lib/gurus'
import { MIN_HISTORY_DAYS, historySpanDays } from '../lib/history'
import { Card } from './ui'

const HOME_BENCHMARK = 'SPY'

/**
 * Home card: how many of my tickers each investor holds (up to three investors), and one line of
 * "same money in SPY" once there is at least a week of history. Links to the compare page.
 */
export function CompareCard() {
  const compare = useGuruCompare()
  // Same query as the dashboard's history section, so this is served from cache.
  const history = usePortfolioHistory(undefined)
  const days = history.data ? historySpanDays(history.data) : 0
  const enough = days >= MIN_HISTORY_DAYS
  const benchmark = useBenchmark([HOME_BENCHMARK], undefined, enough)
  const { pick, format } = useMoney()

  const gurus = compare.data?.gurus ?? []
  const counts = overlapCounts(gurus)
  const loaded = gurus.filter((g) => isLoaded(g.guru)).length
  const secMissing = gurus.some((g) => needsSecUserAgent(g.guru))
  const pair = benchmark.data ? latestPair(benchmark.data.mine, benchmark.data.benchmarks, HOME_BENCHMARK) : undefined

  return (
    <Card
      title="유명 투자자와 비교"
      actions={
        <Link to="/compare" className="text-sm text-accent hover:underline">
          자세히 →
        </Link>
      }
    >
      <div className="space-y-1.5 text-[15px] text-ink-2">
        {compare.error ? (
          <p className="text-danger">비교 자료를 불러오지 못했습니다.</p>
        ) : !compare.data || (compare.data.syncing && loaded === 0) ? (
          <p>불러오는 중…</p>
        ) : counts.length > 0 ? (
          <p className="num">{overlapSentence(counts)}</p>
        ) : loaded > 0 ? (
          <p>내 보유 종목을 들고 있는 유명 투자자가 없습니다.</p>
        ) : (
          <p>아직 투자자 자료가 없습니다.</p>
        )}
        {secMissing && (
          <p className="text-xs text-muted">
            backend/.env에 AM_SEC_USER_AGENT를 넣으면 버핏 등 13F 투자자도 비교할 수 있어요.
          </p>
        )}
        {enough && pair && (
          <p className="num">
            같은 돈을 {HOME_BENCHMARK}에 넣었다면 지금 약 {format(pick(pair.benchmark.usd, pair.benchmark.krw))}
            <span className="text-muted"> (내 자산 {format(pick(pair.mine.usd, pair.mine.krw))})</span>
          </p>
        )}
      </div>
    </Card>
  )
}
