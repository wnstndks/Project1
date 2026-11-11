"""The built frontend served by the API process (app/api/frontend.py, DECISIONS.md D-035).

A fake `vite build` output in tmp_path stands in for frontend/dist. The properties pinned
here: without AM_STATIC_DIR nothing changes; files are files and everything else is the
single-page app, except under /api, which keeps its JSON answers; nothing outside the
folder can be read; and the access-control layers treat pages and files as public while
/api stays as closed as before.
"""

import asyncio
import functools
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.routing import Router

from app.api.frontend import CACHE_HASHED, CACHE_REVALIDATE, Frontend
from app.config import Settings
from app.db.session import get_db
from app.deps import get_provider, get_quote_cache
from app.main import create_app
from app.security.passwords import hash_password
from app.security.policy import DEFAULT_CONTENT_SECURITY_POLICY
from app.services.market_data import QuoteCache

INDEX_HTML = (
    '<!doctype html><html lang="ko"><head><title>Asset Manager</title>'
    '<script src="/theme-init.js"></script>'
    '<script type="module" src="/assets/index-AbCd1234.js"></script>'
    '<link rel="stylesheet" href="/assets/index-Xy_Z-987.css"></head>'
    '<body><div id="root"></div></body></html>'
)
APP_JS = "console.log('app')"
SECRET_TEXT = "not for the public: outside the static folder"
NOT_FOUND = {"detail": "Not Found"}

# Test-only values; no real password or secret is ever used by the tests.
PASSWORD = "test-only passphrase 0002"
SESSION_SECRET = "test-only-session-secret-" + "1" * 32


@functools.lru_cache
def production_hash() -> str:
    """The weakest cost a production instance accepts, so the tests stay quick."""
    return hash_password(PASSWORD, n=2**14, r=8, p=1)


@pytest.fixture
def dist(tmp_path) -> Path:
    """What `vite build` leaves behind, plus a file next to it that must stay unreachable."""
    folder = tmp_path / "dist"
    (folder / "assets").mkdir(parents=True)
    (folder / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (folder / "assets" / "index-AbCd1234.js").write_text(APP_JS, encoding="utf-8")
    (folder / "assets" / "index-Xy_Z-987.css").write_text("body{margin:0}", encoding="utf-8")
    (folder / "assets" / "logo.svg").write_text("<svg/>", encoding="utf-8")  # no hash
    (folder / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (folder / "theme-init.js").write_text("try{}catch{}", encoding="utf-8")
    (folder / ".hidden").write_text(SECRET_TEXT, encoding="utf-8")
    (tmp_path / "secret.txt").write_text(SECRET_TEXT, encoding="utf-8")
    return folder


def settings(**kwargs) -> Settings:
    return Settings(_env_file=None, **kwargs)


def make_client(db, provider, config: Settings, **kwargs) -> TestClient:
    app = create_app(config)
    quote_cache = QuoteCache()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_provider] = lambda: provider
    app.dependency_overrides[get_quote_cache] = lambda: quote_cache
    scheme = "https" if config.env == "production" else "http"
    return TestClient(app, base_url=f"{scheme}://localhost", **kwargs)


@pytest.fixture
def site(db, provider, dist) -> TestClient:
    with make_client(db, provider, settings(static_dir=dist)) as c:
        yield c


def run_asgi(app, scope: dict) -> tuple[int, dict[str, str], bytes]:
    """One request straight into an ASGI app. `receive` behaves like a server: the (empty)
    request once, then it waits. A `receive` that returned at once every time would spin
    forever inside FileResponse, which listens for a disconnect while it sends the file."""
    messages: list[dict] = []

    async def call() -> None:
        request_sent = False

        async def receive() -> dict:
            nonlocal request_sent
            if request_sent:
                await asyncio.Event().wait()  # until the response is done and this is cancelled
            request_sent = True
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: dict) -> None:
            messages.append(message)

        await asyncio.wait_for(app(scope, receive, send), timeout=20)

    asyncio.run(call())
    start = messages[0]
    headers = {k.decode("latin-1"): v.decode("latin-1") for k, v in start["headers"]}
    body = b"".join(m.get("body", b"") for m in messages[1:])
    return start["status"], headers, body


def raw_request(app, path: str, method: str = "GET") -> tuple[int, dict[str, str], bytes]:
    """A request with the path exactly as written. An HTTP client would tidy `..` away
    before sending, which is the very thing to test."""
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8", "surrogatepass"),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"localhost")],
        "client": ("127.0.0.1", 50000),
        "server": ("localhost", 80),
    }
    return run_asgi(app, scope)


