import { useState, type FormEvent } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { useAuthSession, useLogin } from '../api/hooks'
import { Card, ErrorBox } from '../components/ui'
import { AUTH_TEXT, loginErrorMessage, nextPath } from '../lib/auth'

/**
 * The single-account login (D-035). The password goes to the server once; the session is an
 * HttpOnly cookie this page never reads. On a server without a login (local development, the
 * public demo) there is nothing to do here, so the page leaves for home.
 */
export function Login() {
  const session = useAuthSession()
  const login = useLogin()
  const location = useLocation()
  const [password, setPassword] = useState('')

  if (session.isPending) {
    return (
      <p role="status" className="py-16 text-center text-sm text-muted">
        {AUTH_TEXT.checking}
      </p>
    )
  }
  if (session.data && !session.data.auth_required) return <Navigate to="/" replace />
  if (session.data?.authenticated) return <Navigate to={nextPath(location.search)} replace />

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!password || login.isPending) return
    // A refused password is cleared, so the same one is not sent again by habit.
    login.mutate(password, { onError: () => setPassword('') })
  }
  const message = login.error
    ? loginErrorMessage(login.error)
    : login.isSuccess
      ? AUTH_TEXT.cookieNotKept // accepted, yet the session check above still says logged out
      : null

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-4 py-10">
      <Card>
        <p className="text-[13px] font-semibold text-muted">Asset Manager</p>
        <h1 className="mt-1 text-[20px] font-bold text-ink">{AUTH_TEXT.loginTitle}</h1>
        <p className="mt-1 text-sm text-ink-2">{AUTH_TEXT.loginIntro}</p>
        {session.error ? (
          <div className="mt-4">
            <ErrorBox error={session.error} />
          </div>
        ) : null}
        <form onSubmit={submit} className="mt-5 space-y-3">
          {/* One account, so no name to type; password managers still want a field to file it under. */}
          <input type="text" name="username" autoComplete="username" value="asset-manager" readOnly hidden />
          <label className="block text-sm">
            <span className="text-ink-2">{AUTH_TEXT.passwordLabel}</span>
            <input
              type="password"
              name="password"
              autoComplete="current-password"
              autoFocus
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-invalid={message ? true : undefined}
              aria-describedby={message ? 'login-message' : undefined}
              className="mt-1 w-full rounded-lg border border-line bg-surface px-3 py-2.5 text-[15px] outline-none focus:border-accent"
            />
          </label>
          {message && (
            <p id="login-message" role="alert" className="text-sm text-danger">
              {message}
            </p>
          )}
          <button
            type="submit"
            disabled={login.isPending}
            className="w-full rounded-xl bg-ink py-3 text-[15px] font-semibold text-surface disabled:opacity-50"
          >
            {login.isPending ? AUTH_TEXT.submitting : AUTH_TEXT.submit}
          </button>
        </form>
      </Card>
    </main>
  )
}
