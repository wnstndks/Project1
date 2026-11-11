import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { AuthSession } from './api/client'
import { useTransactions } from './api/hooks'
import { createQueryClient, sessionKey } from './api/queryClient'
import { Layout } from './App'
import { AUTH_TEXT } from './lib/auth'
import { useDemoMode } from './lib/session'
import { Login } from './pages/Login'
import { authRequired, fakeApi, json, noContent, type Route as ApiRoute } from './testing/fakeApi'

const open: AuthSession = { auth_required: false, authenticated: false, demo_mode: false }
const demo: AuthSession = { auth_required: false, authenticated: false, demo_mode: true }
const loggedOut: AuthSession = { auth_required: true, authenticated: false, demo_mode: false }
const loggedIn: AuthSession = { auth_required: true, authenticated: true, demo_mode: false }

function Where() {
  const location = useLocation()
  return <span data-testid="where">{`${location.pathname}${location.search}`}</span>
}

/** Stands in for a page: says whether it sees the demo, and loads something protected. */
function Page() {
  const isDemo = useDemoMode()
  const transactions = useTransactions()
  return (
    <div>
      <span data-testid="page">{isDemo ? 'demo page' : 'page'}</span>
      <span data-testid="rows">{transactions.data ? `${transactions.data.length} rows` : 'no rows'}</span>
    </div>
  )
}

function renderApp(at: string): QueryClient {
  const client = createQueryClient()
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[at]}>
        <Where />
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<Layout />}>
            <Route path="*" element={<Page />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return client
}

const server = (session: () => AuthSession, extra: Record<string, ApiRoute> = {}) =>
  fakeApi({
    'GET /api/auth/session': () => json(200, session()),
    'GET /api/transactions': () => json(200, []),
    ...extra,
  })

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('Layout: who gets in', () => {
  it('draws nothing protected until the server has answered, then the app', async () => {
    const api = server(() => open)
    renderApp('/coach')
    // First paint: only the waiting line, and no page request has gone out.
    expect(screen.getByRole('status')).toHaveTextContent(AUTH_TEXT.checking)
    expect(api.count('GET /api/transactions')).toBe(0)
    expect(await screen.findByTestId('page')).toHaveTextContent(/^page$/)
    expect(screen.getByRole('navigation', { name: '주요 메뉴' })).toBeInTheDocument()
  })

  it('on a server without a login shows no logout button and no demo strip', async () => {
    server(() => open)
    renderApp('/')
    await screen.findByTestId('page')
    expect(screen.queryByRole('button', { name: '로그아웃' })).not.toBeInTheDocument()
    expect(screen.queryByText(AUTH_TEXT.demoBanner)).not.toBeInTheDocument()
  })

  it('sends a visitor without a session to the login page, remembering where they were going', async () => {
    const api = server(() => loggedOut)
    renderApp('/transactions?check=1')
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/login?next=%2Ftransactions%3Fcheck%3D1'))
    expect(await screen.findByLabelText('비밀번호')).toBeInTheDocument()
    // The page behind the gate was never drawn, so nothing protected was requested.
    expect(screen.queryByTestId('page')).not.toBeInTheDocument()
    expect(api.count('GET /api/transactions')).toBe(0)
  })

  it('shows a logout button to a logged-in user, and logging out forgets everything', async () => {
    const state = { session: loggedIn }
    const api = server(() => state.session, {
      'POST /api/auth/logout': () => {
        state.session = loggedOut
        return noContent()
      },
    })
    const client = renderApp('/coach')
    await waitFor(() => expect(screen.getByTestId('rows')).toHaveTextContent('0 rows'))
    fireEvent.click(screen.getByRole('button', { name: '로그아웃' }))

    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent(/^\/login$/))
    expect(await screen.findByLabelText('비밀번호')).toBeInTheDocument()
    expect(api.count('POST /api/auth/logout')).toBe(1)
    // Nothing fetched as the logged-in user is left in memory.
    expect(client.getQueryData(['transactions'])).toBeUndefined()
    expect(client.getQueryData(sessionKey)).toEqual(loggedOut)
  })

  it('says so when logging out failed, and stays logged in', async () => {
    server(() => loggedIn, { 'POST /api/auth/logout': () => json(502, { detail: 'Bad Gateway' }) })
    renderApp('/coach')
    fireEvent.click(await screen.findByRole('button', { name: '로그아웃' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(AUTH_TEXT.logoutFailed)
    expect(screen.getByTestId('where')).toHaveTextContent('/coach')
  })
})

describe('Layout: the session ends while the app is open', () => {
  it('goes to the login page once, on the first 401, without asking the same thing again', async () => {
    // The browser still believes it is logged in; the server no longer does.
    const api = server(() => loggedIn, { 'GET /api/transactions': authRequired })
    renderApp('/transactions')

    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/login?next=%2Ftransactions'))
    expect(await screen.findByLabelText('비밀번호')).toBeInTheDocument()
    expect(screen.queryByTestId('page')).not.toBeInTheDocument()

    // No loop: the refused request went out once, and the login page asked for nothing protected.
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(api.count('GET /api/transactions')).toBe(1)
    expect(api.count('GET /api/auth/session')).toBe(1)
    expect(screen.getByTestId('where')).toHaveTextContent('/login?next=%2Ftransactions')
  })
})

describe('Layout: the public demo', () => {
  it('shows the demo strip on every page and tells pages they are read-only', async () => {
    server(() => demo)
    renderApp('/rules')
    expect(await screen.findByTestId('page')).toHaveTextContent('demo page')
    const strip = screen.getByText('데모 데이터입니다. 실제 계좌가 아니며 저장·수정은 막혀 있어요.')
    expect(strip).toHaveAttribute('role', 'status')
    // A notice about the data: neutral ink, never the gain/loss colours or arrows.
    expect(strip.className).not.toMatch(/gain|loss|danger/)
    expect(strip.textContent).not.toMatch(/[▲▼]/)
    // The demo has no login, so there is nothing to log out of.
    expect(screen.queryByRole('button', { name: '로그아웃' })).not.toBeInTheDocument()
  })

  it('still draws the app when the session request itself fails (the server decides every request anyway)', async () => {
    fakeApi({
      'GET /api/auth/session': () => json(502, { detail: 'Bad Gateway' }),
      'GET /api/transactions': () => json(200, []),
    })
    renderApp('/')
    expect(await screen.findByTestId('page')).toHaveTextContent(/^page$/)
    expect(screen.queryByText(AUTH_TEXT.demoBanner)).not.toBeInTheDocument()
  })
})
