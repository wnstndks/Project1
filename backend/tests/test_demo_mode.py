"""The read-only public demo (DECISIONS.md D-035, AM_DEMO_MODE).

Closed by default twice over: every write route under /api answers 403 unless it is on the
reviewed allow list, and ticker routes only answer for the demo's own symbols. Both tests walk
the routes FastAPI actually serves, so a route added later is covered without touching this
file, and an unclassified one fails here until someone reviews it. Symbols are synthetic.
"""

import functools
import os
import re
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import APIRouter, WebSocket
from fastapi.routing import APIRoute, iter_route_contexts
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker
from starlette.websockets import WebSocketDisconnect

from app.config import Settings, get_settings
from app.db.models import (
    AssetType,
    KillSwitchEvent,
    LessonProgress,
    PolicySettingsRow,
    PriceBar,
    RuleSettingsRow,
    Side,
    Transaction,
)
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
from app.security.demo import (
    DEMO_WRITE_ALLOWLIST,
    INTERNAL_SYMBOLS,
    SAFE_METHODS,
    SYMBOL_PARAMS,
    allowed_symbols,
    canonical,
    demo_symbol_guard,
)
from app.security.passwords import hash_password
from app.services.market_data import QuoteCache

PASSWORD = "test-only passphrase 0001"
SECRET = "test-only-session-secret-" + "0" * 32
READ_ONLY = {"detail": "데모에서는 저장·수정할 수 없어요", "code": "demo_read_only"}
NOT_ALLOWED = {
    "detail": "데모에서는 데모 장부에 있는 종목만 볼 수 있어요",
    "code": "demo_symbol_not_allowed",
}
HELD = "AAA"  # in the demo ledger
OUTSIDE = "BBB"  # a valid ticker the provider would serve, but not in the demo
TRADE = {
    "asset_type": "stock",
    "symbol": HELD,
    "side": "buy",
    "trade_date": "2026-10-01",
    "quantity": 1,
    "price": 100,
}

# Every non-read route, reviewed one by one (2026-11-10). "allowed" must match
# app/security/demo.py::DEMO_WRITE_ALLOWLIST; everything else answers 403 in the demo.
ALLOWED, BLOCKED = "allowed", "blocked"
REVIEWED_WRITES = {
    # Compute only: Monte Carlo over cached bars of the demo's own holdings, nothing stored.
    ("POST", "/api/projection/simulate"): ALLOWED,
    # No data behind them (login answers 409 on a demo without a login; logout clears a cookie).
    ("POST", "/api/auth/login"): ALLOWED,
    ("POST", "/api/auth/logout"): ALLOWED,
    # Ledger writes.
    ("POST", "/api/transactions"): BLOCKED,
    ("PUT", "/api/transactions/{tx_id}"): BLOCKED,
    ("POST", "/api/transactions/convert-currency"): BLOCKED,
    ("DELETE", "/api/transactions"): BLOCKED,
    ("DELETE", "/api/transactions/{tx_id}"): BLOCKED,
    # Import: the screenshot preview calls an LLM, the manual preview quotes arbitrary
    # tickers at the provider, commit writes the ledger.
    ("POST", "/api/imports/screenshot"): BLOCKED,
    ("POST", "/api/imports/manual"): BLOCKED,
    ("POST", "/api/imports/commit"): BLOCKED,
    # Dividend / split state changes the ledger.
    ("POST", "/api/corporate-actions/dividends/confirm-all"): BLOCKED,
    ("POST", "/api/corporate-actions/withholding"): BLOCKED,
    ("POST", "/api/corporate-actions/{action_id}/confirm"): BLOCKED,
    ("POST", "/api/corporate-actions/{action_id}/ignore"): BLOCKED,
    # Sync triggers: outbound requests on demand.
    ("POST", "/api/gurus/sync"): BLOCKED,
    ("POST", "/api/congress/sync"): BLOCKED,
    # Model training: minutes of CPU and artifacts on disk.
    ("POST", "/api/forecasts/train"): BLOCKED,
    ("POST", "/api/predictions/{symbol}/train"): BLOCKED,
    # Saved settings and state.
    ("PUT", "/api/rules/settings"): BLOCKED,
    ("POST", "/api/rules/kill-switch/reset"): BLOCKED,
    ("PUT", "/api/coach/policy"): BLOCKED,
    ("PUT", "/api/learn/progress/{lesson_id}"): BLOCKED,
}

