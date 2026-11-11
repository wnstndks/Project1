import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it } from 'vitest'

import type { AuthSession, Transaction } from '../api/client'
import { BulkDelete } from '../components/BulkDelete'
import { AUTH_TEXT } from './auth'
import { SessionProvider, useDemoMode } from './session'

const demo: AuthSession = { auth_required: false, authenticated: false, demo_mode: true }
const mine: AuthSession = { auth_required: true, authenticated: true, demo_mode: false }

function Probe() {
  return <span data-testid="demo">{String(useDemoMode())}</span>
}

const withSession = (session: AuthSession | null, children: ReactNode) =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      {session ? <SessionProvider value={session}>{children}</SessionProvider> : children}
    </QueryClientProvider>,
  )

// Synthetic rows only; the note is the one the backend puts on screenshot imports.
const rows = [
  { id: 1, symbol: 'AAA', note: '스크린샷 가져오기' },
  { id: 2, symbol: 'BBB', note: null },
] as unknown as Transaction[]

afterEach(cleanup)

describe('useDemoMode', () => {
  it('is true only inside the demo session', () => {
    withSession(demo, <Probe />)
    expect(screen.getByTestId('demo')).toHaveTextContent('true')
    cleanup()
    withSession(mine, <Probe />)
    expect(screen.getByTestId('demo')).toHaveTextContent('false')
  })

  it('is false for a page rendered on its own, so nothing is switched off by accident', () => {
    withSession(null, <Probe />)
    expect(screen.getByTestId('demo')).toHaveTextContent('false')
  })
})

describe('a write screen on the demo', () => {
  it('switches its buttons off and says why', () => {
    withSession(demo, <BulkDelete transactions={rows} />)
    for (const name of ['전체 삭제', '가져온 거래만 삭제 (1)']) {
      const button = screen.getByRole('button', { name })
      expect(button).toBeDisabled()
      expect(button).toHaveAttribute('title', AUTH_TEXT.demoReadOnly)
    }
  })

  it('leaves the same buttons alone on my own instance', () => {
    withSession(mine, <BulkDelete transactions={rows} />)
    for (const name of ['전체 삭제', '가져온 거래만 삭제 (1)']) {
      const button = screen.getByRole('button', { name })
      expect(button).toBeEnabled()
      expect(button).not.toHaveAttribute('title')
    }
  })
})
