import { QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { AuthSession } from '../api/client'
import { createQueryClient } from '../api/queryClient'
import { fakeApi, json, noContent, type Route as ApiRoute } from '../testing/fakeApi'
import { Login } from './Login'

// A value that only exists in this test. The real password is never typed by tests or agents.
const PASSWORD = 'test-only-not-a-real-password'

const locked: AuthSession = { auth_required: true, authenticated: false, demo_mode: false }
const open: AuthSession = { auth_required: false, authenticated: false, demo_mode: false }
const demo: AuthSession = { auth_required: false, authenticated: false, demo_mode: true }

function Where() {
  const location = useLocation()
  return <span data-testid="where">{`${location.pathname}${location.search}`}</span>
}

function renderLogin(at = '/login') {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[at]}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** A server with a login: the session flips once the right password has been posted. */
function lockedServer(login: ApiRoute) {
  const state = { session: locked }
  const server = fakeApi({
    'GET /api/auth/session': () => json(200, state.session),
    'POST /api/auth/login': async (init) => {
      const res = await login(init)
      if (res.status === 204) state.session = { ...locked, authenticated: true }
      return res
    },
  })
  return { ...server, state }
}

const passwordField = () => screen.findByLabelText('비밀번호')
const submit = async (value: string) => {
  const field = await passwordField()
  fireEvent.change(field, { target: { value } })
  fireEvent.submit(field.closest('form')!)
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('Login page', () => {
  it('asks for one password, in a field browsers and password managers recognise', async () => {
    lockedServer(noContent)
    renderLogin()
    const field = await passwordField()
    expect(field).toHaveAttribute('type', 'password')
    expect(field).toHaveAttribute('autocomplete', 'current-password')
    expect(field).toBeRequired()
    expect(screen.getByRole('heading', { name: '로그인' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '로그인' })).toBeEnabled()
    // One visible input only: there is no account name to type.
    expect(screen.getAllByLabelText(/./)).toHaveLength(1)
  })

  it('logs in and goes to the page the user came for', async () => {
    const server = lockedServer(noContent)
    renderLogin('/login?next=%2Fcoach')
    await submit(PASSWORD)
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/coach'))
    const login = server.calls.find((c) => c.key === 'POST /api/auth/login')
    expect(login?.init?.body).toBe(JSON.stringify({ password: PASSWORD }))
    // The session was asked again after the login, so "logged in" is the server's word.
    expect(server.count('GET /api/auth/session')).toBe(2)
  })

  it('goes home when there is no next page, or when next points outside the app', async () => {
    lockedServer(noContent)
    renderLogin('/login?next=%2F%2Fevil.example')
    await submit(PASSWORD)
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent(/^\/$/))
  })

  it('says the password is wrong on 401, clears the field and stays on the page', async () => {
    const server = lockedServer(() => json(401, { detail: '비밀번호가 올바르지 않습니다', code: 'invalid_credentials' }))
    renderLogin()
    await submit('wrong-guess')
    expect(await screen.findByRole('alert')).toHaveTextContent('비밀번호가 맞지 않아요')
    expect(await passwordField()).toHaveValue('')
    expect(screen.queryByTestId('where')).not.toBeInTheDocument()
    // A wrong password is not "the session ended": nothing re-asks or redirects.
    expect(server.count('GET /api/auth/session')).toBe(1)
    expect(server.count('POST /api/auth/login')).toBe(1)
  })

  it('says how many minutes to wait on 429, from Retry-After', async () => {
    lockedServer(() =>
      json(429, { detail: '로그인 시도가 너무 많아요. 잠시 뒤에 다시 시도해 주세요', code: 'rate_limited' }, { 'Retry-After': '840' }),
    )
    renderLogin()
    await submit(PASSWORD)
    expect(await screen.findByRole('alert')).toHaveTextContent('시도가 너무 많아요. 14분 뒤에 다시 해 주세요')
  })

  it('explains a login the browser did not keep (204, yet still no session)', async () => {
    fakeApi({ 'GET /api/auth/session': () => json(200, locked), 'POST /api/auth/login': noContent })
    renderLogin()
    await submit(PASSWORD)
    expect(await screen.findByRole('alert')).toHaveTextContent('브라우저가 로그인 상태를 저장하지 않았어요')
    expect(screen.queryByTestId('where')).not.toBeInTheDocument()
  })

  it.each([
    ['a server without a login', open],
    ['the public demo', demo],
  ])('leaves for home on %s, without showing a form', async (_, session) => {
    const server = fakeApi({ 'GET /api/auth/session': () => json(200, session) })
    renderLogin('/login?next=%2Fcoach')
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent(/^\/$/))
    expect(screen.queryByLabelText('비밀번호')).not.toBeInTheDocument()
    expect(server.count('POST /api/auth/login')).toBe(0)
  })

  it('skips the form for a browser that is already logged in', async () => {
    fakeApi({ 'GET /api/auth/session': () => json(200, { ...locked, authenticated: true }) })
    renderLogin('/login?next=%2Frules')
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/rules'))
  })

  it('shows why the session could not be checked, and still offers the form', async () => {
    fakeApi({ 'GET /api/auth/session': () => json(502, { detail: '서버에 연결하지 못했습니다' }) })
    renderLogin()
    expect(await screen.findByText('서버에 연결하지 못했습니다')).toBeInTheDocument()
    expect(await passwordField()).toBeInTheDocument()
  })
})
