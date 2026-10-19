"""Load a fictional demo portfolio for screenshots and public demos.

Trade prices are taken from the market data provider's close on each trade date,
so the demo looks realistic with yfinance and also works offline with AM_MARKET_PROVIDER=fake.

    py -m uv run python -m seed.load            # refuses if transactions already exist
    py -m uv run python -m seed.load --reset    # deletes ALL transactions first

Keep demo data out of your real database by pointing at a separate file, e.g.
    $env:AM_DATABASE_URL = "sqlite:///demo.db"
"""

import argparse
import sys
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import delete, func, select

from app.config import Settings, get_settings
from app.db.models import AssetType, Side, Transaction
from app.db.session import SessionLocal
from app.deps import get_provider, get_quote_cache
from app.schemas.transactions import TransactionIn
from app.services.market_data import MarketDataService
from app.services.transactions import TransactionService

BACKEND_DIR = Path(__file__).resolve().parent.parent

S, C = AssetType.STOCK, AssetType.CRYPTO
B, X = Side.BUY, Side.SELL

# (asset_type, symbol, side, days_ago, quantity)
DEMO_TRADES = [
    (S, "AAPL", B, 700, "15"),
    (S, "MSFT", B, 650, "8"),
    (S, "VOO", B, 600, "6"),
    (C, "ETH-USD", B, 550, "0.8"),
    (S, "NVDA", B, 500, "20"),
    (C, "XRP-USD", B, 450, "1500"),
    (S, "AAPL", B, 400, "5"),
    (C, "SOL-USD", B, 380, "12"),
    (S, "TSLA", B, 350, "5"),
    (C, "BTC-USD", B, 680, "0.05"),
    (C, "BTC-USD", B, 300, "0.03"),
    (S, "VOO", B, 300, "4"),
    (S, "NVDA", X, 200, "10"),
    (S, "AAPL", X, 120, "5"),
    (C, "SOL-USD", X, 90, "4"),
    (S, "VOO", B, 60, "3"),
]
CRYPTO_FEE_RATE = Decimal("0.001")


def _close_on(market: MarketDataService, symbol: str, day: date) -> Decimal:
    bars = market.get_history(symbol, day - timedelta(days=7), day)
    if not bars:
        raise SystemExit(f"No price data for {symbol} around {day}")
    places = Decimal("0.0001") if bars[-1].close < 10 else Decimal("0.01")
    return Decimal(str(bars[-1].close)).quantize(places, ROUND_HALF_UP)


def _sqlite_path(url: str) -> Path | None:
    """Resolved file behind a sqlite URL, so "./asset_manager.db" and the absolute default match."""
    prefix = "sqlite:///"
    return Path(url[len(prefix) :]).resolve() if url.startswith(prefix) else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reset", action="store_true", help="delete all transactions first")
    args = parser.parse_args()

    url = get_settings().database_url
    print(f"Database: {url}")
    if args.reset and _sqlite_path(url) == _sqlite_path(
        Settings.model_fields["database_url"].default
    ):
        sys.exit(
            "Refusing --reset on the default database, which may hold real holdings.\n"
            'Point AM_DATABASE_URL at a demo file first, e.g. AM_DATABASE_URL="sqlite:///demo.db"'
        )
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")

    with SessionLocal() as db:
        existing = db.scalar(select(func.count()).select_from(Transaction))
        if existing and not args.reset:
            sys.exit(f"{existing} transactions already exist. Use --reset to replace them.")

        market = MarketDataService(db, get_provider(), get_quote_cache())
        # Look up every price first: if the network fails, nothing has been deleted yet.
        today = date.today()
        items = []
        for asset_type, symbol, side, days_ago, qty in sorted(DEMO_TRADES, key=lambda t: -t[3]):
            day = today - timedelta(days=days_ago)
            price = _close_on(market, symbol, day)
            quantity = Decimal(qty)
            fee = Decimal("0")
            if asset_type == C:
                fee = (quantity * price * CRYPTO_FEE_RATE).quantize(Decimal("0.01"))
            items.append(
                TransactionIn(
                    asset_type=asset_type,
                    symbol=symbol,
                    side=side,
                    trade_date=day,
                    quantity=quantity,
                    price=price,
                    fee=fee,
                    note="demo",
                )
            )
            print(f"  {day} {side.value:<4} {qty:>6} {symbol:<8} @ {price}")

        # Delete and insert in one transaction (create_many commits once at the end).
        if args.reset:
            db.execute(delete(Transaction))
        TransactionService(db, market).create_many(items)

    print(f"Loaded {len(DEMO_TRADES)} demo transactions.")


if __name__ == "__main__":
    main()
