"""The security layer's building blocks (DECISIONS.md D-035): password hashes, session tokens,
request limits, startup rules, security headers and the middleware order.

Every password, hash and secret here is made inside the test; nothing reads backend/.env.
The login flow is in test_auth.py and the read-only demo in test_demo_mode.py.
"""

import base64
import functools
import inspect
import os
import tempfile
import unicodedata
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import sessionmaker
from starlette.responses import FileResponse, Response
from starlette.staticfiles import StaticFiles

from app import config as config_module
from app.config import Settings, get_settings
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
from app.security import hash_password as cli
from app.security.middleware import PUBLIC_BODY_LIMIT_BYTES
from app.security.passwords import (
    DEFAULT_N,
    MAX_PASSWORD_CHARS,
    PasswordHashError,
    hash_password,
    parse_hash,
    verify_password,
)
from app.security.paths import is_api, route_path
from app.security.policy import DEFAULT_CONTENT_SECURITY_POLICY, deployment_problem
from app.security.ratelimit import (
    OVERFLOW_KEY,
    AttemptLimiter,
    TokenBucketLimiter,
    client_ip,
    rate_key,
    retry_after_header,
)
from app.security.sessions import (
    COOKIE_NAME,
    SECURE_COOKIE_NAME,
    RevokedSessions,
    Sessions,
    SessionSigner,
    _mac,
)
from app.services.market_data import QuoteCache

PASSWORD = "test-only passphrase 0001"
SECRET = "test-only-session-secret-" + "0" * 32
SECURITY_HEADERS = (
    "strict-transport-security",
    "x-content-type-options",
    "referrer-policy",
    "x-frame-options",
    "content-security-policy",
)


@functools.lru_cache
def cheap_hash() -> str:
    """Fast to verify; fine for development-mode tests only."""
    return hash_password(PASSWORD, n=2**4, r=1, p=1)


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


