import { MutationObserver } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'

import type { AuthSession } from './client'
import { ApiError } from './errors'
import { createQueryClient, pollDelay, sessionKey } from './queryClient'

const loggedIn: AuthSession = { auth_required: true, authenticated: true, demo_mode: false }
const sessionEnded = () => Promise.reject(new ApiError(401, '로그인이 필요합니다', 'auth_required'))

describe('createQueryClient: the session ended', () => {
  it('marks the cached session logged out when a query is answered 401 auth_required', async () => {
    const client = createQueryClient()
    client.setQueryData(sessionKey, loggedIn)
    let calls = 0
    await client
      .fetchQuery({
        queryKey: ['transactions'],
        queryFn: () => {
          calls += 1
          return sessionEnded()
        },
      })
      .catch(() => {})
    expect(client.getQueryData(sessionKey)).toEqual({ auth_required: true, authenticated: false, demo_mode: false })
    expect(calls).toBe(1)
  })

  it('does the same for a mutation, and works before the session was ever fetched', async () => {
    const client = createQueryClient()
    await new MutationObserver(client, { mutationFn: sessionEnded }).mutate().catch(() => {})
    expect(client.getQueryData(sessionKey)).toEqual({ auth_required: true, authenticated: false, demo_mode: false })
  })

  it('leaves the session alone for every other failure', async () => {
    const client = createQueryClient()
    client.setQueryData(sessionKey, loggedIn)
    const failures = [
      new ApiError(403, '데모에서는 저장·수정할 수 없어요', 'demo_read_only'),
      new ApiError(401, '비밀번호가 올바르지 않습니다', 'invalid_credentials'),
      new ApiError(429, '요청이 많아요. 잠시 뒤 다시 시도해 주세요', 'rate_limited'),
      new ApiError(404, 'Not Found'),
    ]
    for (const [i, error] of failures.entries()) {
      await client.fetchQuery({ queryKey: ['x', i], queryFn: () => Promise.reject(error) }).catch(() => {})
    }
    expect(client.getQueryData(sessionKey)).toEqual(loggedIn)
  })
})

describe('pollDelay: polling a route that is still syncing', () => {
  it('keeps the usual pace while syncing and stops when the sync is over', () => {
    expect(pollDelay(true, null, 5000)).toBe(5000)
    expect(pollDelay(false, null, 5000)).toBe(false)
    expect(pollDelay(undefined, null, 5000)).toBe(false)
    // Another kind of failure does not change the pace.
    expect(pollDelay(true, new ApiError(502, 'x'), 5000)).toBe(5000)
  })

  it('after a 429 waits at least as long as Retry-After says', () => {
    expect(pollDelay(true, new ApiError(429, 'x', 'rate_limited', 40), 5000)).toBe(40_000)
    // Never faster than the usual pace, and a minute when the server gave no number.
    expect(pollDelay(true, new ApiError(429, 'x', 'rate_limited', 1), 5000)).toBe(5000)
    expect(pollDelay(true, new ApiError(429, 'x'), 15_000)).toBe(60_000)
    expect(pollDelay(false, new ApiError(429, 'x', 'rate_limited', 40), 5000)).toBe(false)
  })
})

describe('createQueryClient: retries', () => {
  const retry = createQueryClient().getDefaultOptions().queries?.retry as (failures: number, error: Error) => boolean

  it("never asks again after the server's own refusal (4xx)", () => {
    for (const status of [400, 401, 403, 404, 409, 422, 429]) {
      expect(retry(0, new ApiError(status, 'x')), String(status)).toBe(false)
    }
  })

  it('retries a network failure or a 5xx up to three times', () => {
    for (const error of [new TypeError('Failed to fetch'), new ApiError(502, 'x')]) {
      expect(retry(0, error)).toBe(true)
      expect(retry(2, error)).toBe(true)
      expect(retry(3, error)).toBe(false)
    }
  })
})