# Read routes that take a ticker, reviewed the same way: all of them go through the guard.
REVIEWED_SYMBOL_READS = {
    "/api/market/{symbol}/history",
    "/api/market/{symbol}/quote",
    "/api/market/{symbol}/info",
    "/api/transactions",
    "/api/portfolio/benchmark",
    "/api/predictions/{symbol}",
    "/api/predictions/{symbol}/backtest",
    "/api/predictions/{symbol}/train",
    "/api/news/{symbol}",
    "/api/forecasts/track-record",
    "/api/forecasts/{symbol}",
    "/api/forecasts/{symbol}/backtest",
    "/api/congress/trades",
}
# Every other path or query parameter of a read route, each checked not to carry a ticker.
# A new name fails test_every_read_parameter_is_reviewed until it is added here or to
# SYMBOL_PARAMS.
REVIEWED_OTHER_PARAMS = {
    "action_id",
    "asset_type",
    "confirm",
    "days",
    "end",
    "guru_id",
    "horizon",
    "lesson_id",
    "month",
    "start",
    "top",
    "tx_id",
}


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


@pytest.fixture
def ledger(db):
    """A small demo ledger: one stock and one coin."""
    rows = [
        (AssetType.STOCK, HELD, Decimal("10"), Decimal("100")),
        (AssetType.CRYPTO, "ETH-USD", Decimal("0.5"), Decimal("3000")),
    ]
    for asset_type, symbol, quantity, price in rows:
        db.add(
            Transaction(
                asset_type=asset_type,
                symbol=symbol,
                side=Side.BUY,
                trade_date=date(2026, 10, 1),
                quantity=quantity,
                price=price,
            )
        )
    db.commit()
    return db


@pytest.fixture
def demo(db, provider, ledger):
    with make_client(db, provider, settings(demo_mode=True)) as c:
        yield c


def routes(app) -> list[tuple[str, str, set[str]]]:
    """(method, path template, parameter names) of every route FastAPI serves."""
    out = []
    for ctx in iter_route_contexts(app.routes):
        if not isinstance(ctx.original_route, APIRoute):
            continue
        names: set[str] = set()
        pending = [ctx.dependant]
        while pending:
            dependant = pending.pop()
            names.update(p.alias for p in [*dependant.path_params, *dependant.query_params])
            pending.extend(dependant.dependencies)
        out += [(method, ctx.path, names) for method in sorted(ctx.methods or [])]
    return out


def write_routes(app) -> set[tuple[str, str]]:
    return {(m, p) for m, p, _ in routes(app) if m not in SAFE_METHODS}


def concrete(path: str, symbol: str = HELD) -> str:
    return re.sub(r"\{(\w+)[^}]*\}", lambda m: symbol if m.group(1) == "symbol" else "1", path)


def count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


# --- writes --------------------------------------------------------------------------------


def test_every_write_route_is_classified(demo):
    """A write route added later fails here until someone reviews it (and is blocked
    meanwhile: see test_a_new_write_route_is_blocked_until_listed)."""
    served = write_routes(demo.app)
    assert len(served) >= 23
    assert served == set(REVIEWED_WRITES), served ^ set(REVIEWED_WRITES)


def test_allow_list_is_exactly_the_reviewed_one(demo):
    allowed = {route for route, verdict in REVIEWED_WRITES.items() if verdict == ALLOWED}
    assert allowed == DEMO_WRITE_ALLOWLIST
    for method, path in DEMO_WRITE_ALLOWLIST:
        assert method == "POST" and "{" not in path  # exact paths only, no patterns
        assert (method, path) in write_routes(demo.app)  # no stale entry


