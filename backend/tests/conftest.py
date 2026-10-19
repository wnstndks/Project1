from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.data.fake_provider import FakeProvider
from app.db.base import Base
from app.db.session import get_db, make_engine
from app.deps import get_provider, get_quote_cache
from app.main import create_app
from app.services.market_data import QuoteCache

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
