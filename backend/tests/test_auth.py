"""Single-account login (DECISIONS.md D-035): the session cookie, what needs one, attempt
limits and the Origin check on writes.

Every password, hash and secret is made inside the test. Symbols are synthetic (AAA).
"""

import asyncio
import functools
import logging
import os
import re
import tempfile
import time
from pathlib import Path

import pytest
from fastapi import WebSocket
from fastapi.routing import APIRoute, iter_route_contexts
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker
from starlette.websockets import WebSocketDisconnect

from app.config import Settings, get_settings
from app.db.models import Transaction
from app.db.session import get_db
from app.deps import (
    get_artifacts_dir,
    get_congress_provider,
    get_cusip_resolver,
    get_extractor,
    get_finnhub,
    get_gdelt,
    get_guru_provider,
    get_provider,
    get_quote_cache,
    get_scorer,
    get_sec_configured,
    get_session_factory,
)
from app.main import create_app
from app.security.passwords import MAX_PASSWORD_CHARS, hash_password
from app.security.ratelimit import AttemptLimiter
from app.security.sessions import COOKIE_NAME, SECURE_COOKIE_NAME, SessionSigner
from app.services.market_data import QuoteCache

PASSWORD = "test-only passphrase 0001"
OTHER_PASSWORD = "test-only passphrase 0002"
SECRET = "test-only-session-secret-" + "0" * 32
AUTH_REQUIRED = {"detail": "로그인이 필요합니다", "code": "auth_required"}
TRADE = {
    "asset_type": "stock",
    "symbol": "AAA",
    "side": "buy",
    "trade_date": "2026-10-01",
    "quantity": 1,
    "price": 100,
}


@functools.lru_cache
def cheap_hash(password: str = PASSWORD) -> str:
    """Fast to verify; fine for development-mode tests only."""
    return hash_password(password, n=2**4, r=1, p=1)


@functools.lru_cache
def production_hash() -> str:
    """The weakest cost production accepts, so tests stay quick."""
    return hash_password(PASSWORD, n=2**14, r=8, p=1)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Settings built here never see the shell's AM_ variables (ISSUE-014)."""
    for key in list(os.environ):
        if key.upper().startswith("AM_"):
            monkeypatch.delenv(key)
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def settings(**kwargs) -> Settings:
    return Settings(_env_file=None, **kwargs)


def login_settings(**kwargs) -> Settings:
    return settings(**({"auth_password_hash": cheap_hash(), "session_secret": SECRET} | kwargs))


class Offline:
    """Stands in for every external service: a test that reaches one fails loudly."""

    def __getattr__(self, name: str):
        raise AssertionError(f"this test must not reach an external service ({name})")


# Never created: nothing here trains, and no route may read the real trained models.
NO_ARTIFACTS = Path(tempfile.gettempdir()) / "asset-manager-tests-no-artifacts"


def make_client(db, provider, config: Settings, *, https: bool = False, **kwargs) -> TestClient:
    app = create_app(config)
    quote_cache = QuoteCache()
    factory = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
    app.dependency_overrides.update(
        {
            get_db: lambda: db,
            get_provider: lambda: provider,
            get_quote_cache: lambda: quote_cache,
            # Hermetic even if a check under test let a request through: background jobs
            # stay on the test database, and no route can reach the network, an LLM or the
            # trained models on disk.
            get_session_factory: lambda: factory,
            get_artifacts_dir: lambda: NO_ARTIFACTS,
            get_congress_provider: Offline,
            get_guru_provider: Offline,
            get_gdelt: Offline,
            get_extractor: Offline,
            get_finnhub: lambda: None,
            get_scorer: lambda: None,
            get_cusip_resolver: lambda: None,
            get_sec_configured: lambda: False,
        }
    )
    scheme = "https" if https else "http"
    return TestClient(app, base_url=f"{scheme}://localhost", **kwargs)


@pytest.fixture
def auth_client(db, provider):
    with make_client(db, provider, login_settings()) as c:
        yield c


def login(client, password: str = PASSWORD, **kwargs):
    return client.post("/api/auth/login", json={"password": password}, **kwargs)


def api_routes(app) -> list[tuple[str, str]]:
    """(method, path template) of every route FastAPI serves, included routers and all."""
    out = []
    for ctx in iter_route_contexts(app.routes):
        if isinstance(ctx.original_route, APIRoute):
            out += [(method, ctx.path) for method in sorted(ctx.methods or [])]
    return out


