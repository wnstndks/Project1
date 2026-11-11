"""Signed session cookies for the single-account login (DECISIONS.md D-035).

A token is `v1.<expires>.<nonce>.<mac>` with an HMAC-SHA256 over the first three parts. There
is no server-side session table, so a restart keeps a logged-in browser logged in. The MAC key
is derived from AM_SESSION_SECRET and the password hash: changing either one ends every
session. Logging out also remembers the token's nonce in memory until it would have expired,
so a copied cookie stops working (until the next restart; the cookie itself is deleted).
"""

import base64
import hashlib
import hmac
import secrets
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from starlette.responses import Response

VERSION = "v1"
COOKIE_NAME = "am_session"
# Browsers accept a `__Host-` cookie only with Secure, Path=/ and no Domain, so a sibling
# subdomain (shared tunnel domains) cannot plant one.
SECURE_COOKIE_NAME = "__Host-am_session"
MAX_TOKEN_CHARS = 256
_KEY_CONTEXT = b"asset-manager.session.v1\x00"


@dataclass(frozen=True)
class SessionInfo:
    nonce: str
    expires_at: int


def _mac(key: bytes, payload: str) -> str:
    digest = hmac.new(key, payload.encode("ascii"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class SessionSigner:
    def __init__(
        self,
        secret: str,
        password_hash: str,
        ttl_seconds: int,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._key = hmac.new(
            secret.encode("utf-8"), _KEY_CONTEXT + password_hash.encode("utf-8"), hashlib.sha256
        ).digest()
        self.ttl_seconds = ttl_seconds
        self._clock = clock

    def issue(self) -> str:
        expires_at = int(self._clock()) + self.ttl_seconds
        payload = f"{VERSION}.{expires_at}.{secrets.token_urlsafe(16)}"
        return f"{payload}.{_mac(self._key, payload)}"

    def verify(self, token: str | None) -> SessionInfo | None:
        """The session a token stands for, or None when it is forged, malformed or expired."""
        if not token or len(token) > MAX_TOKEN_CHARS or not token.isascii():
            return None
        payload, _, mac = token.rpartition(".")
        # The MAC is checked first, in constant time, before any field is interpreted.
        if not payload or not hmac.compare_digest(_mac(self._key, payload), mac):
            return None
        parts = payload.split(".")
        if len(parts) != 3 or parts[0] != VERSION or not parts[1].isdigit():
            return None
        expires_at = int(parts[1])
        if self._clock() >= expires_at:
            return None
        return SessionInfo(nonce=parts[2], expires_at=expires_at)


class RevokedSessions:
    """Nonces of logged-out tokens, kept only until each token would have expired."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._until: dict[str, int] = {}
        self._lock = threading.Lock()

    def revoke(self, session: SessionInfo) -> None:
        with self._lock:
            now = self._clock()
            self._until = {n: t for n, t in self._until.items() if t > now}
            self._until[session.nonce] = session.expires_at

    def __contains__(self, nonce: object) -> bool:
        with self._lock:
            return nonce in self._until

    def __len__(self) -> int:
        with self._lock:
            return len(self._until)


@dataclass
class Sessions:
    """Issues, checks and ends the session cookie."""

    signer: SessionSigner
    secure: bool  # production: Secure flag and the __Host- name
    revoked: RevokedSessions = field(default_factory=RevokedSessions)

    @property
    def cookie_name(self) -> str:
        return SECURE_COOKIE_NAME if self.secure else COOKIE_NAME

    def current(self, cookies: Mapping[str, str]) -> SessionInfo | None:
        session = self.signer.verify(cookies.get(self.cookie_name))
        if session is None or session.nonce in self.revoked:
            return None
        return session

    def start(self, response: Response) -> None:
        response.set_cookie(
            self.cookie_name,
            self.signer.issue(),
            max_age=self.signer.ttl_seconds,
            path="/",
            secure=self.secure,
            httponly=True,
            samesite="strict",
        )

    def end(self, response: Response, cookies: Mapping[str, str]) -> None:
        session = self.signer.verify(cookies.get(self.cookie_name))
        if session is not None:
            self.revoked.revoke(session)
        response.delete_cookie(
            self.cookie_name, path="/", secure=self.secure, httponly=True, samesite="strict"
        )
