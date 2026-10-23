import { useState, type FormEvent } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'

import { SegmentedControl } from './components/ui'
import { useCurrency, type Currency } from './lib/currency'
import { useTheme, type Theme } from './lib/theme'

type Options<T extends string> = { value: T; label: string }[]
const CURRENCY_LONG: Options<Currency> = [
  { value: 'KRW', label: '₩ 원화' },
  { value: 'USD', label: '$ 달러' },
]
const CURRENCY_SHORT: Options<Currency> = [
  { value: 'KRW', label: '₩' },
  { value: 'USD', label: '$' },
]
const THEME_LONG: Options<Theme> = [
  { value: 'light', label: '밝게' },
  { value: 'dark', label: '어둡게' },
  { value: 'system', label: '시스템' },
]
// Sun and moon as text glyphs (not emoji), so they follow the text color like the other labels.
const THEME_SHORT: Options<Theme> = [
  { value: 'light', label: '☀' },
  { value: 'dark', label: '☾' },
  { value: 'system', label: '자동' },
]

/**
 * A segmented control with short labels on phones and full labels from `sm` up. The unused
 * variant is `display: none`, so only one radio group exists for assistive tech at a time.
 */
function Toggle<T extends string>({ label, value, onChange, short, long }: {
  label: string
  value: T
  onChange: (v: T) => void
  short: Options<T>
  long: Options<T>
}) {
  return (
    <>
      <div className="sm:hidden">
        <SegmentedControl label={label} value={value} onChange={onChange} options={short} />
      </div>
      <div className="hidden sm:block">
        <SegmentedControl label={label} value={value} onChange={onChange} options={long} />
      </div>
    </>
  )
}

const navClass = ({ isActive }: { isActive: boolean }) =>
  `shrink-0 whitespace-nowrap rounded-md px-3 py-1.5 text-sm ${isActive ? 'bg-hover font-semibold text-ink' : 'text-ink-2 hover:text-ink'}`

/** A nav label with a shorter form on phones; the long one is hidden there, not just truncated. */
function NavLabel({ short, long }: { short: string; long: string }) {
  return (
    <>
      <span className="sm:hidden">{short}</span>
      <span className="hidden sm:inline">{long}</span>
    </>
  )
}

/**
 * Header on wide screens: brand · nav · currency · theme · search in one row. On phones the brand
 * and the two toggles (short labels: ₩/$ and ☀/☾/자동) share the first row; the nav and the search
 * box take the second, where the nav wraps onto a second line rather than scrolling (every link
 * stays visible, nothing is clipped). On a 360px phone the toggles drop to their own row instead
 * of overflowing. That second-row wrapper needs `min-w-0`: as a flex item its automatic minimum
 * width would otherwise be the nowrap links' full width, pushing the document wider than a 390px
 * phone. `sm:contents` dissolves the wrapper on wide screens.
 */
export function Layout() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const { currency, setCurrency } = useCurrency()
  const { theme, setTheme } = useTheme()

  const onSearch = (e: FormEvent) => {
    e.preventDefault()
    const symbol = search.trim().toUpperCase()
    if (symbol) navigate(`/assets/${encodeURIComponent(symbol)}`)
    setSearch('')
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
          <span className="shrink-0 font-semibold">Asset Manager</span>
          <div className="ml-auto flex shrink-0 items-center gap-2 sm:order-2">
            <Toggle label="표시 통화" value={currency} onChange={setCurrency} short={CURRENCY_SHORT} long={CURRENCY_LONG} />
            <Toggle label="화면 테마" value={theme} onChange={setTheme} short={THEME_SHORT} long={THEME_LONG} />
          </div>
          <div className="flex min-w-0 basis-full items-center gap-2 sm:contents">
            <nav
              aria-label="주요 메뉴"
              className="flex min-w-0 flex-1 flex-wrap gap-1 sm:order-1 sm:flex-none sm:flex-nowrap"
            >
              <NavLink to="/" end className={navClass}>홈</NavLink>
              <NavLink to="/compare" className={navClass}>비교</NavLink>
              <NavLink to="/rules" className={navClass}>규칙</NavLink>
              <NavLink to="/transactions" className={navClass}>거래</NavLink>
              <NavLink to="/import" className={navClass}>
                <NavLabel short="가져오기" long="스크린샷 가져오기" />
              </NavLink>
              <NavLink to="/projection" className={navClass}>
                <NavLabel short="시뮬레이션" long="장기 시뮬레이션" />
              </NavLink>
            </nav>
            <form onSubmit={onSearch} className="min-w-0 shrink sm:order-3 sm:shrink-0">
              <input
                aria-label="종목 검색"
                placeholder="종목 검색"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-28 max-w-full rounded-lg border border-line bg-page px-3 py-1.5 text-sm outline-none focus:border-accent sm:w-44"
              />
            </form>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
      <footer className="mx-auto max-w-6xl px-4 pb-8 text-xs text-muted">
        시세: Yahoo Finance (yfinance). 예측과 시뮬레이션은 참고용이며 투자 조언이 아닙니다.
      </footer>
    </div>
  )
}