def concrete(path: str) -> str:
    return re.sub(r"\{(\w+)[^}]*\}", lambda m: "AAA" if m.group(1) == "symbol" else "1", path)


def trade_count(db) -> int:
    return db.scalar(select(func.count()).select_from(Transaction))


# --- no login configured: the development default ----------------------------------------


def test_without_a_login_the_api_is_open_as_before(client):
    assert client.get("/api/auth/session").json() == {
        "auth_required": False,
        "authenticated": False,
        "demo_mode": False,
    }
    assert client.get("/api/transactions").status_code == 200
    assert client.post("/api/transactions", json=TRADE).status_code == 201
    res = login(client)
    assert res.status_code == 409
    assert res.json()["code"] == "login_not_configured"
    assert "set-cookie" not in res.headers
    assert client.post("/api/auth/logout").status_code == 204


# --- what needs a session ---------------------------------------------------------------


def test_every_api_route_needs_a_session(auth_client, db):
    routes = api_routes(auth_client.app)
    protected = [(m, p) for m, p in routes if p != "/api/health" and not p.startswith("/api/auth/")]
    assert len(protected) >= 60  # the whole API, not a sample
    assert all(p.startswith("/api/") for _, p in routes)
    for method, path in protected:
        res = auth_client.request(method, concrete(path), json=TRADE)
        assert res.status_code == 401, (method, path)
        assert res.json() == AUTH_REQUIRED, (method, path)
        assert res.headers["cache-control"] == "no-store"
    assert trade_count(db) == 0  # no write got through


def test_other_methods_and_unknown_paths_under_api_are_closed_too(auth_client):
    for method in ("HEAD", "OPTIONS", "PATCH", "TRACE"):
        assert auth_client.request(method, "/api/transactions").status_code == 401, method
    for path in ("/api", "/api/", "/api/nothing-here", "/api/health/", "/api/healthz", "/api/auth"):
        assert auth_client.get(path).status_code == 401, path
    # Percent-encoding reaches the router decoded, and the check sees the same path.
    assert auth_client.get("/%61pi/transactions").status_code == 401


def raw_get(app, path: str) -> int:
    """Status for a path sent exactly as written (an HTTP client would tidy it up first)."""
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"localhost")],
        "client": ("127.0.0.1", 50000),
        "server": ("localhost", 80),
    }
    asyncio.run(app(scope, receive, send))
    return sent[0]["status"]


def test_odd_spellings_of_an_api_path_never_reach_a_route(auth_client):
    app = auth_client.app
    assert raw_get(app, "/api/transactions") == 401
    assert raw_get(app, "/api/health") == 200
    # Everything that starts with /api/ needs a session, whatever follows.
    for path in ("/api/../api/transactions", "/api/./transactions", "/api//transactions"):
        assert raw_get(app, path) == 401, path
    # Spellings the check lets through are not API routes for the router either: it is
    # case-sensitive and does not collapse slashes or dot segments.
    for path in (
        "/API/transactions",
        "//api/transactions",
        "/x/../api/transactions",
        "/./api/transactions",
        "/api%2Ftransactions",
        "/apiX/transactions",
        "api/transactions",
    ):
        assert raw_get(app, path) == 404, path


def test_health_auth_routes_and_static_paths_stay_public(db, provider):
    client = make_client(db, provider, login_settings())

    @client.app.get("/assets/app.js")
    def static_file():
        return {"static": True}

    with client as c:
        assert c.get("/api/health").json() == {"status": "ok"}
        assert c.get("/api/auth/session").json() == {
            "auth_required": True,
            "authenticated": False,
            "demo_mode": False,
        }
        assert c.get("/assets/app.js").status_code == 200  # the login page must load
        assert c.post("/api/auth/logout").status_code == 204


def test_root_path_cannot_be_used_to_step_around_the_check(db, provider):
    with make_client(db, provider, login_settings(), root_path="/app") as c:
        assert c.get("/app/api/transactions").status_code == 401
        assert c.get("/api/transactions").status_code == 401
        assert c.get("/app/api/health").status_code == 200