class Clock:
    def __init__(self, now: float = 1_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


# --- password hashes -------------------------------------------------------------------


def test_hash_has_the_documented_format_and_verifies():
    encoded = cheap_hash()
    scheme, n, r, p, salt, key = encoded.split("$")
    assert (scheme, n, r, p) == ("scrypt", "16", "1", "1")
    assert not set(salt + key) & set("+/= ")  # safe to paste into an env file
    parsed = parse_hash(encoded)
    assert len(parsed.salt) == 16 and len(parsed.key) == 32
    assert verify_password(PASSWORD, parsed) is True
    assert verify_password(PASSWORD + "x", parsed) is False
    assert verify_password(PASSWORD.upper(), parsed) is False


def test_same_password_gets_a_new_salt_every_time():
    a, b = hash_password(PASSWORD, n=16, r=1, p=1), hash_password(PASSWORD, n=16, r=1, p=1)
    assert a != b
    assert verify_password(PASSWORD, parse_hash(a)) and verify_password(PASSWORD, parse_hash(b))


def test_default_cost_is_accepted_in_production():
    parsed = parse_hash(hash_password(PASSWORD))
    assert parsed.n == DEFAULT_N and parsed.strong_enough_for_production
    assert verify_password(PASSWORD, parsed)
    assert not parse_hash(cheap_hash()).strong_enough_for_production


def test_unicode_passphrase_is_normalized():
    composed = unicodedata.normalize("NFC", "비밀 문장 열두 글자 이상")
    decomposed = unicodedata.normalize("NFD", composed)
    parsed = parse_hash(hash_password(composed, n=16, r=1, p=1))
    assert composed != decomposed
    assert verify_password(decomposed, parsed)


def test_empty_and_oversized_passwords_are_refused_without_hashing():
    parsed = parse_hash(cheap_hash())
    assert verify_password("", parsed) is False
    assert verify_password("x" * (MAX_PASSWORD_CHARS + 1), parsed) is False
    with pytest.raises(ValueError):
        hash_password("")
    with pytest.raises(ValueError):
        hash_password("x" * (MAX_PASSWORD_CHARS + 1))


def test_parse_accepts_standard_base64_with_padding():
    parsed = parse_hash(cheap_hash())
    salt, key = (base64.b64encode(raw).decode() for raw in (parsed.salt, parsed.key))
    assert key.endswith("=")  # 32 bytes always pad
    assert parse_hash(f"scrypt$16$1$1${salt}${key}") == parsed


@pytest.mark.parametrize(
    "mutate",
    [
        lambda h: h.replace("scrypt", "bcrypt"),
        lambda h: h.replace("$", ":"),
        lambda h: "$".join(h.split("$")[:5]),  # a shell ate one field
        lambda h: h.replace("$16$", "$sixteen$"),
        lambda h: h.replace("$16$", "$15$"),  # not a power of two
        lambda h: h.replace("$16$", f"${2**21}$"),  # would allocate gigabytes
        lambda h: h.replace("$16$1$1$", "$16$64$1$"),
        lambda h: h.replace("$16$1$1$", "$16$1$0$"),
        lambda h: h + "!!",
        lambda h: "$".join([*h.split("$")[:4], "AAAA", h.split("$")[5]]),  # 3-byte salt
        lambda h: "$".join([*h.split("$")[:5], "AAAA"]),  # 3-byte key
        lambda h: "",
    ],
)
def test_malformed_hashes_are_rejected_without_echoing_them(mutate):
    bad = mutate(cheap_hash())
    with pytest.raises(PasswordHashError) as exc:
        parse_hash(bad)
    salt, key = cheap_hash().split("$")[4:]
    assert salt not in str(exc.value) and key not in str(exc.value)


def test_parsed_hash_repr_hides_salt_and_key():
    parsed = parse_hash(cheap_hash())
    assert "salt" not in repr(parsed) and "key" not in repr(parsed)


# --- session tokens --------------------------------------------------------------------


def signer(clock=None, secret=SECRET, password_hash="hash-a", ttl=3600) -> SessionSigner:
    return SessionSigner(secret, password_hash, ttl, clock or Clock())


def test_token_round_trip_and_expiry():
    clock = Clock()
    s = signer(clock)
    token = s.issue()
    session = s.verify(token)
    assert session is not None and session.expires_at == int(clock.now) + 3600
    clock.now += 3599
    assert s.verify(token) is not None
    clock.now += 1  # exactly at the expiry second
    assert s.verify(token) is None


def test_tampered_tokens_are_rejected():
    clock = Clock()
    s = signer(clock)
    token = s.issue()
    version, expires, nonce, mac = token.split(".")
    forged = [
        f"{version}.{int(expires) + 86400}.{nonce}.{mac}",  # a longer life
        f"{version}.{expires}.{nonce}x.{mac}",
        f"v2.{expires}.{nonce}.{mac}",
        f"{version}.{expires}.{nonce}.{mac[:-1]}{'A' if mac[-1] != 'A' else 'B'}",
        f"{version}.{expires}.{nonce}",
        f"{version}.{expires}.{nonce}.",
        token + ".extra",
        mac,
        "",
        None,
        "x" * 10_000,
        token.replace("v1", "v１"),  # non-ASCII
    ]
    for bad in forged:
        assert s.verify(bad) is None, bad
    assert s.verify(token) is not None


def test_token_is_bound_to_the_secret_and_the_password_hash():
    clock = Clock()
    token = signer(clock).issue()
    assert signer(clock).verify(token) is not None
    assert signer(clock, secret=SECRET + "x").verify(token) is None
    # Changing the password ends every session.
    assert signer(clock, password_hash="hash-b").verify(token) is None


def test_a_validly_signed_token_with_odd_fields_is_still_rejected():
    # Sign payloads the server itself would never issue: the checks after the MAC hold.
    s = signer()
    for payload in ("v1.notanumber.nonce", "v1.-5.nonce", "v9.9999999999.nonce", "v1.9999999999"):
        assert s.verify(f"{payload}.{_mac(s._key, payload)}") is None


def test_revoked_sessions_expire_from_memory():
    clock = Clock()
    s = signer(clock, ttl=100)
    revoked = RevokedSessions(clock)
    first = s.verify(s.issue())
    revoked.revoke(first)
    assert first.nonce in revoked and len(revoked) == 1
    clock.now += 101
    revoked.revoke(s.verify(s.issue()))  # pruning happens on the next revoke
    assert first.nonce not in revoked and len(revoked) == 1


def test_cookie_name_and_flags_follow_the_secure_setting():
    for secure, name in ((False, COOKIE_NAME), (True, SECURE_COOKIE_NAME)):
        sessions = Sessions(signer(), secure=secure)
        response = Response()
        sessions.start(response)
        cookie = response.headers["set-cookie"]
        assert cookie.startswith(f"{name}=v1.")
        lowered = cookie.lower()
        assert "httponly" in lowered and "samesite=strict" in lowered and "path=/" in lowered
        assert "max-age=3600" in lowered and "domain" not in lowered
        assert ("secure" in lowered) is secure
    assert SECURE_COOKIE_NAME.startswith("__Host-")


# --- request limits ----------------------------------------------------------------------


def test_token_bucket_allows_a_burst_then_refills():
    clock = Clock()
    limiter = TokenBucketLimiter(60, clock=clock)
    assert all(limiter.check("a") == 0.0 for _ in range(60))
    wait = limiter.check("a")
    assert wait == pytest.approx(1.0)  # one token per second at 60 a minute
    assert limiter.check("b") == 0.0  # other addresses are unaffected
    clock.now += 1.0
    assert limiter.check("a") == 0.0
    assert limiter.check("a") > 0
    clock.now += 3600
    assert all(limiter.check("a") == 0.0 for _ in range(60))  # never more than the burst
    assert limiter.check("a") > 0


def test_token_bucket_forgets_idle_addresses():
    clock = Clock()
    limiter = TokenBucketLimiter(60, clock=clock)
    for i in range(500):
        limiter.check(f"ip-{i}")
    assert len(limiter) == 500
    clock.now += 61  # long enough for every bucket to be full again
    limiter.check("fresh")
    assert len(limiter) == 1


def test_token_bucket_memory_is_capped():
    clock = Clock()
    limiter = TokenBucketLimiter(2, clock=clock, max_keys=10)
    for i in range(1_000):
        limiter.check(f"ip-{i}")
    assert len(limiter) <= 11  # ten addresses plus the shared overflow bucket
    # Addresses past the cap share one bucket instead of getting a free pass.
    assert limiter.check("yet-another") > 0
    assert OVERFLOW_KEY in limiter._buckets


def test_token_bucket_rejects_a_zero_rate():
    with pytest.raises(ValueError):
        TokenBucketLimiter(0)


def test_attempt_limiter_blocks_after_the_limit_and_slides():
    clock = Clock()
    limiter = AttemptLimiter(3, 900, clock=clock)
    assert [limiter.acquire("a") for _ in range(3)] == [0.0, 0.0, 0.0]
    assert limiter.acquire("a") == pytest.approx(900)
    assert limiter.acquire("b") == 0.0
    clock.now += 600
    assert limiter.acquire("a") == pytest.approx(300)
    clock.now += 300  # the first three attempts leave the window
    assert limiter.acquire("a") == 0.0


def test_attempt_limiter_reset_forgive_and_pruning():
    clock = Clock()
    limiter = AttemptLimiter(2, 60, clock=clock)
    limiter.acquire("a")
    limiter.acquire("a")
    limiter.forgive("a")
    assert limiter.acquire("a") == 0.0
    assert limiter.acquire("a") > 0
    limiter.reset("a")
    assert limiter.acquire("a") == 0.0
    for i in range(200):
        limiter.acquire(f"ip-{i}")
    assert len(limiter) == 201
    clock.now += 61
    limiter.acquire("later")
    assert len(limiter) == 1


def test_attempt_limiter_memory_is_capped():
    clock = Clock()
    limiter = AttemptLimiter(1, 60, clock=clock, max_keys=5)
    for i in range(100):
        limiter.acquire(f"ip-{i}")
    assert len(limiter) <= 6
    assert limiter.acquire("new-address") > 0  # shares the overflow budget


def scope(client=("198.51.100.4", 5000), headers=()) -> dict:
    return {
        "type": "http",
        "client": client,
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers],
    }


