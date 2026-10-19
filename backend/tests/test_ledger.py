from datetime import date
from decimal import Decimal as D

import pytest

from app.db.models import AssetType, Side, Transaction
from app.services.ledger import OversellError, build_positions


def tx(side, qty, price, day, fee="0", symbol="AAPL", id_=None):
    return Transaction(
        id=id_,
        asset_type=AssetType.CRYPTO if symbol.endswith("-USD") else AssetType.STOCK,
        symbol=symbol,
        side=Side(side),
        trade_date=date(2026, 1, day),
        quantity=D(qty),
        price=D(price),
        fee=D(fee),
    )


def test_moving_average_cost_includes_buy_fees():
    pos = build_positions([tx("buy", "10", "100", 1, fee="5"), tx("buy", "10", "120", 2, fee="5")])[
        "AAPL"
    ]
    assert pos.quantity == D("20")
    assert pos.cost_basis == D("2210")
    assert pos.avg_cost == D("110.5")


def test_sell_realizes_pnl_against_average_cost():
    pos = build_positions(
        [
            tx("buy", "10", "100", 1),
            tx("buy", "10", "120", 2),
            tx("sell", "5", "130", 3, fee="2"),
        ]
    )["AAPL"]
    # avg 110, sold 5 at 130 minus 2 fee -> 5*20 - 2
    assert pos.realized_pnl == D("98")
    assert pos.quantity == D("15")
    assert pos.avg_cost == D("110")


def test_full_sell_clears_cost_basis():
    pos = build_positions(
        [tx("buy", "3", "10", 1), tx("buy", "3", "20", 2), tx("sell", "6", "15", 3)]
    )["AAPL"]
    assert pos.quantity == 0
    assert pos.cost_basis == 0
    assert pos.realized_pnl == D("0")


def test_fractional_crypto_quantities_stay_exact():
    pos = build_positions(
        [
            tx("buy", "0.1", "60000", 1, symbol="BTC-USD"),
            tx("buy", "0.2", "60000", 2, symbol="BTC-USD"),
            tx("sell", "0.3", "61000", 3, symbol="BTC-USD"),
        ]
    )["BTC-USD"]
    assert pos.quantity == 0
    assert pos.realized_pnl == D("300")


def test_oversell_is_rejected():
    with pytest.raises(OversellError):
        build_positions([tx("buy", "1", "10", 1), tx("sell", "2", "10", 2)])


def test_sell_before_buy_is_rejected_even_if_total_is_enough():
    with pytest.raises(OversellError):
        build_positions([tx("sell", "1", "10", 1), tx("buy", "5", "10", 2)])


def test_same_day_round_trip_follows_entry_order():
    # Hold 10 @ 100; same day sell 10 @ 120, then buy 10 @ 130.
    pos = build_positions(
        [
            tx("buy", "10", "100", 1, id_=1),
            tx("sell", "10", "120", 2, id_=2),
            tx("buy", "10", "130", 2, id_=3),
        ]
    )["AAPL"]
    assert pos.realized_pnl == D("200")
    assert pos.avg_cost == D("130")


def test_seq_overrides_entry_order_within_a_day():
    sell = tx("sell", "1", "12", 1, id_=1)
    buy = tx("buy", "1", "10", 1, id_=2)
    sell.seq, buy.seq = 1, 0
    pos = build_positions([sell, buy])["AAPL"]
    assert pos.realized_pnl == D("2")


def test_sell_entered_before_its_same_day_buy_is_an_oversell():
    with pytest.raises(OversellError):
        build_positions([tx("sell", "1", "12", 1, id_=1), tx("buy", "1", "10", 1, id_=2)])


def test_flat_position_can_restart_in_another_currency():
    from app.db.models import Currency

    usd_buy = tx("buy", "1", "60000", 1, symbol="BTC-USD", id_=1)
    usd_sell = tx("sell", "1", "61000", 2, symbol="BTC-USD", id_=2)
    krw_buy = tx("buy", "1", "80000000", 3, symbol="BTC-USD", id_=3)
    for t in (usd_buy, usd_sell):
        t.currency = Currency.USD
    krw_buy.currency = Currency.KRW
    pos = build_positions([usd_buy, usd_sell, krw_buy])["BTC-USD"]
    assert pos.currency == Currency.KRW and pos.quantity == D("1")


def test_krw_cost_uses_trade_date_rates():
    rates = {1: D("1300"), 2: D("1400"), 3: D("1500")}
    pos = build_positions(
        [tx("buy", "10", "100", 1), tx("buy", "10", "100", 2), tx("sell", "10", "110", 3)],
        fx_on=lambda d: rates[d.day],
    )["AAPL"]
    # bought 1000 USD at 1300 and 1000 USD at 1400 -> 2,700,000 KRW; sold half the shares
    assert pos.cost_basis_krw == D("1350000")
    assert pos.avg_cost_krw == D("135000")
    # proceeds 1100 USD at 1500 = 1,650,000 KRW minus released cost 1,350,000
    assert pos.realized_pnl_krw == D("300000")
    assert pos.realized_pnl == D("100")


def test_as_of_ignores_later_trades():
    positions = build_positions(
        [tx("buy", "1", "10", 1), tx("buy", "1", "10", 5)], as_of=date(2026, 1, 3)
    )
    assert positions["AAPL"].quantity == D("1")