def test_websockets_under_api_need_a_session_too(db, provider):
    client = make_client(db, provider, login_settings())

    @client.app.websocket("/api/live")
    async def live(ws: WebSocket):
        await ws.accept()
        await ws.send_text("hello")
        await ws.close()

    url = "ws://localhost/api/live"  # the test client would otherwise say Host: testserver
    with client as c:
        with pytest.raises(WebSocketDisconnect) as refused, c.websocket_connect(url):
            pass
        assert refused.value.code == 1008  # closed by the session check, before the route
        assert login(c).status_code == 204
        with c.websocket_connect(url) as ws:
            assert ws.receive_text() == "hello"


# --- logging in and out ------------------------------------------------------------------


def test_login_sets_a_strict_http_only_cookie(auth_client):
    res = login(auth_client)
    assert res.status_code == 204 and res.content == b""
    cookie = res.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE_NAME}=v1.")
    lowered = cookie.lower()
    assert "httponly" in lowered and "samesite=strict" in lowered and "path=/" in lowered
    assert f"max-age={168 * 3600}" in lowered
    assert "secure" not in lowered and "domain" not in lowered  # plain http in development
    assert res.headers["cache-control"] == "no-store"

    assert auth_client.get("/api/auth/session").json()["authenticated"] is True
    assert auth_client.get("/api/transactions").status_code == 200
    assert auth_client.post("/api/transactions", json=TRADE).status_code == 201


def test_production_cookie_is_secure_and_host_bound(db, provider):
    config = settings(
        env="production",
        auth_password_hash=production_hash(),
        session_secret=SECRET,
        session_ttl_hours=2,
    )
    with make_client(db, provider, config, https=True) as c:
        res = login(c)
        assert res.status_code == 204
        cookie = res.headers["set-cookie"]
        assert cookie.startswith(f"{SECURE_COOKIE_NAME}=v1.")
        lowered = cookie.lower()
        assert "secure" in lowered and "httponly" in lowered and "samesite=strict" in lowered
        assert "path=/" in lowered and "domain" not in lowered and "max-age=7200" in lowered
        assert c.get("/api/transactions").status_code == 200
        # The development cookie name is not accepted here.
        token = c.cookies[SECURE_COOKIE_NAME]
        c.cookies.clear()
        c.cookies.set(COOKIE_NAME, token)
        assert c.get("/api/transactions").status_code == 401


def test_wrong_password_gets_401_and_no_cookie(auth_client):
    for attempt in (OTHER_PASSWORD, PASSWORD + " ", PASSWORD.upper(), "x"):
        res = login(auth_client, attempt)
        assert res.status_code == 401
        assert res.json() == {
            "detail": "비밀번호가 올바르지 않습니다",
            "code": "invalid_credentials",
        }
        assert "set-cookie" not in res.headers
    assert auth_client.get("/api/auth/session").json()["authenticated"] is False
    assert auth_client.get("/api/transactions").status_code == 401


@pytest.mark.parametrize(
    "body",
    [{}, {"password": ""}, {"password": None}, {"password": "x" * (MAX_PASSWORD_CHARS + 1)}, []],
)
def test_malformed_login_bodies_are_rejected_before_hashing(auth_client, body):
    assert auth_client.post("/api/auth/login", json=body).status_code == 422


def test_logout_clears_the_cookie_and_revokes_the_token(auth_client):
    assert login(auth_client).status_code == 204
    token = auth_client.cookies[COOKIE_NAME]
    res = auth_client.post("/api/auth/logout")
    assert res.status_code == 204
    cleared = res.headers["set-cookie"].lower()
    assert cleared.startswith(f"{COOKIE_NAME}=") and "max-age=0" in cleared
    assert "httponly" in cleared and "samesite=strict" in cleared
    assert COOKIE_NAME not in auth_client.cookies
    assert auth_client.get("/api/transactions").status_code == 401

    # A copy of the old cookie no longer works either.
    auth_client.cookies.set(COOKIE_NAME, token)
    assert auth_client.get("/api/transactions").status_code == 401
    assert auth_client.get("/api/auth/session").json()["authenticated"] is False
    # Logging in again issues a fresh, working token.
    auth_client.cookies.clear()
    assert login(auth_client).status_code == 204
    assert auth_client.cookies[COOKIE_NAME] != token
    assert auth_client.get("/api/transactions").status_code == 200


