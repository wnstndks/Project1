/* oxlint-disable react/only-export-components -- context provider and its hook live together */
import { createContext, useContext } from 'react'

import type { AuthSession } from '../api/client'

/**
 * What the server said about this browser's session (`GET /api/auth/session`), handed down by the
 * app shell. A context rather than a query hook so that a page rendered on its own (tests, a
 * failed session request) simply sees "not a demo" and works as before.
 */
const SessionContext = createContext<AuthSession | null>(null)

export const SessionProvider = SessionContext.Provider

/**
 * True on the public read-only demo. Screens use it to switch their save buttons off up front;
 * the server refuses the write either way (403 `demo_read_only`).
 */
export function useDemoMode(): boolean {
  return useContext(SessionContext)?.demo_mode === true
}
