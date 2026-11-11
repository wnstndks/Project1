import { ApiError } from '../api/errors'

/**
 * Login, logout and the read-only demo (DECISIONS.md D-035): every sentence the user sees about
 * them lives here. The server decides who may do what; these only explain its answers.
 */
export const AUTH_TEXT = {
  loginTitle: '로그인',
  loginIntro: '이 서버는 비밀번호로 잠겨 있어요.',
  passwordLabel: '비밀번호',
  submit: '로그인',
  submitting: '확인하는 중…',
  wrongPassword: '비밀번호가 맞지 않아요',
  tooManyAttempts: (minutes: number) => `시도가 너무 많아요. ${minutes}분 뒤에 다시 해 주세요`,
  tooManyAttemptsSoon: '시도가 너무 많아요. 잠시 뒤에 다시 해 주세요',
  loginFailed: '로그인하지 못했어요. 잠시 뒤 다시 시도해 주세요',
  // 204 from the server, yet the next request still has no session: the browser dropped the cookie.
  cookieNotKept: '로그인은 됐지만 브라우저가 로그인 상태를 저장하지 않았어요. 쿠키 설정을 확인해 주세요',
  logout: '로그아웃',
  loggingOut: '로그아웃 중…',
  logoutFailed: '로그아웃하지 못했어요. 다시 시도해 주세요',
  checking: '접속 상태를 확인하는 중…',
  demoBanner: '데모 데이터입니다. 실제 계좌가 아니며 저장·수정은 막혀 있어요.',
  // Same sentence the server sends with 403 `demo_read_only`; shown on buttons the demo disables.
  demoReadOnly: '데모에서는 저장·수정할 수 없어요',
  demoQuizNotSaved: '데모에서는 셀프 체크 결과를 저장하지 않아요',
  // Under the server's own sentence when a visitor opens a ticker outside the demo ledger.
  demoSymbolHome: '홈에서 데모 종목 보기 →',
  tooManyRequests: '요청이 많아요. 잠시 뒤 다시 시도해 주세요',
} as const

export const LOGIN_PATH = '/login'
export const AUTH_REQUIRED_CODE = 'auth_required'
export const DEMO_READ_ONLY_CODE = 'demo_read_only'
export const DEMO_SYMBOL_CODE = 'demo_symbol_not_allowed'

/** The server refused a call because there is no (longer a) session. */
export function isAuthRequired(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401 && error.code === AUTH_REQUIRED_CODE
}

/** The demo answers only for the tickers of its own ledger (403 `demo_symbol_not_allowed`). */
export function isDemoSymbolRefusal(error: unknown): error is ApiError {
  return error instanceof ApiError && error.status === 403 && error.code === DEMO_SYMBOL_CODE
}

/** Whole minutes to wait, rounded up and at least one, from a `Retry-After` in seconds. */
export function retryMinutes(seconds: number): number {
  return Math.max(1, Math.ceil(seconds / 60))
}

/** What the login form says for a failed attempt. */
export function loginErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return AUTH_TEXT.loginFailed
  if (error.status === 401) return AUTH_TEXT.wrongPassword
  if (error.status === 429) {
    return error.retryAfter === undefined
      ? AUTH_TEXT.tooManyAttemptsSoon
      : AUTH_TEXT.tooManyAttempts(retryMinutes(error.retryAfter))
  }
  // Anything else (no login configured here, a request from another site, …): the server's words.
  return error.message || AUTH_TEXT.loginFailed
}

/**
 * Where to go after logging in: the `next` query parameter when it is a path inside this app.
 * Anything else (another site, `//host`, a backslash trick, the login page itself) becomes home,
 * so a crafted login link cannot send the user elsewhere.
 */
export function nextPath(search: string): string {
  const next = new URLSearchParams(search).get('next')
  if (!next || !next.startsWith('/') || next.startsWith('//') || next.includes('\\')) return '/'
  if (next === LOGIN_PATH || next.startsWith(`${LOGIN_PATH}?`) || next.startsWith(`${LOGIN_PATH}/`)) return '/'
  return next
}

/** The login page's address, remembering the page the user was on (home needs no parameter). */
export function loginPath(from: { pathname: string; search?: string }): string {
  const target = `${from.pathname}${from.search ?? ''}`
  return target === '/' || target.startsWith(LOGIN_PATH) ? LOGIN_PATH : `${LOGIN_PATH}?next=${encodeURIComponent(target)}`
}