def test_every_write_route_is_allow_listed_or_answers_403(demo, db, provider):
    before = {m: count(db, m) for m in (Transaction, RuleSettingsRow, PolicySettingsRow)}
    blocked = 0
    for method, path in sorted(write_routes(demo.app)):
        if (method, path) in DEMO_WRITE_ALLOWLIST:
            continue
        res = demo.request(method, concrete(path), json=TRADE)
        assert res.status_code == 403, (method, path)
        assert res.json() == READ_ONLY, (method, path)
        blocked += 1
    assert blocked == len(REVIEWED_WRITES) - len(DEMO_WRITE_ALLOWLIST) == 20
    # Nothing ran: no row written, no state changed, the provider never asked.
    assert {m: count(db, m) for m in before} == before
    assert count(db, KillSwitchEvent) == 0 and count(db, LessonProgress) == 0
    assert provider.history_calls == []


def test_blocked_writes_are_refused_before_their_body_is_read(demo, db):
    # Valid bodies that would succeed outside the demo.
    assert demo.post("/api/transactions", json=TRADE).json() == READ_ONLY
    assert demo.delete("/api/transactions", params={"confirm": "all"}).json() == READ_ONLY
    assert demo.put("/api/learn/progress/x", json={"read": True}).json() == READ_ONLY
    files = {"files": ("a.png", b"\x89PNG\r\n\x1a\n", "image/png")}
    assert demo.post("/api/imports/screenshot", files=files).json() == READ_ONLY
    assert count(db, Transaction) == 2  # the seeded ledger, untouched


def test_a_new_write_route_is_blocked_until_listed(db, provider, ledger):
    client = make_client(db, provider, settings(demo_mode=True))
    called = []
    extra = APIRouter(prefix="/api/extra")

    @extra.post("/thing")
    @extra.put("/thing/{thing_id}")
    @extra.patch("/thing/{thing_id}")
    @extra.delete("/thing/{thing_id}")
    def new_write(thing_id: int = 0):
        called.append(thing_id)
        return {"written": True}

    @client.app.post("/api/brand-new")
    def brand_new():
        called.append("brand-new")
        return {"written": True}

    @client.app.get("/api/extra/thing")
    def new_read():
        return {"read": True}

    client.app.include_router(extra)
    with client as c:
        assert ("POST", "/api/brand-new") in write_routes(c.app)
        for method, path in (
            ("POST", "/api/brand-new"),
            ("POST", "/api/extra/thing"),
            ("PUT", "/api/extra/thing/1"),
            ("PATCH", "/api/extra/thing/1"),
            ("DELETE", "/api/extra/thing/1"),
        ):
            res = c.request(method, path)
            assert res.status_code == 403 and res.json() == READ_ONLY, (method, path)
        assert called == []
        assert c.get("/api/extra/thing").json() == {"read": True}  # reads are unaffected


def test_any_other_method_or_path_under_api_is_closed(demo):
    for method, path in (
        ("PATCH", "/api/transactions/1"),
        ("TRACE", "/api/transactions"),
        ("POST", "/api"),
        ("POST", "/api/"),
        ("POST", "/api/nothing-here"),
        ("POST", "/api/projection/simulate/"),  # not the listed path
        ("POST", "/api/projection/simulate/extra"),
        ("PUT", "/api/projection/simulate"),  # listed for POST only
        ("POST", "/%61pi/transactions"),  # reaches the router as /api/transactions
    ):
        res = demo.request(method, path)
        assert res.status_code == 403 and res.json() == READ_ONLY, (method, path)
    # Outside /api the demo lock does not apply (static files); the router answers.
    assert demo.post("/somewhere-else").status_code == 404


def test_the_compute_only_route_works_and_stores_nothing(demo, db):
    res = demo.post("/api/projection/simulate", json={"years": 2, "simulations": 500})
    assert res.status_code == 200
    assert len(res.json()["years"]) == 3
    assert count(db, Transaction) == 2
    # It read bars for the demo's own holdings only.
    cached = set(db.scalars(select(PriceBar.symbol).distinct()))
    assert cached and cached <= allowed_symbols(db, settings().benchmarks)