def is_page(res) -> bool:
    return (
        res.status_code == 200
        and res.headers["content-type"].startswith("text/html")
        and res.text == INDEX_HTML
    )


# --- without a built frontend ----------------------------------------------------------------


def test_without_static_dir_nothing_is_served_and_the_router_is_untouched(client):
    assert not isinstance(client.app.router.default, Frontend)
    assert client.app.router.default == client.app.router.not_found
    for path in ("/", "/coach", "/assets/AAA", "/index.html"):
        res = client.get(path)
        assert res.status_code == 404 and res.json() == NOT_FOUND, path


def test_a_folder_without_index_html_stops_the_server(tmp_path):
    with pytest.raises(RuntimeError, match="AM_STATIC_DIR") as raised:
        create_app(settings(static_dir=tmp_path))
    assert "index.html" in str(raised.value)


# --- files and pages --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/index.html",
        "/coach",
        "/learn/some-lesson",
        "/transactions?check=1",
        "/login?next=%2Fcoach",
        "/coach/",
        "/no/such/page",
        # The ticker page shares its prefix with Vite's assets/ folder.
        "/assets/AAA",
        "/assets/BTC-USD",
        "/assets/BRK.B",
        "/assets/KRW=X",
        "/assets/",
        "/assets",
        # Only /api and what is below it is the API.
        "/apiary",
    ],
)
def test_pages_get_index_html_and_are_revalidated(site, path):
    res = site.get(path)
    assert is_page(res), path
    assert res.headers["cache-control"] == CACHE_REVALIDATE == "no-cache"


@pytest.mark.parametrize(
    ("path", "media_type", "cache", "body"),
    [
        ("/assets/index-AbCd1234.js", "text/javascript", CACHE_HASHED, APP_JS),
        ("/assets/index-Xy_Z-987.css", "text/css", CACHE_HASHED, "body{margin:0}"),
        # Not hashed, so the same name may hold other bytes after the next build.
        ("/assets/logo.svg", "image/svg+xml", CACHE_REVALIDATE, "<svg/>"),
        ("/favicon.svg", "image/svg+xml", CACHE_REVALIDATE, "<svg/>"),
        ("/theme-init.js", "text/javascript", CACHE_REVALIDATE, "try{}catch{}"),
    ],
)
def test_files_are_sent_as_files_with_their_type_and_cache_rule(
    site, path, media_type, cache, body
):
    res = site.get(path)
    assert res.status_code == 200
    assert res.headers["content-type"].split(";")[0] == media_type
    assert res.headers["cache-control"] == cache
    assert res.text == body
    assert int(res.headers["content-length"]) == len(body.encode())


def test_hashed_files_may_be_cached_for_a_year_without_asking():
    assert CACHE_HASHED == "public, max-age=31536000, immutable"


def test_head_answers_without_a_body(site):
    for path, length in (("/", len(INDEX_HTML)), ("/assets/index-AbCd1234.js", len(APP_JS))):
        res = site.head(path)
        assert res.status_code == 200
        assert res.content == b""
        assert int(res.headers["content-length"]) == length


@pytest.mark.parametrize(
    "path",
    [
        "/assets/index-0ldBu1ld.js",  # a tab left open across a deployment asks for this
        "/assets/missing.css",
        "/assets/AAA.js",
        "/favicon.ico",
        "/robots.txt",
        "/nope.html",
        "/assets/index-AbCd1234.js.map",
        "/site.webmanifest",
    ],
)
def test_a_missing_build_file_is_a_404_not_the_page(site, path):
    res = site.get(path)
    assert res.status_code == 404, path
    assert res.json() == NOT_FOUND


# --- /api keeps its own answers ---------------------------------------------------------------


def test_unknown_api_paths_stay_json_404(site):
    for method in ("GET", "HEAD", "POST", "PUT", "DELETE"):
        for path in ("/api/nope", "/api", "/api/", "/api/nope/deeper", "/api/index.html"):
            res = site.request(method, path)
            assert res.status_code == 404, (method, path)
            assert res.headers["content-type"] == "application/json"
            if method != "HEAD":
                assert res.json() == NOT_FOUND
    # A real file name under /api is still not served from the folder.
    assert site.get("/api/assets/index-AbCd1234.js").json() == NOT_FOUND
    assert site.get("/api/theme-init.js").json() == NOT_FOUND