def test_forwarding_header_is_ignored_unless_configured():
    spoofed = scope(headers=[("CF-Connecting-IP", "203.0.113.9"), ("X-Forwarded-For", "1.1.1.1")])
    assert client_ip(spoofed) == "198.51.100.4"
    assert client_ip(spoofed, "CF-Connecting-IP") == "203.0.113.9"
    assert client_ip(scope(), "CF-Connecting-IP") == "198.51.100.4"  # header missing
    garbage = scope(headers=[("CF-Connecting-IP", "not-an-address")])
    assert client_ip(garbage, "CF-Connecting-IP") == "198.51.100.4"
    chain = scope(headers=[("X-Forwarded-For", "6.6.6.6, 203.0.113.9")])
    assert client_ip(chain, "X-Forwarded-For") == "203.0.113.9"  # the proxy's own entry
    assert client_ip(scope(client=None)) == "unknown"


def test_rate_key_groups_an_ipv6_subscriber():
    assert rate_key("203.0.113.9") == "203.0.113.9"
    assert (
        rate_key("2001:db8:1:2:aaaa::1") == rate_key("2001:db8:1:2:bbbb::2") == "2001:db8:1:2::/64"
    )
    assert rate_key("2001:db8:1:3::1") != rate_key("2001:db8:1:2::1")
    assert rate_key("::ffff:203.0.113.9") == "203.0.113.9"
    assert rate_key("testclient") == "testclient"


