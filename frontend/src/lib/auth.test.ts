import { describe, expect, it } from 'vitest'

import { ApiError } from '../api/errors'
import { AUTH_TEXT, isAuthRequired, loginErrorMessage, loginPath, nextPath, retryMinutes } from './auth'

describe('login error wording', () => {
  it('says the password is wrong for 401, whatever the server wrote', () => {
    expect(loginErrorMessage(new ApiError(401, '비밀번호가 올바르지 않습니다', 'invalid_credentials'))).toBe(
      '비밀번호가 맞지 않아요',
    )
  })

  it('turns Retry-After seconds into whole minutes, rounded up and never zero', () => {
    expect(retryMinutes(840)).toBe(14)
    expect(retryMinutes(841)).toBe(15)
    expect(retryMinutes(1)).toBe(1)
    expect(retryMinutes(0)).toBe(1)
    expect(loginErrorMessage(new ApiError(429, 'x', 'rate_limited', 840))).toBe(
      '시도가 너무 많아요. 14분 뒤에 다시 해 주세요',
    )
    // A proxy may answer 429 without the header.
    expect(loginErrorMessage(new ApiError(429, 'x'))).toBe('시도가 너무 많아요. 잠시 뒤에 다시 해 주세요')
  })

  it("passes the server's own sentence through for anything else, and has a fallback", () => {
    const notConfigured = new ApiError(409, '이 서버에는 로그인이 설정되어 있지 않습니다', 'login_not_configured')
    expect(loginErrorMessage(notConfigured)).toBe('이 서버에는 로그인이 설정되어 있지 않습니다')
    expect(loginErrorMessage(new TypeError('Failed to fetch'))).toBe(AUTH_TEXT.loginFailed)
    expect(loginErrorMessage(new ApiError(500, ''))).toBe(AUTH_TEXT.loginFailed)
  })
})

describe('isAuthRequired', () => {
  it('is true only for 401 with the auth_required code', () => {
    expect(isAuthRequired(new ApiError(401, '로그인이 필요합니다', 'auth_required'))).toBe(true)
    // A wrong password is also 401, but it is not "the session ended".
    expect(isAuthRequired(new ApiError(401, 'x', 'invalid_credentials'))).toBe(false)
    expect(isAuthRequired(new ApiError(403, 'x', 'demo_read_only'))).toBe(false)
    expect(isAuthRequired(new Error('auth_required'))).toBe(false)
    expect(isAuthRequired(undefined)).toBe(false)
  })
})

describe('where to go after logging in', () => {
  it('keeps a path inside the app, query string included', () => {
    expect(nextPath('?next=%2Fcoach')).toBe('/coach')
    expect(nextPath('?next=%2Ftransactions%3Fcheck%3D1')).toBe('/transactions?check=1')
    expect(nextPath('?next=%2Fassets%2FAAA')).toBe('/assets/AAA')
  })

  it('falls back to home for anything that could leave the app or loop', () => {
    for (const search of [
      '',
      '?next=',
      '?next=https%3A%2F%2Fevil.example',
      '?next=%2F%2Fevil.example',
      '?next=%2F%5Cevil.example',
      '?next=coach',
      '?next=javascript%3Aalert(1)',
      '?next=%2Flogin',
      '?next=%2Flogin%3Fnext%3D%252Fcoach',
    ]) {
      expect(nextPath(search), search).toBe('/')
    }
  })

  it('builds the login address from the page the user was on', () => {
    expect(loginPath({ pathname: '/' })).toBe('/login')
    expect(loginPath({ pathname: '/coach', search: '' })).toBe('/login?next=%2Fcoach')
    expect(loginPath({ pathname: '/transactions', search: '?check=1' })).toBe('/login?next=%2Ftransactions%3Fcheck%3D1')
    expect(loginPath({ pathname: '/login', search: '?next=%2Fcoach' })).toBe('/login')
    // Round trip.
    expect(nextPath(loginPath({ pathname: '/assets/AAA', search: '' }).slice('/login'.length))).toBe('/assets/AAA')
  })
})

describe('wording rules', () => {
  const sentences = Object.values(AUTH_TEXT).map((v) => (typeof v === 'function' ? v(3) : v))

  it('says the demo is not a real account and that saving is off', () => {
    expect(AUTH_TEXT.demoBanner).toBe('데모 데이터입니다. 실제 계좌가 아니며 저장·수정은 막혀 있어요.')
    expect(AUTH_TEXT.demoReadOnly).toBe('데모에서는 저장·수정할 수 없어요')
    expect(AUTH_TEXT.tooManyRequests).toBe('요청이 많아요. 잠시 뒤 다시 시도해 주세요')
  })

  it('never uses the banned words or a gain/loss cue', () => {
    for (const s of sentences) {
      expect(s).not.toMatch(/추천|사세요|파세요|오를|예상 수익/)
      expect(s).not.toMatch(/[▲▼]/)
    }
  })
})
