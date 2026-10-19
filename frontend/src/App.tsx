import { useState, type FormEvent } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'

const navClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-md px-3 py-1.5 text-sm ${isActive ? 'bg-hover font-semibold text-ink' : 'text-ink-2 hover:text-ink'}`

export function Layout() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')

  const onSearch = (e: FormEvent) => {
    e.preventDefault()
    const symbol = search.trim().toUpperCase()
    if (symbol) navigate(`/assets/${encodeURIComponent(symbol)}`)
    setSearch('')
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <span className="font-semibold">Asset Manager</span>
          <nav className="flex gap-1">
            <NavLink to="/" end className={navClass}>대시보드</NavLink>
            <NavLink to="/transactions" className={navClass}>거래 내역</NavLink>
          </nav>
          <form onSubmit={onSearch} className="ml-auto">
            <input
              aria-label="종목 검색"
              placeholder="종목 검색 (AAPL, BTC)"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-48 rounded-lg border border-line bg-page px-3 py-1.5 text-sm outline-none focus:border-accent"
            />
          </form>
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