def test_retry_after_is_a_whole_number_of_seconds_and_at_least_one():
    assert retry_after_header(0.01) == "1"
    assert retry_after_header(59.2) == "60"


# --- startup rules (config) --------------------------------------------------------------


def test_defaults_are_the_local_development_setup():
    s = settings()
    assert s.env == "development" and s.demo_mode is False
    assert s.auth_password_hash is None and s.session_secret is None
    assert s.session_ttl_hours == 168
    assert (s.login_max_attempts, s.login_window_minutes) == (5, 15)
    assert s.rate_limit_per_minute == 0 and s.client_ip_header == ""
    assert s.static_dir is None
    assert s.content_security_policy == DEFAULT_CONTENT_SECURITY_POLICY
    assert s.live_trading is False


def test_production_refuses_to_start_open():
    with pytest.raises(ValidationError, match="AM_ENV=production needs"):
        settings(env="production")
    with pytest.raises(ValidationError, match="AM_ENV=production needs"):
        settings(env="production", session_secret=SECRET)  # a secret alone is not a login
    with pytest.raises(ValidationError, match="needs AM_SESSION_SECRET"):
        settings(env="production", auth_password_hash=production_hash())


def test_production_starts_as_a_demo_or_with_a_login():
    assert settings(env="production", demo_mode=True).demo_mode is True
    s = settings(env="production", auth_password_hash=production_hash(), session_secret=SECRET)
    assert s.auth_password_hash is not None
    both = settings(
        env="production",
        demo_mode=True,
        auth_password_hash=production_hash(),
        session_secret=SECRET,
    )
    assert both.demo_mode and both.auth_password_hash is not None


def test_a_login_needs_a_long_secret_and_a_real_hash_in_any_environment():
    with pytest.raises(ValidationError, match="needs AM_SESSION_SECRET"):
        settings(auth_password_hash=cheap_hash())
    with pytest.raises(ValidationError, match="at least 32 bytes"):
        settings(auth_password_hash=cheap_hash(), session_secret="x" * 31)
    with pytest.raises(ValidationError, match="at least 32 bytes"):
        settings(session_secret="short")
    with pytest.raises(ValidationError, match="AM_AUTH_PASSWORD_HASH"):
        settings(auth_password_hash="plain-text-password", session_secret=SECRET)
    assert settings(auth_password_hash=cheap_hash(), session_secret=SECRET).env == "development"


def test_production_refuses_a_cheap_hash():
    with pytest.raises(ValidationError, match="too cheap for production"):
        settings(env="production", auth_password_hash=cheap_hash(), session_secret=SECRET)


def test_demo_never_runs_with_real_orders(monkeypatch):
    # No test may switch the real-order flag on (tests/test_execution.py scans for it), so the
    # rule is proven on the pure function and the wiring from the default side.
    problem = deployment_problem(
        production=True,
        demo_mode=True,
        real_orders_enabled=True,
        password_hash=None,
        session_secret=None,
    )
    assert problem is not None and "AM_DEMO_MODE" in problem
    for production in (False, True):
        assert (
            deployment_problem(
                production=production,
                demo_mode=True,
                real_orders_enabled=False,
                password_hash=None,
                session_secret=None,
            )
            is None
        )

    seen = {}

    def spy(**kwargs):
        seen.update(kwargs)
        return None

    monkeypatch.setattr(config_module, "deployment_problem", spy)
    built = settings(demo_mode=True)
    assert seen["real_orders_enabled"] is built.live_trading is False
    assert seen["demo_mode"] is True
    assert "real_orders_enabled=self.live_trading" in inspect.getsource(Settings)