def test_api_routes_answer_exactly_as_without_a_frontend(site, client):
    """`client` is the same app without AM_STATIC_DIR: every answer must be identical."""
    calls = [
        ("GET", "/api/health"),
        ("GET", "/api/transactions"),
        ("PATCH", "/api/transactions"),  # 405: the path exists, the method does not
        ("DELETE", "/api/health"),
        ("GET", "/api/nope"),
        ("POST", "/api/nope"),
        ("GET", "/api/market/crypto"),
        # Not GET/HEAD and not a route: the frontend never answers a write.
        ("POST", "/coach"),
        ("PUT", "/assets/AAA"),
        ("DELETE", "/"),
        ("POST", "/assets/index-AbCd1234.js"),
    ]
    for method, path in calls:
        with_site, without = site.request(method, path), client.request(method, path)
        assert with_site.status_code == without.status_code, (method, path)
        assert with_site.content == without.content, (method, path)
        assert with_site.headers.get("allow") == without.headers.get("allow"), (method, path)
    assert site.get("/api/health").json() == {"status": "ok"}
    assert site.request("PATCH", "/api/transactions").status_code == 405


def test_docs_stay_real_routes_in_development(site):
    assert site.get("/docs").status_code == 200 and "swagger" in site.get("/docs").text.lower()
    assert "paths" in site.get("/openapi.json").json()


# --- nothing outside the folder ---------------------------------------------------------------


def traversal_paths(dist: Path) -> list[str]:
    outside = (dist.parent / "secret.txt").resolve()
    return [
        "/../secret.txt",
        "/assets/../../secret.txt",
        "/assets/../../../secret.txt",
        "/./../secret.txt",
        "//../secret.txt",
        "/..\\secret.txt",
        "/assets/..\\..\\secret.txt",
        "\\..\\secret.txt",
        "/%2e%2e/secret.txt",
        "/..%2fsecret.txt",
        # An absolute path, POSIX or Windows style: joining must not replace the folder.
        "/" + outside.as_posix(),
        "//" + outside.as_posix(),
        "/" + str(outside),
        outside.as_posix(),
        # Dot-files are never served, whatever they hold.
        "/.hidden",
        "/assets/../.hidden",
        "/.env",
        "/.git/config",
        # Things a file system refuses or special-cases.
        "/assets/index-AbCd1234.js\x00.png",
        "/\x00",
        "/" + "a" * 5000,
        "/CON",
        "/assets/NUL",
    ]


def test_nothing_outside_the_folder_can_be_read(db, provider, dist):
    client = make_client(db, provider, settings(static_dir=dist))
    frontend = client.app.router.default
    assert isinstance(frontend, Frontend)
    for path in traversal_paths(dist):
        assert frontend.file_for(path) is None, path
        status, headers, body = raw_request(client.app, path)
        assert SECRET_TEXT.encode() not in body, path
        # Either the page (a path without a build suffix) or a 404; never another file.
        assert (status, body) in ((200, INDEX_HTML.encode()), (404, b'{"detail":"Not Found"}')), (
            path
        )
    # The same lookup does find what is inside.
    assert (
        frontend.file_for("/assets/index-AbCd1234.js")
        == (dist / "assets" / "index-AbCd1234.js").resolve()
    )
    assert frontend.file_for("/favicon.svg") == (dist / "favicon.svg").resolve()
    assert frontend.file_for("/assets") is None  # a folder is not a file
    assert frontend.file_for("/") is None


def test_a_symlink_pointing_out_of_the_folder_is_not_followed(db, provider, dist):
    link = dist / "assets" / "leak-AbCd1234.txt"
    try:
        os.symlink(dist.parent / "secret.txt", link)
    except (OSError, NotImplementedError):
        pytest.skip("this account may not create symlinks")
    with make_client(db, provider, settings(static_dir=dist)) as c:
        res = c.get("/assets/leak-AbCd1234.txt")
        assert res.status_code == 404
        assert SECRET_TEXT not in res.text


def test_the_fallback_also_works_under_a_root_path(dist):
    """Mounted under a prefix, the path the router matched on decides, as in the layers."""

    async def not_found(scope, receive, send):
        raise AssertionError("the frontend should have answered")

    frontend = Frontend(dist, not_found)
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/demo/assets/index-AbCd1234.js",
        "root_path": "/demo",
        "headers": [],
        "query_string": b"",
    }
    status, headers, body = run_asgi(frontend, scope)
    assert (status, body) == (200, APP_JS.encode())
    assert headers["cache-control"] == CACHE_HASHED


def test_the_router_fallback_is_what_gets_wrapped(db, provider, dist):
    app = make_client(db, provider, settings(static_dir=dist)).app
    plain = make_client(db, provider, settings()).app
    assert isinstance(app.router, Router)
    assert isinstance(app.router.default, Frontend)
    assert app.router.default.not_found == app.router.not_found
    # No route and no mount was added for the frontend.
    assert [type(r) for r in app.router.routes] == [type(r) for r in plain.router.routes]


