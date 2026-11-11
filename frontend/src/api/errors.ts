/** A failed `/api` call. Its own module so `lib/auth.ts` can read it without importing the client. */
export class ApiError extends Error {
  readonly status: number
  /** Machine-readable reason from the backend (e.g. 'not_trained', 'auth_required'), when it sends one. */
  readonly code?: string
  /** Seconds from the `Retry-After` header (sent with 429), when there was one. */
  readonly retryAfter?: number

  constructor(status: number, message: string, code?: string, retryAfter?: number) {
    super(message)
    this.status = status
    this.code = code
    this.retryAfter = retryAfter
  }
}
