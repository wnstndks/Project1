import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query'

import { isAuthRequired } from '../lib/auth'
import type { AuthSession } from './client'
import { ApiError } from './errors'

export const sessionKey = ['auth', 'session'] as const

/**
 * How long to wait before asking a still-syncing route again: the usual pace, but after a 429
 * at least as long as the server asked for in `Retry-After` (a minute when it did not say).
 * `false` stops the polling once the sync is over.
 */
export function pollDelay(syncing: boolean | undefined, error: unknown, usualMs: number): number | false {
  if (!syncing) return false
  if (error instanceof ApiError && error.status === 429) return Math.max(usualMs, (error.retryAfter ?? 60) * 1000)
  return usualMs
}

/**
 * The app's query client. Two things beyond the defaults:
 *
 * - "The session ended" is handled once, here: when any query or mutation is answered 401
 *   `auth_required`, the cached session is marked logged out. The layout reads that and sends the
 *   user to the login page. Nothing here navigates, and the login page calls no protected route,
 *   so a 401 can never bounce the browser back and forth.
 * - A 4xx answer is the server's decision (not found, not allowed, too many requests), so it is
 *   shown at once instead of being asked three more times; only network and 5xx failures retry.
 */
export function createQueryClient(): QueryClient {
  const onError = (error: unknown) => {
    if (!isAuthRequired(error)) return
    client.setQueryData<AuthSession>(sessionKey, (session) => ({
      demo_mode: session?.demo_mode ?? false,
      auth_required: true,
      authenticated: false,
    }))
  }
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({ onError }),
    mutationCache: new MutationCache({ onError }),
    defaultOptions: {
      queries: {
        // Backend caches quotes for 60s; refetching more often gains nothing.
        staleTime: 60_000,
        refetchOnWindowFocus: false,
        retry: (failures, error) =>
          !(error instanceof ApiError && error.status >= 400 && error.status < 500) && failures < 3,
      },
    },
  })
  return client
}