# --- with the access-control layers of a deployed instance -------------------------------------

SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "same-origin",
    "x-frame-options": "DENY",
    "cross-origin-opener-policy": "same-origin",
    "content-security-policy": DEFAULT_CONTENT_SECURITY_POLICY,
}


def assert_security_headers(res) -> None:
    for name, value in SECURITY_HEADERS.items():
        assert res.headers[name] == value, name
    assert res.headers["strict-transport-security"].startswith("max-age=31536000")


MODES = {
    "demo": {"demo_mode": True},
    "login": {"auth_password_hash": "production", "session_secret": SESSION_SECRET},
    "demo+login": {
        "demo_mode": True,
        "auth_password_hash": "production",
        "session_secret": SESSION_SECRET,
    },
}


@pytest.mark.parametrize("mode", sorted(MODES))
def test_pages_and_files_are_public_while_api_stays_closed(db, provider, dist, mode):
    extra = dict(MODES[mode])
    if "auth_password_hash" in extra:
        extra["auth_password_hash"] = production_hash()
    # Three /api requests a minute: exactly the three made at the end of this test.
    config = settings(env="production", rate_limit_per_minute=3, static_dir=dist, **extra)
    with make_client(db, provider, config) as c:
        # No session, no cookie, and far more requests than the limit: the login page and
        # its files must load anyway (the limit counts /api only, and never the health check).
        pages = ("/", "/index.html", "/login", "/coach", "/learn/some-lesson", "/assets/AAA")
        # Page addresses that carry a ticker the way API routes do. The demo's ticker
        # guard is for /api: here it must not answer 403 (or open a database session).
        ticker_pages = (
            "/assets/ZZZ",
            "/assets/ZZZ?symbol=ZZZ",
            "/transactions?symbol=ZZZ",
            "/?symbols=ZZZ,YYY",
        )
        for path in (*pages, *ticker_pages):
            res = c.get(path)
            assert is_page(res), (mode, path)
            assert res.headers["cache-control"] == CACHE_REVALIDATE
            assert_security_headers(res)
        for path in ("/assets/index-AbCd1234.js", "/theme-init.js", "/favicon.svg"):
            res = c.get(path)
            assert res.status_code == 200, (mode, path)
            assert res.headers["cache-control"] != "no-store"
            assert_security_headers(res)
        assert c.get("/assets/index-AbCd1234.js").headers["cache-control"] == CACHE_HASHED

        missing = c.get("/assets/index-0ldBu1ld.js")
        assert missing.status_code == 404 and missing.json() == NOT_FOUND
        assert_security_headers(missing)

        # A production instance publishes no API schema, and the frontend does not bring
        # it back: /docs is just an unknown page, /openapi.json a missing file.
        assert is_page(c.get("/docs"))
        assert c.get("/openapi.json").status_code == 404

        # /api is as closed as without a frontend.
        health = c.get("/api/health")
        assert health.status_code == 200 and health.json() == {"status": "ok"}
        api = c.get("/api/transactions")
        blocked = c.post("/api/transactions", json={})
        unknown = c.get("/api/no-such-route")
        if "login" in mode:
            assert api.status_code == 401 and api.json()["code"] == "auth_required"
            # Without a session even the existence of a route is not disclosed.
            assert unknown.status_code == 401 and unknown.json()["code"] == "auth_required"
        if "demo" in mode:
            assert blocked.status_code == 403 and blocked.json()["code"] == "demo_read_only"
        else:
            assert blocked.status_code == 401
        if mode == "demo":
            # A read, so the demo lock lets it through to the router: it must come back
            # as the API's JSON 404, not as the page with a 200.
            assert unknown.status_code == 404 and unknown.json() == NOT_FOUND
            assert unknown.headers["content-type"] == "application/json"
            assert unknown.headers["cache-control"] == "no-store"
        for res in (api, blocked, unknown):
            assert_security_headers(res)
            assert not res.headers["content-type"].startswith("text/html")


def test_the_demo_ticker_guard_still_guards_the_api_next_to_the_frontend(db, provider, dist):
    config = settings(env="production", demo_mode=True, static_dir=dist)
    with make_client(db, provider, config) as c:
        refused = c.get("/api/market/ZZZ/quote")
        assert refused.status_code == 403
        assert refused.json()["code"] == "demo_symbol_not_allowed"
        # ...while the page for the same ticker loads, and shows that answer itself.
        assert is_page(c.get("/assets/ZZZ"))