def test_reads_work_and_the_session_says_demo(demo):
    assert demo.get("/api/auth/session").json() == {
        "auth_required": False,
        "authenticated": False,
        "demo_mode": True,
    }
    assert demo.get("/api/health").json() == {"status": "ok"}
    assert len(demo.get("/api/transactions").json()) == 2
    assert {h["symbol"] for h in demo.get("/api/portfolio/holdings").json()} == {HELD, "ETH-USD"}
    assert demo.options("/api/transactions").status_code == 405  # safe method: the router's answer


def test_login_is_not_offered_on_a_demo_without_one(demo):
    res = demo.post("/api/auth/login", json={"password": PASSWORD})
    assert res.status_code == 409
    assert res.json()["code"] == "login_not_configured"
    assert "set-cookie" not in res.headers
    assert demo.post("/api/auth/logout").status_code == 204


def test_websockets_under_api_are_closed_in_the_demo(db, provider, ledger):
    client = make_client(db, provider, settings(demo_mode=True))

    @client.app.websocket("/api/live")
    async def live(ws: WebSocket):
        await ws.accept()

    with (
        client as c,
        pytest.raises(WebSocketDisconnect) as refused,
        c.websocket_connect("ws://localhost/api/live"),
    ):
        pass
    assert refused.value.code == 1008


def test_outside_the_demo_nothing_is_blocked(client):
    assert client.post("/api/transactions", json=TRADE).status_code == 201
    assert client.get(f"/api/market/{OUTSIDE}/quote").status_code == 200


# --- tickers -------------------------------------------------------------------------------


def symbol_reads(app) -> dict[str, set[str]]:
    return {
        path: names & set(SYMBOL_PARAMS)
        for method, path, names in routes(app)
        if method == "GET" and names & set(SYMBOL_PARAMS)
    }


def test_every_read_parameter_is_reviewed(demo):
    """The guard recognizes tickers by parameter name, so a new name must be looked at."""
    names = set().union(*(n for m, _, n in routes(demo.app) if m == "GET"))
    unreviewed = names - set(SYMBOL_PARAMS) - REVIEWED_OTHER_PARAMS
    assert not unreviewed, f"classify these parameters: {sorted(unreviewed)}"
    assert set(symbol_reads(demo.app)) == REVIEWED_SYMBOL_READS


def test_the_guard_sits_on_every_route_in_demo_mode_only(demo, client):
    def guarded(app) -> list[bool]:
        return [
            any(d.call is demo_symbol_guard for d in ctx.dependant.dependencies)
            for ctx in iter_route_contexts(app.routes)
            if isinstance(ctx.original_route, APIRoute)
        ]

    assert len(guarded(demo.app)) >= 60 and all(guarded(demo.app))
    assert not any(guarded(client.app))


def test_ticker_routes_refuse_symbols_outside_the_demo(demo, db, provider):
    quoted = []
    original = provider.get_quote
    provider.get_quote = lambda symbol: (quoted.append(symbol), original(symbol))[1]

    checked = 0
    for path, params in sorted(symbol_reads(demo.app).items()):
        for name in sorted(params):
            if "{symbol}" in path:
                res = demo.get(concrete(path, OUTSIDE))
            else:
                res = demo.get(path, params={name: OUTSIDE})
            assert res.status_code == 403, (path, name)
            assert res.json() == NOT_ALLOWED, (path, name)
            checked += 1
    assert checked == len(REVIEWED_SYMBOL_READS) == 13
    # Refused before any dependency reached the provider or the cache.
    assert provider.history_calls == [] and quoted == []
    assert count(db, PriceBar) == 0


@pytest.mark.parametrize(
    "symbol",
    [HELD, "aaa", " AAA ", "ETH-USD", "eth", "KRW-ETH", "BTC-USD", "btc", "KRW-BTC", "SPY", "QQQ"],
)
def test_demo_symbols_benchmarks_and_proxies_are_served(demo, symbol):
    res = demo.get(f"/api/market/{symbol}/quote")
    assert res.status_code == 200, symbol
    assert res.json()["symbol"] == canonical(symbol)


