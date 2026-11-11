"""The security middleware stack (DECISIONS.md D-035), as plain ASGI classes.

Order, outermost first (`build_stack`): trusted host, security headers, CORS, request limit,
body limit, demo read-only, session + CSRF, then the router. A layer is only installed when
its setting is on, so the development default (no login, no demo) keeps the old stack of
trusted host + CORS. Rejections are produced inside the security headers layer, so 401, 403
and 429 answers carry the same headers as everything else.
"""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.datastructures import Headers, MutableHeaders
from starlette.middleware import Middleware
from starlette.middleware.body_limit import RequestBodyLimitMiddleware
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from starlette.websockets import WebSocketClose

from app.config import Settings
from app.security.demo import (
    DEMO_WRITE_ALLOWLIST,
    READ_ONLY_CODE,
    READ_ONLY_DETAIL,
    SAFE_METHODS,
)
from app.security.passwords import ScryptHash, parse_hash
from app.security.paths import is_api, route_path
from app.security.ratelimit import (
    AttemptLimiter,
    TokenBucketLimiter,
    client_ip,
    rate_key,
    retry_after_header,
)
from app.security.sessions import RevokedSessions, Sessions, SessionSigner

# Reachable without a session when a login is configured.
PUBLIC_PATHS = frozenset({"/api/health"})
PUBLIC_PREFIX = "/api/auth/"
# Not counted by the request limit (container health checks).
UNLIMITED_PATHS = frozenset({"/api/health"})

AUTH_REQUIRED_DETAIL = "로그인이 필요합니다"
AUTH_REQUIRED_CODE = "auth_required"
CSRF_DETAIL = "다른 사이트에서 보낸 요청은 받지 않습니다"
CSRF_CODE = "csrf_origin_mismatch"
RATE_LIMITED_DETAIL = "요청이 너무 많아요. 잠시 뒤에 다시 시도해 주세요"
RATE_LIMITED_CODE = "rate_limited"

# JSON bodies on routes anyone can reach (login, and every write the demo lets through).
PUBLIC_BODY_LIMIT_BYTES = 64 * 1024
# One login failure budget across all addresses, as a multiple of the per-address one, so a
# guesser with many addresses is still bounded (the owner is locked out meanwhile: closed).
GLOBAL_LOGIN_ATTEMPTS_FACTOR = 20
WS_POLICY_VIOLATION = 1008

HSTS = "max-age=31536000; includeSubDomains"
PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=()"


def is_public(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIX)


def rejection(
    status: int, detail: str, code: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"detail": detail, "code": code},
        headers={"Cache-Control": "no-store", **(headers or {})},
    )


@dataclass
class SecurityState:
    """Per-application security objects (`app.state.security`), built once from settings."""

    settings: Settings
    sessions: Sessions | None  # None: no login configured
    password: ScryptHash | None
    login_attempts: AttemptLimiter
    all_login_attempts: AttemptLimiter
    # One scrypt at a time: parallel logins cannot multiply its memory.
    verify_lock: threading.Lock = field(default_factory=threading.Lock)

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> "SecurityState":
        sessions = password = None
        if settings.auth_password_hash is not None and settings.session_secret is not None:
            encoded = settings.auth_password_hash.get_secret_value()
            password = parse_hash(encoded)
            signer = SessionSigner(
                settings.session_secret.get_secret_value(),
                encoded,
                settings.session_ttl_hours * 3600,
                clock,
            )
            sessions = Sessions(
                signer, secure=settings.env == "production", revoked=RevokedSessions(clock)
            )
        window = settings.login_window_minutes * 60
        return cls(
            settings=settings,
            sessions=sessions,
            password=password,
            login_attempts=AttemptLimiter(settings.login_max_attempts, window, clock=monotonic),
            all_login_attempts=AttemptLimiter(
                settings.login_max_attempts * GLOBAL_LOGIN_ATTEMPTS_FACTOR, window, clock=monotonic
            ),
        )

    @property
    def auth_enabled(self) -> bool:
        return self.sessions is not None

    def client_key(self, scope: Scope) -> str:
        return rate_key(client_ip(scope, self.settings.client_ip_header))