def leaks(text: str, secret: str, size: int = 8) -> bool:
    """Any `size`-character piece of the secret in the text (pydantic truncates the input it
    prints, so a whole-string search would miss the tail it does show)."""
    return any(secret[i : i + size] in text for i in range(len(secret) - size + 1))


def test_startup_errors_never_print_a_secret(clean_env):
    bad_secret = "leaky-session-secret-value"
    fake_key = "sk-ant-api03-FAKE-0123456789"
    with pytest.raises(ValidationError) as exc:
        settings(auth_password_hash=cheap_hash(), session_secret=bad_secret)
    assert not leaks(str(exc.value), bad_secret) and not leaks(str(exc.value), cheap_hash())

    # Through environment variables a model-level error would print the input dict, whose
    # truncated form still shows the tail of the last value (hide_input_in_errors).
    clean_env.setenv("AM_ANTHROPIC_API_KEY", fake_key)
    clean_env.setenv("AM_AUTH_PASSWORD_HASH", cheap_hash())
    clean_env.setenv("AM_SESSION_SECRET", bad_secret)
    with pytest.raises(ValidationError) as exc:
        settings()
    text = str(exc.value) + repr(exc.value)
    assert "AM_SESSION_SECRET must be at least 32 bytes" in text
    assert "input_value" not in text
    for secret in (bad_secret, cheap_hash(), fake_key):
        assert not leaks(text, secret)

    clean_env.setenv("AM_AUTH_PASSWORD_HASH", "scrypt$oops-a-typo-in-the-hash")
    clean_env.setenv("AM_SESSION_SECRET", SECRET)
    with pytest.raises(ValidationError) as exc:
        settings()
    text = str(exc.value) + repr(exc.value)
    assert "AM_AUTH_PASSWORD_HASH" in text
    assert not leaks(text, "oops-a-typo-in-the-hash") and not leaks(text, SECRET)

    # A field-level error (a mistyped number) hides its input too.
    clean_env.setenv("AM_AUTH_PASSWORD_HASH", "")
    clean_env.setenv("AM_SESSION_TTL_HOURS", "a-week")
    with pytest.raises(ValidationError) as exc:
        settings()
    assert "session_ttl_hours" in str(exc.value) and "input_value" not in str(exc.value)


def test_secrets_stay_out_of_repr():
    s = settings(auth_password_hash=cheap_hash(), session_secret=SECRET)
    assert cheap_hash() not in repr(s) and SECRET not in repr(s)
    assert cheap_hash() not in s.model_dump_json() and SECRET not in s.model_dump_json()


def test_blank_values_mean_unset(clean_env):
    for name in ("AM_AUTH_PASSWORD_HASH", "AM_SESSION_SECRET", "AM_STATIC_DIR"):
        clean_env.setenv(name, "  ")
    clean_env.setenv("AM_CONTENT_SECURITY_POLICY", "")
    s = settings()
    assert s.auth_password_hash is None and s.session_secret is None
    # An empty path would otherwise mean "serve the working directory".
    assert s.static_dir is None
    assert s.content_security_policy == DEFAULT_CONTENT_SECURITY_POLICY
    clean_env.setenv("AM_STATIC_DIR", "dist")
    assert settings().static_dir == Path("dist")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"env": "staging"},
        {"session_ttl_hours": 0},
        {"login_max_attempts": 0},
        {"login_window_minutes": 0},
        {"rate_limit_per_minute": -1},
        {"client_ip_header": "X Bad\r\nHeader"},
        {"demo_mode": "maybe"},
    ],
)
def test_out_of_range_values_fail_at_startup(kwargs):
    with pytest.raises(ValidationError):
        settings(**kwargs)


def test_default_policy_allows_only_same_origin_scripts_and_no_framing():
    csp = DEFAULT_CONTENT_SECURITY_POLICY
    assert "script-src 'self';" in csp and "'unsafe-eval'" not in csp
    assert "unsafe-inline" not in csp.split("script-src")[1].split(";")[0]
    assert "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
    assert "default-src 'self'" in csp and "connect-src 'self'" in csp


