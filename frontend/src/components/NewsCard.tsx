import type { News } from '../api/client'
import { useNews } from '../api/hooks'
import { ErrorBox, Muted } from './ui'

type Article = News['articles'][number]

function label(a: Article): { text: string; tone: string; icon: string } {
  const score = a.positive - a.negative
  if (a.neutral >= Math.max(a.positive, a.negative) || Math.abs(score) < 0.2)
    return { text: '중립', tone: 'text-ink-2', icon: '•' }
  return score > 0
    ? { text: '긍정', tone: 'text-gain', icon: '▲' }
    : { text: '부정', tone: 'text-loss', icon: '▼' }
}

function relative(iso: string): string {
  // published_at is UTC without an offset.
  const ms = Date.now() - new Date(`${iso}Z`).getTime()
  const h = Math.round(ms / 3_600_000)
  if (h < 1) return '방금'
  if (h < 24) return `${h}시간 전`
  return `${Math.round(h / 24)}일 전`
}

export function NewsCard({ symbol }: { symbol: string }) {
  const news = useNews(symbol)

  if (news.error) return <ErrorBox error={news.error} />
  if (!news.data) return <Muted>해외 뉴스를 모으는 중… (처음에는 30초 정도 걸립니다)</Muted>

  const { articles, days, finnhub_enabled, warnings } = news.data
  const tones = days.map((d) => d.tone).filter((t): t is number => t != null)
  const avgTone = tones.length ? tones.reduce((a, b) => a + b, 0) / tones.length : null
  const recent = articles.slice(0, 8)
  const scored = articles.length
    ? articles.reduce((s, a) => s + a.positive - a.negative, 0) / articles.length
    : null

  return (
    <div className="space-y-4">
      {warnings.length > 0 && (
        <p className="text-xs text-muted">
          일부 뉴스 소스를 갱신하지 못해 저장된 데이터를 보여줍니다 ({warnings.join(' · ')})
        </p>
      )}
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <div className="text-xs text-muted">헤드라인 감성 (FinBERT, 최근 {articles.length}건)</div>
          <div className="mt-1 font-semibold">
            {scored == null ? '—' : `${scored >= 0 ? '+' : '−'}${Math.abs(scored).toFixed(2)}`}
            <span className="ml-1 text-xs font-normal text-muted">−1 부정 ~ +1 긍정</span>
          </div>
        </div>
        <div>
          <div className="text-xs text-muted">해외 뉴스 논조 (GDELT, 30일 평균)</div>
          <div className="mt-1 font-semibold">
            {avgTone == null ? '—' : avgTone.toFixed(2)}
            <span className="ml-1 text-xs font-normal text-muted">0보다 크면 긍정적</span>
          </div>
        </div>
      </div>

      {!finnhub_enabled ? (
        <p className="text-xs text-muted">
          기사 헤드라인을 보려면 <code className="rounded bg-hover px-1">backend/.env</code>에{' '}
          <code className="rounded bg-hover px-1">AM_FINNHUB_API_KEY</code>를 설정하세요(finnhub.io 무료 가입).
        </p>
      ) : recent.length === 0 ? (
        <Muted>최근 기사가 없습니다.</Muted>
      ) : (
        <ul className="divide-y divide-[var(--border)]">
          {recent.map((a) => {
            const l = label(a)
            return (
              <li key={a.url} className="flex gap-3 py-2.5 text-sm">
                <span className={`w-12 shrink-0 text-xs font-medium ${l.tone}`}>
                  <span aria-hidden="true">{l.icon}</span> {l.text}
                </span>
                <div className="min-w-0">
                  <a href={a.url} target="_blank" rel="noreferrer noopener" className="hover:underline">
                    {a.headline}
                  </a>
                  <div className="mt-0.5 text-xs text-muted">
                    {a.source} · {relative(a.published_at)}
                  </div>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
