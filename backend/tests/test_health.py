from datetime import date
from decimal import Decimal

from app.db.models import AssetType, Side, Transaction


def test_untrusted_host_is_rejected(client):
    # A DNS-rebinding page would send its own hostname.
    assert client.get("/api/health", headers={"host": "evil.example"}).status_code == 400
    assert client.get("/api/health", headers={"host": "localhost:8000"}).status_code == 200


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_decimal_text_round_trips_exactly(db):
    tx = Transaction(
        asset_type=AssetType.CRYPTO,
        symbol="BTC-USD",
        side=Side.BUY,
        trade_date=date(2026, 1, 2),
        quantity=Decimal("0.12345678"),
        price=Decimal("64250.10"),
    )
    db.add(tx)
    db.commit()
    db.expire_all()

    loaded = db.get(Transaction, tx.id)
    assert loaded.quantity == Decimal("0.12345678")
    assert loaded.price == Decimal("64250.10")
    assert loaded.fee == Decimal("0")