def test_forged_tampered_and_expired_cookies_are_refused(auth_client):
    assert login(auth_client).status_code == 204
    good = auth_client.cookies[COOKIE_NAME]
    version, expires, nonce, mac = good.split(".")
    ttl = 168 * 3600
    expired = SessionSigner(SECRET, cheap_hash(), ttl, lambda: time.time() - ttl - 5).issue()
    other_secret = SessionSigner(SECRET + "x", cheap_hash(), ttl).issue()
    forged = [
        f"{version}.{int(expires) + 86400}.{nonce}.{mac}",
        f"{version}.{expires}.{nonce}.{mac[::-1]}",
        f"{version}.{expires}.{nonce}",
        "v1.9999999999.nonce.signature",
        expired,
        other_secret,
        "",
    ]
    for token in forged:
        auth_client.cookies.clear()
        auth_client.cookies.set(COOKIE_NAME, token)
        assert auth_client.get("/api/transactions").status_code == 401, token
        assert auth_client.get("/api/auth/session").json()["authenticated"] is False
    auth_client.cookies.clear()
    auth_client.cookies.set(COOKIE_NAME, good)
    assert auth_client.get("/api/transactions").status_code == 200


def test_changing_the_password_ends_existing_sessions(db, provider):
    with make_client(db, provider, login_settings()) as old:
        assert login(old).status_code == 204
        token = old.cookies[COOKIE_NAME]
    changed = login_settings(auth_password_hash=cheap_hash(OTHER_PASSWORD))
    with make_client(db, provider, changed) as new:
        new.cookies.set(COOKIE_NAME, token)
        assert new.get("/api/transactions").status_code == 401
        assert login(new, PASSWORD).status_code == 401
        assert login(new, OTHER_PASSWORD).status_code == 204


def test_a_restart_keeps_a_session(db, provider):
    with make_client(db, provider, login_settings()) as first:
        assert login(first).status_code == 204
        token = first.cookies[COOKIE_NAME]
    with make_client(db, provider, login_settings()) as second:  # same hash and secret
        second.cookies.set(COOKIE_NAME, token)
        assert second.get("/api/transactions").status_code == 200


# --- attempt limits ----------------------------------------------------------------------


def test_too_many_wrong_passwords_lock_the_address_out(auth_client):
    assert [login(auth_client, "wrong").status_code for _ in range(5)] == [401] * 5
    res = login(auth_client, "wrong")
    assert res.status_code == 429
    assert res.json()["code"] == "rate_limited"
    assert 1 <= int(res.headers["retry-after"]) <= 15 * 60
    # The right password does not help while locked out, and sets no cookie.
    res = login(auth_client)
    assert res.status_code == 429 and "set-cookie" not in res.headers
    assert auth_client.get("/api/auth/session").json()["authenticated"] is False


def test_lockout_ends_when_the_window_has_passed(auth_client):
    now = [1000.0]
    state = auth_client.app.state.security
    state.login_attempts = AttemptLimiter(5, 15 * 60, clock=lambda: now[0])
    for _ in range(5):
        login(auth_client, "wrong")
    assert login(auth_client).status_code == 429
    now[0] += 15 * 60 - 1
    assert login(auth_client).status_code == 429
    now[0] += 1
    assert login(auth_client).status_code == 204


def test_a_successful_login_clears_the_address_counter(auth_client):
    for _ in range(3):
        assert [login(auth_client, "wrong").status_code for _ in range(4)] == [401] * 4
        assert login(auth_client).status_code == 204
    assert len(auth_client.app.state.security.all_login_attempts) == 1  # only the failures


def test_lockout_is_per_address_when_the_proxy_header_is_trusted(db, provider):
    config = login_settings(client_ip_header="CF-Connecting-IP", login_max_attempts=2)
    with make_client(db, provider, config) as c:
        attacker, owner = {"CF-Connecting-IP": "203.0.113.66"}, {"CF-Connecting-IP": "203.0.113.5"}
        assert [login(c, "wrong", headers=attacker).status_code for _ in range(3)] == [
            401,
            401,
            429,
        ]
        assert login(c, headers=owner).status_code == 204


def test_a_spoofed_header_buys_no_extra_attempts_by_default(auth_client):
    codes = [
        login(auth_client, "wrong", headers={"X-Forwarded-For": f"203.0.113.{i}"}).status_code
        for i in range(7)
    ]
    assert codes == [401] * 5 + [429] * 2