# --- middleware: order, headers, limits --------------------------------------------------


def layer_names(app) -> list[str]:
    return [m.cls.__name__ for m in app.user_middleware]


def test_development_default_keeps_the_old_stack():
    app = create_app(settings())
    assert layer_names(app) == ["TrustedHostMiddleware", "CORSMiddleware"]


def test_full_stack_order_outermost_first():
    app = create_app(
        settings(
            env="production",
            demo_mode=True,
            auth_password_hash=production_hash(),
            session_secret=SECRET,
            rate_limit_per_minute=60,
        )
    )
    assert layer_names(app) == [
        "TrustedHostMiddleware",
        "SecurityHeadersMiddleware",
        "CORSMiddleware",
        "RateLimitMiddleware",
        "PublicBodyLimitMiddleware",
        "DemoReadOnlyMiddleware",
        "AuthMiddleware",
    ]


def test_route_path_matches_the_router_under_a_root_path():
    assert route_path({"path": "/api/x"}) == "/api/x"
    assert route_path({"path": "/app/api/x", "root_path": "/app"}) == "/api/x"
    assert route_path({"path": "/app", "root_path": "/app"}) == ""
    assert route_path({"path": "/application/x", "root_path": "/app"}) == "/application/x"
    assert route_path({"path": "/api/x", "root_path": "/app"}) == "/api/x"


def test_development_sends_no_security_headers_and_serves_docs(db, provider):
    with make_client(db, provider, settings()) as c:
        res = c.get("/api/health")
        assert res.status_code == 200
        assert not any(h in res.headers for h in SECURITY_HEADERS)
        assert c.get("/docs").status_code == 200
        assert c.get("/openapi.json").status_code == 200


def test_production_hides_the_api_schema(db, provider):
    with make_client(db, provider, settings(env="production", demo_mode=True)) as c:
        for path in ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"):
            assert c.get(path).status_code == 404, path
        assert c.get("/api/health").status_code == 200


def assert_security_headers(res, csp=DEFAULT_CONTENT_SECURITY_POLICY) -> None:
    assert res.headers["strict-transport-security"].startswith("max-age=31536000")
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["referrer-policy"] == "same-origin"
    assert res.headers["x-frame-options"] == "DENY"
    assert res.headers["content-security-policy"] == csp
    assert res.headers["cross-origin-opener-policy"] == "same-origin"
    assert "permissions-policy" in res.headers


def test_production_headers_on_every_kind_of_answer(db, provider):
    config = settings(
        env="production",
        auth_password_hash=production_hash(),
        session_secret=SECRET,
        rate_limit_per_minute=4,
    )
    client = make_client(db, provider, config, https=True, raise_server_exceptions=False)

    @client.app.get("/api/boom")
    def boom():
        raise RuntimeError("unhandled")

    @client.app.get("/page")
    def page():
        return {"static": True}

    with client as c:
        ok = c.get("/api/health")
        assert ok.status_code == 200
        assert_security_headers(ok)
        assert ok.headers["cache-control"] == "no-store"  # API answers are never cached

        static = c.get("/page")  # not under /api: no session needed, no cache header forced
        assert static.status_code == 200
        assert_security_headers(static)
        assert "cache-control" not in static.headers

        unauthorized = c.get("/api/transactions")
        assert unauthorized.status_code == 401
        assert_security_headers(unauthorized)

        forbidden = c.post("/api/auth/login", json={"password": "x"}, headers={"origin": "null"})
        assert forbidden.status_code == 403
        assert_security_headers(forbidden)

        missing = c.get("/nothing-here")
        assert missing.status_code == 404
        assert_security_headers(missing)

        assert c.post("/api/auth/login", json={"password": PASSWORD}).status_code == 204
        crashed = c.get("/api/boom")
        assert crashed.status_code == 500
        assert crashed.json() == {"detail": "Internal Server Error"}
        assert_security_headers(crashed)

        limited = [c.get("/api/auth/session") for _ in range(6)][-1]
        assert limited.status_code == 429
        assert_security_headers(limited)


