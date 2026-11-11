import os

# The suite always runs as a plain local instance, whatever the developer's backend/.env says
# (D-035). A .env that turns on the login, production mode, the demo lock or a request limit
# would otherwise make every API test answer 401/403/429, because `create_app()` below reads
# the same settings as the server. Environment variables win over the .env file, and they
# must be in place before any `app` module is imported: `app.main` builds an app (and with it
# the settings) at import time. Tests of those features pass their own `Settings` to
# `create_app(settings=...)` instead.
os.environ.update(
    {
        "AM_ENV": "development",
        "AM_DEMO_MODE": "false",
        "AM_AUTH_PASSWORD_HASH": "",
        "AM_SESSION_SECRET": "",
        "AM_RATE_LIMIT_PER_MINUTE": "0",
        "AM_CLIENT_IP_HEADER": "",
        "AM_STATIC_DIR": "",
        # Real orders stay off in the test process even if the user has switched them on in
        # their own .env for the real app. This only ever pins the flag to off.
        "AM_LIVE_TRADING": "false",
        # The test client calls http://localhost.
        "AM_ALLOWED_HOSTS": '["localhost", "127.0.0.1", "[::1]"]',
    }
)

from collections.abc import Iterator  # noqa: E402
from datetime import date  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.data.fake_provider import FakeProvider  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db, make_engine  # noqa: E402
from app.deps import get_provider, get_quote_cache  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.market_data import QuoteCache  # noqa: E402

TODAY = date(2026, 10, 16)  # a Friday


@pytest.fixture
def db() -> Iterator[Session]:
    engine = make_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider(today=TODAY, unknown={"ZZZZ"})


@pytest.fixture
def client(db: Session, provider: FakeProvider) -> Iterator[TestClient]:
    app = create_app()
    quote_cache = QuoteCache()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_provider] = lambda: provider
    app.dependency_overrides[get_quote_cache] = lambda: quote_cache
    with TestClient(app, base_url="http://localhost") as c:
        yield c
