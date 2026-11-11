import { vi } from 'vitest'

/** Test helper only (never imported by app code): a table of answers in place of `fetch`. */
export type Route = (init: RequestInit | undefined) => Response | Promise<Response>

export const json = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } })

export const noContent = () => new Response(null, { status: 204 })

/** What the backend answers without a session (app/security/middleware.py). */
export const authRequired = () => json(401, { detail: '로그인이 필요합니다', code: 'auth_required' })

/** What the demo answers to a write (app/security/demo.py). */
export const demoReadOnly = () => json(403, { detail: '데모에서는 저장·수정할 수 없어요', code: 'demo_read_only' })

/**
 * Replaces `fetch` with handlers keyed by `"METHOD /api/path"`. A request nobody listed fails
 * loudly, so a test also proves which calls were NOT made. Undo with `vi.unstubAllGlobals()`.
 */
export function fakeApi(routes: Record<string, Route>) {
  const calls: { key: string; init?: RequestInit }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const key = `${init?.method ?? 'GET'} ${String(input)}`
      calls.push({ key, init })
      const route = routes[key]
      if (!route) throw new Error(`unexpected request: ${key}`)
      return route(init)
    }),
  )
  return {
    calls,
    count: (key: string) => calls.filter((c) => c.key === key).length,
  }
}