@pytest.mark.parametrize(
    "symbol",
    [OUTSIDE, "bbb", "AAAA", "AAA.B", "DOGE-USD", "KRW-DOGE", "^GSPC", "KRW=X2", "A" * 30, "%20"],
)
def test_other_symbols_are_refused_whatever_their_spelling(demo, symbol):
    res = demo.get(f"/api/market/{symbol}/history")
    assert res.status_code == 403 and res.json() == NOT_ALLOWED, symbol


def test_symbol_lists_are_checked_item_by_item(demo):
    ok = demo.get("/api/portfolio/benchmark", params={"symbols": f"{HELD},SPY"})
    assert ok.status_code == 200
    assert demo.get("/api/portfolio/benchmark").status_code == 200  # the default list
    for symbols in (f"{HELD},{OUTSIDE}", f"{OUTSIDE},{HELD}", f"SPY, {OUTSIDE} ,QQQ"):
        res = demo.get("/api/portfolio/benchmark", params={"symbols": symbols})
        assert res.status_code == 403 and res.json() == NOT_ALLOWED, symbols
    # A repeated parameter cannot hide one behind the other.
    res = demo.get(f"/api/transactions?symbol={HELD}&symbol={OUTSIDE}")
    assert res.status_code == 403
    assert demo.get(f"/api/transactions?symbol={HELD}").status_code == 200
    assert demo.get("/api/transactions").status_code == 200


def test_allowed_symbols_are_the_ledger_the_benchmarks_and_the_proxies(ledger):
    allowed = allowed_symbols(ledger, "ARKK, brk-b")
    assert allowed == INTERNAL_SYMBOLS | {HELD, "ETH-USD", "KRW-ETH", "ARKK", "BRK-B"}
    assert {"SPY", "KRW=X", "BTC-USD", "KRW-BTC", "SOL-USD", "KRW-SOL"} <= INTERNAL_SYMBOLS
    assert OUTSIDE not in allowed
    # A sold-out position stays viewable: the ledger still shows its history.
    assert allowed_symbols(ledger, "") == INTERNAL_SYMBOLS | {HELD, "ETH-USD", "KRW-ETH"}


def test_configured_benchmarks_widen_the_demo(db, provider, ledger):
    with make_client(db, provider, settings(demo_mode=True, benchmarks=f"SPY,{OUTSIDE}")) as c:
        assert c.get(f"/api/market/{OUTSIDE}/quote").status_code == 200
        assert c.get("/api/market/QQQ/quote").status_code == 403  # no longer listed


# --- together with the other layers ----------------------------------------------------------


@functools.lru_cache
def cheap_hash() -> str:
    return hash_password(PASSWORD, n=2**4, r=1, p=1)


def test_demo_with_a_login_applies_both_locks(db, provider, ledger):
    config = settings(demo_mode=True, auth_password_hash=cheap_hash(), session_secret=SECRET)
    with make_client(db, provider, config) as c:
        assert c.get("/api/auth/session").json() == {
            "auth_required": True,
            "authenticated": False,
            "demo_mode": True,
        }
        assert c.get("/api/transactions").status_code == 401
        assert c.post("/api/transactions", json=TRADE).json() == READ_ONLY  # outer layer first
        assert c.post("/api/projection/simulate", json={}).status_code == 401
        assert c.post("/api/auth/login", json={"password": PASSWORD}).status_code == 204
        assert c.get("/api/transactions").status_code == 200
        assert c.post("/api/transactions", json=TRADE).json() == READ_ONLY  # still read-only
        assert c.get(f"/api/market/{OUTSIDE}/quote").json() == NOT_ALLOWED
        assert c.post("/api/projection/simulate", json={"simulations": 500}).status_code == 200


def test_demo_request_limit(db, provider, ledger):
    config = settings(env="production", demo_mode=True, rate_limit_per_minute=3)
    with make_client(db, provider, config, https=True) as c:
        codes = [c.get("/api/transactions").status_code for _ in range(4)]
        assert codes == [200, 200, 200, 429]
        # Refused writes and refused tickers are counted like any other request.
        assert c.post("/api/transactions", json=TRADE).status_code == 429
        assert c.get("/api/health").status_code == 200