def test_demo_rejection_carries_the_headers_and_a_custom_policy(db, provider):
    custom = "default-src 'self'; script-src 'self' 'sha256-abc='"
    config = settings(env="production", demo_mode=True, content_security_policy=custom)
    with make_client(db, provider, config, https=True) as c:
        res = c.post("/api/transactions", json={})
        assert res.status_code == 403 and res.json()["code"] == "demo_read_only"
        assert_security_headers(res, csp=custom)


def test_untrusted_host_is_rejected_before_anything_else(db, provider):
    config = settings(env="production", demo_mode=True, rate_limit_per_minute=1)
    with make_client(db, provider, config, https=True) as c:
        for _ in range(3):  # never reaches the limiter
            assert (
                c.get("/api/portfolio/holdings", headers={"host": "evil.example"}).status_code
                == 400
            )


def test_request_limit_per_address(db, provider):
    config = settings(rate_limit_per_minute=3)
    client = make_client(db, provider, config)

    @client.app.get("/page")
    def page():
        return {"static": True}

    with client as c:
        assert [c.get("/api/market/crypto").status_code for _ in range(3)] == [200, 200, 200]
        res = c.get("/api/market/crypto")
        assert res.status_code == 429
        assert res.json() == {
            "detail": "요청이 너무 많아요. 잠시 뒤에 다시 시도해 주세요",
            "code": "rate_limited",
        }
        assert 1 <= int(res.headers["retry-after"]) <= 20
        # The health check and non-API paths are never limited.
        assert [c.get("/api/health").status_code for _ in range(10)] == [200] * 10
        assert [c.get("/page").status_code for _ in range(10)] == [200] * 10
        # Without AM_CLIENT_IP_HEADER a forwarding header cannot buy a fresh budget.
        spoof = {"CF-Connecting-IP": "203.0.113.50", "X-Forwarded-For": "203.0.113.51"}
        assert c.get("/api/market/crypto", headers=spoof).status_code == 429


def test_request_limit_uses_the_configured_client_address_header(db, provider):
    config = settings(rate_limit_per_minute=2, client_ip_header="CF-Connecting-IP")
    with make_client(db, provider, config) as c:
        first, second = {"CF-Connecting-IP": "203.0.113.7"}, {"CF-Connecting-IP": "203.0.113.8"}
        assert [c.get("/api/market/crypto", headers=first).status_code for _ in range(3)] == [
            200,
            200,
            429,
        ]
        assert c.get("/api/market/crypto", headers=second).status_code == 200
        # One IPv6 subscriber (/64) is one client however many addresses it rotates through.
        v6 = [{"CF-Connecting-IP": f"2001:db8:5:6::{i:x}"} for i in range(1, 4)]
        assert [c.get("/api/market/crypto", headers=h).status_code for h in v6] == [200, 200, 429]


def test_rejected_requests_count_against_the_limit(db, provider):
    # The limiter sits outside the session check: hammering a locked API is limited too.
    config = settings(
        auth_password_hash=cheap_hash(), session_secret=SECRET, rate_limit_per_minute=3
    )
    with make_client(db, provider, config) as c:
        assert [c.get("/api/transactions").status_code for _ in range(5)] == [
            401,
            401,
            401,
            429,
            429,
        ]


def test_anonymous_request_bodies_are_capped(db, provider):
    big = b'{"password": "' + b"x" * PUBLIC_BODY_LIMIT_BYTES + b'"}'
    json_headers = {"content-type": "application/json"}
    login_config = settings(auth_password_hash=cheap_hash(), session_secret=SECRET)
    with make_client(db, provider, login_config) as c:
        res = c.post("/api/auth/login", content=big, headers=json_headers)
        assert res.status_code == 413
        assert c.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
    with make_client(db, provider, settings(demo_mode=True)) as c:
        res = c.post("/api/projection/simulate", content=big, headers=json_headers)
        assert res.status_code == 413


# --- the built frontend: static files and page routes -------------------------------------


