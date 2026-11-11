import { afterEach, describe, expect, it, vi } from 'vitest'

import { authRequired, demoReadOnly, fakeApi, json, noContent } from '../testing/fakeApi'
import { api, ApiError, authApi } from './client'

afterEach(() => vi.unstubAllGlobals())

const failure = async (call: Promise<unknown>): Promise<ApiError> => {
  const error = await call.then(
    () => undefined,
    (e: unknown) => e,
  )
  expect(error).toBeInstanceOf(ApiError)
  return error as ApiError
}

describe('auth calls', () => {
  it('asks for the session and sends the cookie to this origin only', async () => {
    const session = { auth_required: true, authenticated: false, demo_mode: false }
    const server = fakeApi({ 'GET /api/auth/session': () => json(200, session) })
    await expect(authApi.session()).resolves.toEqual(session)
    expect(server.calls[0].init?.credentials).toBe('same-origin')
  })

  it('posts the password as JSON and treats 204 as success', async () => {
    const server = fakeApi({ 'POST /api/auth/login': noContent, 'POST /api/auth/logout': noContent })
    await expect(authApi.login('not-a-real-password')).resolves.toBeUndefined()
    expect(server.calls[0].init?.body).toBe(JSON.stringify({ password: 'not-a-real-password' }))
    expect(server.calls[0].init?.credentials).toBe('same-origin')
    await expect(authApi.logout()).resolves.toBeUndefined()
  })
})

describe('refusals the screens explain', () => {
  it('carries the code of a 401 so the session can be marked ended', async () => {
    fakeApi({ 'GET /api/transactions': authRequired })
    const error = await failure(api.transactions())
    expect(error.status).toBe(401)
    expect(error.code).toBe('auth_required')
    expect(error.message).toBe('로그인이 필요합니다')
  })

  it("keeps the server's sentence for a demo write (403)", async () => {
    fakeApi({ 'DELETE /api/transactions/1': demoReadOnly })
    const error = await failure(api.deleteTransaction(1))
    expect(error.status).toBe(403)
    expect(error.code).toBe('demo_read_only')
    expect(error.message).toBe('데모에서는 저장·수정할 수 없어요')
  })

  it("keeps the server's sentence for a symbol outside the demo ledger (403)", async () => {
    const detail = '데모에서는 데모 장부에 있는 종목만 볼 수 있어요'
    fakeApi({ 'GET /api/market/ZZZ/quote': () => json(403, { detail, code: 'demo_symbol_not_allowed' }) })
    const error = await failure(api.quote('ZZZ'))
    expect(error.code).toBe('demo_symbol_not_allowed')
    expect(error.message).toBe(detail)
  })

  it('answers 429 with one plain sentence and the seconds to wait', async () => {
    fakeApi({
      'GET /api/portfolio/summary': () =>
        json(429, { detail: '요청이 너무 많아요. 잠시 뒤에 다시 시도해 주세요', code: 'rate_limited' }, { 'Retry-After': '7' }),
    })
    const error = await failure(api.summary())
    expect(error.message).toBe('요청이 많아요. 잠시 뒤 다시 시도해 주세요')
    expect(error.code).toBe('rate_limited')
    expect(error.retryAfter).toBe(7)
  })

  it('still explains a 429 that a proxy answered without JSON or the header', async () => {
    fakeApi({ 'GET /api/portfolio/summary': () => new Response('<html>slow down</html>', { status: 429 }) })
    const error = await failure(api.summary())
    expect(error.message).toBe('요청이 많아요. 잠시 뒤 다시 시도해 주세요')
    expect(error.code).toBeUndefined()
    expect(error.retryAfter).toBeUndefined()
  })
})
