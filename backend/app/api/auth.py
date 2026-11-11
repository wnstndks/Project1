"""Single-account login (DECISIONS.md D-035). Always reachable without a session.

The session is an HttpOnly, SameSite=Strict cookie signed by the server; the frontend never
sees the token and only asks `/session` what to show. Nothing here logs the password, the
hash or the token.
"""

import logging

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse

from app.schemas.auth import LoginIn, SessionOut
from app.security.middleware import RATE_LIMITED_CODE, SecurityState, rejection
from app.security.passwords import verify_password
from app.security.ratelimit import retry_after_header

log = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

GLOBAL_KEY = "*all*"
NOT_CONFIGURED_CODE = "login_not_configured"
NOT_CONFIGURED_DETAIL = "이 서버에는 로그인이 설정되어 있지 않습니다"
DEMO_NO_LOGIN_DETAIL = "데모에서는 로그인 없이 둘러볼 수 있어요"
INVALID_CODE = "invalid_credentials"
INVALID_DETAIL = "비밀번호가 올바르지 않습니다"
LOCKED_DETAIL = "로그인 시도가 너무 많아요. 잠시 뒤에 다시 시도해 주세요"

_ERRORS = {
    401: {"description": "Wrong password (`code: invalid_credentials`)"},
    409: {"description": "No login configured on this server (`code: login_not_configured`)"},
    429: {"description": "Too many attempts; see `Retry-After` (`code: rate_limited`)"},
}


def _state(request: Request) -> SecurityState:
    return request.app.state.security


@router.get("/session", response_model=SessionOut)
async def session(request: Request, response: Response) -> SessionOut:
    state = _state(request)
    response.headers["Cache-Control"] = "no-store"
    authenticated = (
        state.sessions is not None and state.sessions.current(request.cookies) is not None
    )
    return SessionOut(
        auth_required=state.auth_enabled,
        authenticated=authenticated,
        demo_mode=state.settings.demo_mode,
    )


def _locked(wait: float) -> JSONResponse:
    return rejection(
        429, LOCKED_DETAIL, RATE_LIMITED_CODE, {"Retry-After": retry_after_header(wait)}
    )


# A plain `def`: scrypt takes a few hundred milliseconds, so it runs off the event loop.
@router.post("/login", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
def login(body: LoginIn, request: Request) -> Response:
    state = _state(request)
    if state.sessions is None or state.password is None:
        detail = DEMO_NO_LOGIN_DETAIL if state.settings.demo_mode else NOT_CONFIGURED_DETAIL
        return rejection(409, detail, NOT_CONFIGURED_CODE)

    # Each try is counted before the password is checked, so parallel guesses cannot outrun
    # the limit, and a locked-out address is refused even with the right password.
    key = state.client_key(request.scope)
    wait = state.login_attempts.acquire(key)
    if wait > 0:
        log.warning("login refused: too many attempts from %s", key)
        return _locked(wait)
    wait = state.all_login_attempts.acquire(GLOBAL_KEY)
    if wait > 0:
        state.login_attempts.forgive(key)
        log.warning("login refused: too many failed attempts across all addresses")
        return _locked(wait)

    with state.verify_lock:
        ok = verify_password(body.password, state.password)
    if not ok:
        log.warning("login failed from %s", key)
        return rejection(401, INVALID_DETAIL, INVALID_CODE)

    state.login_attempts.reset(key)
    state.all_login_attempts.forgive(GLOBAL_KEY)
    response = Response(
        status_code=status.HTTP_204_NO_CONTENT, headers={"Cache-Control": "no-store"}
    )
    state.sessions.start(response)
    log.info("login succeeded from %s", key)
    return response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request) -> Response:
    state = _state(request)
    response = Response(
        status_code=status.HTTP_204_NO_CONTENT, headers={"Cache-Control": "no-store"}
    )
    if state.sessions is not None:
        state.sessions.end(response, request.cookies)
    return response