def serve_frontend(app, folder: Path) -> None:
    """A stand-in for the real static serving: built files plus a page fallback that
    answers index.html for the frontend's own routes."""
    (folder / "assets").mkdir()
    (folder / "index.html").write_text("<!doctype html><title>app</title>", encoding="utf-8")
    (folder / "assets" / "app.js").write_text("console.log('app')", encoding="utf-8")
    app.mount("/assets", StaticFiles(directory=folder / "assets"), name="assets")

    # A page route whose parameter is named like the API's ticker parameter.
    @app.get("/stocks/{symbol}", include_in_schema=False)
    @app.get("/{page_path:path}", include_in_schema=False)
    def page(symbol: str = "", page_path: str = ""):
        return FileResponse(folder / "index.html")


FRONTEND_MODES = {
    "demo": {"demo_mode": True},
    "login": {"auth_password_hash": "production", "session_secret": SECRET},
    "demo+login": {
        "demo_mode": True,
        "auth_password_hash": "production",
        "session_secret": SECRET,
    },
}


@pytest.mark.parametrize("mode", sorted(FRONTEND_MODES))
def test_frontend_files_pass_every_layer_and_carry_the_headers(db, provider, tmp_path, mode):
    extra = dict(FRONTEND_MODES[mode])
    if "auth_password_hash" in extra:
        extra["auth_password_hash"] = production_hash()
    config = settings(env="production", rate_limit_per_minute=2, **extra)
    client = make_client(db, provider, config, https=True)
    serve_frontend(client.app, tmp_path)
    with client as c:
        # No session, no cookie, more requests than the limit: pages and files still load.
        pages = ("/", "/index.html", "/coach", "/learn/some-lesson", "/assets/app.js")
        # Page routes of the frontend that look like tickers or carry one in the query.
        # In the demo the ticker guard must leave them alone: it is for /api only.
        ticker_pages = ("/stocks/BBB", "/transactions?symbol=BBB", "/?symbols=BBB,CCC")
        for path in (*pages, *ticker_pages):
            res = c.get(path)
            assert res.status_code == 200, path
            assert_security_headers(res)
            assert res.headers.get("cache-control") != "no-store", path
        assert c.get("/assets/app.js").text == "console.log('app')"
        assert "<title>app</title>" in c.get("/coach").text
        # A missing file under the static folder is a plain 404, with the headers.
        missing = c.get("/assets/missing.js")
        assert missing.status_code == 404
        assert_security_headers(missing)
        # The demo lock and the session check apply to /api only: a write to a page path is
        # answered by the router (405), not by them.
        assert c.post("/coach").status_code == 405
        # ...while /api is as closed as without a frontend.
        api = c.get("/api/transactions")
        blocked = c.post("/api/transactions", json={})
        if "login" in mode:
            assert api.status_code == 401 and api.json()["code"] == "auth_required"
        if "demo" in mode:
            assert blocked.status_code == 403 and blocked.json()["code"] == "demo_read_only"
        else:
            assert blocked.status_code == 401
        assert_security_headers(api)
        assert_security_headers(blocked)


def test_only_api_paths_count_as_api():
    for path in ("/api", "/api/", "/api/x", "/api/x/y"):
        assert is_api(path), path
    for path in ("/", "", "/apix", "/API/x", "/assets/api/x", "//api/x", "api/x", "/index.html"):
        assert not is_api(path), path


# --- the hash CLI ------------------------------------------------------------------------


def answers(*values):
    queue = list(values)
    return lambda _prompt: queue.pop(0)


def test_cli_prints_one_line_that_verifies(capsys):
    assert cli.main(prompt=answers(PASSWORD, PASSWORD)) == 0
    out, err = capsys.readouterr()
    lines = out.splitlines()
    assert len(lines) == 1 and lines[0].startswith("scrypt$")
    parsed = parse_hash(lines[0])
    assert parsed.strong_enough_for_production and verify_password(PASSWORD, parsed)
    assert PASSWORD not in out + err
    assert "AM_AUTH_PASSWORD_HASH" in err  # the hint goes to stderr, not into the value


def test_cli_refuses_a_mismatch_or_a_short_password(capsys):
    assert cli.main(prompt=answers(PASSWORD, PASSWORD + "typo")) == 1
    assert cli.main(prompt=answers("short", "short")) == 1
    out, err = capsys.readouterr()
    assert out == "" and PASSWORD not in err and "short" not in err


def test_cli_reads_no_settings():
    source = inspect.getsource(cli)
    assert "app.config" not in source and "get_settings" not in source
    assert "getpass" in source
