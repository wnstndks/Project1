import threading
from datetime import date

from sqlalchemy.orm import sessionmaker

from app.data.fake_provider import FakeProvider
from app.db.base import Base
from app.db.session import make_engine
from app.services.market_data import MarketDataService, QuoteCache
from tests.conftest import TODAY


class BarrierProvider(FakeProvider):
    """Both threads finish fetching before either writes: the worst-case interleaving."""

    def __init__(self, barrier: threading.Barrier) -> None:
        super().__init__(today=TODAY)
        self.barrier = barrier

    def get_history(self, symbol, start, end):
        bars = super().get_history(symbol, start, end)
        self.barrier.wait(timeout=10)
        return bars


def test_concurrent_first_sync_of_a_symbol_does_not_collide(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'race.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    provider = BarrierProvider(threading.Barrier(2))
    errors: list[Exception] = []

    def worker() -> None:
        with Session() as db:
            try:
                MarketDataService(db, provider, QuoteCache()).get_history("KRW=X", date(2026, 9, 1))
            except Exception as exc:  # pragma: no cover - the assertion reports it
                errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    engine.dispose()
    assert errors == []
