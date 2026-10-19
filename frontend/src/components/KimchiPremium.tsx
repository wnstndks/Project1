import { useKimchi } from '../api/hooks'
import { displaySymbol, formatKrw, formatPct } from '../lib/format'
import { Muted } from './ui'

/** Upbit KRW price vs. the global USD price at today's rate. Reference information only. */
export function KimchiPremium() {
  const kimchi = useKimchi()
  if (kimchi.error) return <Muted>시세를 불러오지 못했습니다.</Muted>
  if (!kimchi.data) return <Muted>불러오는 중…</Muted>

  return (
    <div>
      <ul className="space-y-1.5 text-sm">
        {kimchi.data.map((k) => (
          <li key={k.symbol} className="num flex items-center justify-between gap-3">
            <span className="font-medium">{displaySymbol(k.symbol)}</span>
            <span className="text-muted">{formatKrw(k.upbit_krw)}</span>
            <span className="w-16 text-right font-semibold">{formatPct(k.premium_pct)}</span>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs text-muted">
        업비트 원화 가격이 해외 시세×환율보다 비싼 정도입니다. 업비트에 보유한 코인은 업비트 가격으로 평가합니다.
      </p>
    </div>
  )
}