class SecurityHeadersMiddleware:
    """Production only. Also answers an unhandled error itself, so even a 500 leaves with
    the headers (the exception still propagates to the server log)."""

    def __init__(self, app: ASGIApp, *, content_security_policy: str) -> None:
        self.app = app
        self.headers = {
            "Strict-Transport-Security": HSTS,
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "same-origin",
            "X-Frame-Options": "DENY",
            "Cross-Origin-Opener-Policy": "same-origin",
            "Permissions-Policy": PERMISSIONS_POLICY,
            "Content-Security-Policy": content_security_policy,
        }

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        api = is_api(route_path(scope))
        started = False

        async def send_with_headers(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                message.setdefault("headers", [])
                headers = MutableHeaders(scope=message)
                for name, value in self.headers.items():
                    headers[name] = value
                # Ledger data must not sit in a shared or browser cache.
                if api and "cache-control" not in headers:
                    headers["Cache-Control"] = "no-store"
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        except Exception:
            if not started:
                response = JSONResponse({"detail": "Internal Server Error"}, status_code=500)
                await response(scope, receive, send_with_headers)
            raise


class RateLimitMiddleware:
    """Per-address request limit on /api (static files and the health check are free)."""

    def __init__(self, app: ASGIApp, *, state: SecurityState, limiter: TokenBucketLimiter) -> None:
        self.app = app
        self.state = state
        self.limiter = limiter

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = route_path(scope)
            if is_api(path) and path not in UNLIMITED_PATHS:
                wait = self.limiter.check(self.state.client_key(scope))
                if wait > 0:
                    response = rejection(
                        429,
                        RATE_LIMITED_DETAIL,
                        RATE_LIMITED_CODE,
                        {"Retry-After": retry_after_header(wait)},
                    )
                    await response(scope, receive, send)
                    return
        await self.app(scope, receive, send)


class PublicBodyLimitMiddleware:
    """Caps the request body where no session is needed to send one: /api/auth/* always,
    and all of /api in demo mode (nothing there uploads). Without it an anonymous client
    could make the server buffer an arbitrarily large JSON body."""

    def __init__(self, app: ASGIApp, *, demo_mode: bool) -> None:
        self.app = app
        self.demo_mode = demo_mode
        self.limited = RequestBodyLimitMiddleware(app, max_body_size=PUBLIC_BODY_LIMIT_BYTES)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = route_path(scope)
            if path.startswith(PUBLIC_PREFIX) or (self.demo_mode and is_api(path)):
                await self.limited(scope, receive, send)
                return
        await self.app(scope, receive, send)


class DemoReadOnlyMiddleware:
    """Demo mode: only reads and the listed compute-only routes pass (closed by default)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket") and is_api(route_path(scope)):
            if scope["type"] == "websocket":
                await WebSocketClose(WS_POLICY_VIOLATION)(scope, receive, send)
                return
            method = scope["method"]
            allowed = (method, route_path(scope)) in DEMO_WRITE_ALLOWLIST
            if method not in SAFE_METHODS and not allowed:
                await rejection(403, READ_ONLY_DETAIL, READ_ONLY_CODE)(scope, receive, send)
                return
        await self.app(scope, receive, send)


class AuthMiddleware:
    """With a login configured: /api needs a valid session cookie (except the health check
    and /api/auth/*), and a write whose Origin is another site is refused."""

    def __init__(self, app: ASGIApp, *, sessions: Sessions, trusted_origins: list[str]) -> None:
        self.app = app
        self.sessions = sessions
        self.trusted_origins = frozenset(o.rstrip("/").lower() for o in trusted_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        path = route_path(scope)
        if not is_api(path):
            await self.app(scope, receive, send)  # static files: the login page itself
            return

        connection = HTTPConnection(scope)
        if not is_public(path) and self.sessions.current(connection.cookies) is None:
            if scope["type"] == "websocket":
                await WebSocketClose(WS_POLICY_VIOLATION)(scope, receive, send)
                return
            response = rejection(401, AUTH_REQUIRED_DETAIL, AUTH_REQUIRED_CODE)
            await response(scope, receive, send)
            return
        write = scope["type"] == "http" and scope["method"] not in SAFE_METHODS
        if write and not self._same_site(connection.headers):
            await rejection(403, CSRF_DETAIL, CSRF_CODE)(scope, receive, send)
            return
        await self.app(scope, receive, send)

    def _same_site(self, headers: Headers) -> bool:
        """Browsers attach Origin to every cross-origin write. No Origin at all means a
        non-browser client (or an old browser, which SameSite=Strict already covers)."""
        origin = headers.get("origin")
        if origin is None:
            return headers.get("sec-fetch-site", "").lower() != "cross-site"
        origin = origin.strip().lower()
        if origin in self.trusted_origins:
            return True
        parsed = urlsplit(origin)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return False  # "null" and other opaque origins
        # Host only: behind the tunnel the app sees http while the browser's origin is https.
        return parsed.netloc == headers.get("host", "").strip().lower()


def build_stack(settings: Settings, state: SecurityState) -> list[Middleware]:
    """The middleware to install, outermost first."""
    production = settings.env == "production"
    stack = [Middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)]
    if production:
        stack.append(
            Middleware(
                SecurityHeadersMiddleware, content_security_policy=settings.content_security_policy
            )
        )
    # Outside the checks below so their 401/403/429 answers stay readable cross-origin, and
    # so a preflight (which carries no cookie) is answered before the session check.
    stack.append(
        Middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    )
    if settings.rate_limit_per_minute > 0:
        limiter = TokenBucketLimiter(settings.rate_limit_per_minute)
        stack.append(Middleware(RateLimitMiddleware, state=state, limiter=limiter))
    if settings.demo_mode or state.sessions is not None:
        stack.append(Middleware(PublicBodyLimitMiddleware, demo_mode=settings.demo_mode))
    if settings.demo_mode:
        stack.append(Middleware(DemoReadOnlyMiddleware))
    if state.sessions is not None:
        stack.append(
            Middleware(
                AuthMiddleware, sessions=state.sessions, trusted_origins=settings.cors_origins
            )
        )
    return stack