def test_failures_across_all_addresses_are_bounded(db, provider):
    # One wrong password per address: the per-address limit never trips, the global one does
    # (20 times the per-address limit inside the window).
    config = login_settings(client_ip_header="CF-Connecting-IP", login_max_attempts=1)
    with make_client(db, provider, config) as c:
        codes = [
            login(c, "wrong", headers={"CF-Connecting-IP": f"198.51.100.{i}"}).status_code
            for i in range(1, 23)
        ]
        assert codes == [401] * 20 + [429] * 2
        res = login(c, headers={"CF-Connecting-IP": "203.0.113.5"})
        assert res.status_code == 429 and "set-cookie" not in res.headers


# --- cross-site writes (CSRF) ------------------------------------------------------------


def test_writes_from_another_origin_are_refused(auth_client, db):
    assert login(auth_client).status_code == 204
    for origin in ("https://evil.example", "http://localhost.evil.example", "null", "file://"):
        res = auth_client.post("/api/transactions", json=TRADE, headers={"origin": origin})
        assert res.status_code == 403, origin
        assert res.json() == {
            "detail": "다른 사이트에서 보낸 요청은 받지 않습니다",
            "code": "csrf_origin_mismatch",
        }
    for method in ("PUT", "DELETE", "PATCH"):
        res = auth_client.request(
            method, "/api/transactions/1", headers={"origin": "https://evil.example"}
        )
        assert res.status_code == 403, method
    cross = {"sec-fetch-site": "cross-site"}  # an Origin-less cross-site request
    assert auth_client.post("/api/transactions", json=TRADE, headers=cross).status_code == 403
    assert trade_count(db) == 0


def test_same_origin_and_trusted_origins_may_write(auth_client, db):
    assert login(auth_client).status_code == 204
    allowed = [
        {},  # a non-browser client sends no Origin
        {"origin": "http://localhost"},  # the app's own origin
        {"origin": "https://localhost"},  # behind the tunnel the browser side is https
        {"origin": "http://localhost:5173"},  # AM_CORS_ORIGINS (the Vite dev server)
        {"sec-fetch-site": "same-origin"},
    ]
    for headers in allowed:
        res = auth_client.post("/api/transactions", json=TRADE, headers=headers)
        assert res.status_code == 201, headers
    assert trade_count(db) == len(allowed)


def test_reads_are_not_subject_to_the_origin_check(auth_client):
    assert login(auth_client).status_code == 204
    res = auth_client.get("/api/transactions", headers={"origin": "https://evil.example"})
    assert res.status_code == 200
    # ...and the cross-origin page still cannot read the answer: no CORS grant for it.
    assert "access-control-allow-origin" not in res.headers


def test_login_and_logout_from_another_origin_are_refused(auth_client):
    evil = {"origin": "https://evil.example"}
    assert login(auth_client, headers=evil).status_code == 403
    assert login(auth_client).status_code == 204
    assert auth_client.post("/api/auth/logout", headers=evil).status_code == 403
    assert auth_client.get("/api/auth/session").json()["authenticated"] is True


def test_cors_preflight_is_answered_without_a_session(auth_client):
    res = auth_client.options(
        "/api/transactions",
        headers={"origin": "http://localhost:5173", "access-control-request-method": "POST"},
    )
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == "http://localhost:5173"
    # Rejections stay readable for an allowed origin.
    res = auth_client.get("/api/transactions", headers={"origin": "http://localhost:5173"})
    assert res.status_code == 401
    assert res.headers["access-control-allow-origin"] == "http://localhost:5173"


# --- nothing secret in the logs ----------------------------------------------------------


def test_logs_never_contain_the_password_hash_or_token(auth_client, caplog):
    with caplog.at_level(logging.DEBUG):
        assert login(auth_client, "a-wrong-guess-123").status_code == 401
        assert login(auth_client).status_code == 204
        token = auth_client.cookies[COOKIE_NAME]
        assert auth_client.get("/api/transactions").status_code == 200
        assert auth_client.post("/api/auth/logout").status_code == 204
        for _ in range(6):
            login(auth_client, "a-wrong-guess-123")
    assert "login failed" in caplog.text and "login succeeded" in caplog.text
    assert "too many attempts" in caplog.text
    for secret in (PASSWORD, "a-wrong-guess-123", cheap_hash(), SECRET, token, token.split(".")[3]):
        assert secret not in caplog.text
