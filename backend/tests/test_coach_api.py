"""The portfolio coach over HTTP (DECISIONS.md D-033): policy store, kill switch reset,
diagnosis, rebalancing, habit patterns and the monthly review.

Demo numbers only. FakeProvider supplies quotes and deterministic bars from 2015; every
coach-side clock is pinned to the provider's `today` so windows, months and staleness do not
depend on the wall clock. The artifacts directory is empty so no forecast model is involved.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import KillSwitchEvent, PolicySettingsRow
from app.db.session import get_db
from app.deps import get_artifacts_dir, get_coach_service, get_market_service
from app.services.benchmarks import BenchmarkService
from app.services.coach import BENCHMARK_CAVEAT_KO, FLAGS_OUTSIDE_WINDOW_KO, CoachService
from app.services.market_data import MarketDataService
from app.services.portfolio import PortfolioService
from app.services.rules import RuleService
from app.strategy.coach import NO_CASH_NOTE_KO, PAST_CAVEAT_KO, REBALANCE_HEADLINE_KO
from app.strategy.execution import KillSwitch

from .conftest import TODAY
from .test_portfolio_api import buy, krw_trade

NEXT_YEAR = (TODAY + timedelta(days=365)).isoformat()
DAY = TODAY.isoformat()


@pytest.fixture(autouse=True)
def _fixed_clock(client, tmp_path):
    """No forecast model, and the coach's services on the provider's `today`."""
    client.app.dependency_overrides[get_artifacts_dir] = lambda: tmp_path

    def coach(
        db: Session = Depends(get_db), market: MarketDataService = Depends(get_market_service)
    ) -> CoachService:
        settings = get_settings()
        clock = lambda: TODAY  # noqa: E731
        portfolio = PortfolioService(db, market, today=clock)
        rules = RuleService(db, market, portfolio, settings, forecasts=None, today=clock)
        benchmarks = BenchmarkService(db, market, portfolio, today=clock)
        return CoachService(db, market, portfolio, rules, benchmarks, settings, today=clock)

    client.app.dependency_overrides[get_coach_service] = coach


def policy_body(client, **over):
    """The current policy turned back into a PUT body, numbers as strings the way the screen
    sends them. `cash` is left out (None) unless the test sets it."""
    current = client.get("/api/coach/policy").json()["policy"]
    policy = {k: (str(v) if isinstance(v, int | float) else v) for k, v in current.items()}
    policy.update(over)
    return {"policy": policy, "cash": None}


def put_policy(client, cash=None, **over):
    body = policy_body(client, **over)
    body["cash"] = cash
    res = client.put("/api/coach/policy", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def pct(ratio) -> float:
    return float(Decimal(str(ratio)) * 100)


def seed_mixed(client):
    """Two dollar stocks and one coin held in won, all bought on one day."""
    assert buy(client, "AAPL", 10, 100).status_code == 201
    assert buy(client, "MSFT", 5, 200).status_code == 201
    assert krw_trade(client, "BTC", "0.01", "80000000").status_code == 201


def close_on(provider, symbol, day):
    """The provider's close of `symbol` on `day` (an ISO string), to price a test trade
    relative to it."""
    d = date.fromisoformat(day)
    [bar] = provider.get_history(symbol, d, d)
    return bar.close


# --- policy -----------------------------------------------------------------------------------


def test_get_without_a_row_answers_the_settings_defaults(client):
    s = get_settings()
    body = client.get("/api/coach/policy").json()
    assert body["policy_set"] is False and body["updated_at"] is None
    p = body["policy"]
    assert p["max_position_weight_pct"] == pct(s.risk_max_position_weight)
    assert p["drawdown_tolerance_pct"] == pct(s.risk_max_drawdown)
    assert p["target_stock_pct"] == pct(s.strategy_budget_stock)
    assert p["target_crypto_pct"] == min(
        pct(s.strategy_budget_crypto), float(s.coach_max_crypto_weight_pct)
    )
    assert p["target_cash_pct"] == pytest.approx(
        100 - p["target_stock_pct"] - p["target_crypto_pct"]
    )
    assert p["max_crypto_weight_pct"] == float(s.coach_max_crypto_weight_pct)
    assert p["max_total_risk_pct"] == float(s.coach_max_total_risk_pct)
    assert p["rebalance_band_pt"] == float(s.rules_target_weight_gap_pt)
    assert p["goal_krw"] is None and p["goal_date"] is None
    assert p["monthly_contribution_krw"] == 0
    assert body["defaults"] == p
    assert body["cash"] is None and body["cash_stale"] is False


def test_put_parses_strings_stores_them_exactly_and_marks_the_policy_set(client, db):
    out = put_policy(
        client,
        cash={"krw": "1500000", "usd": "200.5", "as_of": DAY},
        goal_krw="10000000",
        goal_date=NEXT_YEAR,
        monthly_contribution_krw="300000",
        drawdown_tolerance_pct="15",
        max_position_weight_pct="12.5",
        target_stock_pct="60",
        target_crypto_pct="20",
        target_cash_pct="20",
    )
    assert out["policy_set"] is True and out["updated_at"] is not None
    assert out["policy"]["goal_krw"] == 10_000_000 and out["policy"]["goal_date"] == NEXT_YEAR
    assert out["policy"]["drawdown_tolerance_pct"] == 15
    assert out["policy"]["max_position_weight_pct"] == 12.5
    assert out["cash"] == {"krw": 1_500_000, "usd": 200.5, "as_of": DAY}
    assert out["cash_stale"] is False
    # Exact strings in the row, like the ledger; no floats.
    row = db.get(PolicySettingsRow, 1)
    assert row.policy_json["goal_krw"] == "10000000"
    assert row.policy_json["max_position_weight_pct"] == "12.5"
    assert row.cash_json == {"krw": "1500000", "usd": "200.5", "as_of": DAY}
    # Stored, not just echoed; the defaults are untouched by what the user saved.
    again = client.get("/api/coach/policy").json()
    assert again["policy"] == out["policy"] and again["cash"] == out["cash"]
    assert again["defaults"]["target_stock_pct"] == pct(get_settings().strategy_budget_stock)


def test_put_with_null_cash_clears_the_cash_record(client):
    put_policy(client, cash={"krw": "100", "usd": "0", "as_of": DAY})
    assert client.get("/api/coach/policy").json()["cash"] is not None
    put_policy(client)
    assert client.get("/api/coach/policy").json()["cash"] is None


@pytest.mark.parametrize(
    "over",
    [
        # Asset-class targets must add up to 100.
        {"target_stock_pct": "80", "target_crypto_pct": "20", "target_cash_pct": "10"},
        # Crypto target above the crypto cap.
        {
            "target_stock_pct": "60",
            "target_crypto_pct": "40",
            "target_cash_pct": "0",
            "max_crypto_weight_pct": "30",
        },
        # A goal in the past, and a zero goal (the engine wants a positive one).
        {"goal_krw": "1000000", "goal_date": "2000-01-01"},
        {"goal_krw": "0", "goal_date": NEXT_YEAR},
        # Schema and engine ranges.
        {"drawdown_tolerance_pct": "0"},
        {"max_position_weight_pct": "150"},
        {"max_position_weight_pct": "100"},
        {"monthly_contribution_krw": "-1"},
        {"rebalance_band_pt": "abc"},
    ],
)
def test_put_rejects_an_invalid_policy(client, over):
    res = client.put("/api/coach/policy", json=policy_body(client, **over))
    assert res.status_code == 422, res.text
    # Nothing was stored.
    assert client.get("/api/coach/policy").json()["policy_set"] is False


def test_put_names_the_sum_in_korean(client):
    res = client.put(
        "/api/coach/policy",
        json=policy_body(
            client, target_stock_pct="50", target_crypto_pct="20", target_cash_pct="20"
        ),
    )
    assert res.status_code == 422
    assert "합이 100" in res.json()["detail"] and "90%" in res.json()["detail"]
    assert res.json()["code"] == "invalid_policy"


@pytest.mark.parametrize(
    "cash",
    [
        {"krw": "-1", "usd": "0", "as_of": "2026-10-01"},
        {"krw": "0", "usd": "-0.5", "as_of": "2026-10-01"},
        {"krw": "0", "usd": "0"},  # no date
        {"krw": "0", "usd": "0", "as_of": (TODAY + timedelta(days=1)).isoformat()},
    ],
)
def test_put_rejects_an_invalid_cash_record(client, cash):
    body = policy_body(client)
    body["cash"] = cash
    assert client.put("/api/coach/policy", json=body).status_code == 422


def test_cash_older_than_thirty_days_is_stale(client):
    cash = {"krw": "500000", "usd": "0", "as_of": (TODAY - timedelta(days=31)).isoformat()}
    out = put_policy(client, cash=cash)
    assert out["cash_stale"] is True
    assert any("현금 기준일" in w and "31일" in w for w in out["warnings"])

    cash["as_of"] = (TODAY - timedelta(days=30)).isoformat()
    assert put_policy(client, cash=cash)["cash_stale"] is False


def test_warnings_name_a_loose_tolerance_and_a_goal_without_a_date(client):
    out = put_policy(client, drawdown_tolerance_pct="25", goal_krw="5000000", goal_date=None)
    assert any("20%" in w and "느슨" in w for w in out["warnings"])
    assert any("목표일" in w for w in out["warnings"])
    # Stored anyway: the user's number is not blocked.
    assert out["policy"]["drawdown_tolerance_pct"] == 25


def test_warning_when_a_cash_target_has_no_cash_record(client):
    out = put_policy(client, target_stock_pct="70", target_crypto_pct="20", target_cash_pct="10")
    assert any("현금 잔고를 적지 않아" in w for w in out["warnings"])


# --- kill switch reset --------------------------------------------------------------------------


def test_reset_turns_the_switch_off_and_records_the_user_as_actor(client, db):
    KillSwitch(db).trip("manual", "test trip")
    assert KillSwitch(db).state().tripped is True

    # An `actor` in the body is ignored: the server fixes it.
    res = client.post(
        "/api/rules/kill-switch/reset", json={"detail": "확인 후 해제", "actor": "system"}
    )
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["tripped"] is False and out["reason_code"] is None
    assert out["since"] is not None

    events = list(db.scalars(select(KillSwitchEvent).order_by(KillSwitchEvent.id)))
    assert [e.action for e in events] == ["trip", "reset"]
    assert events[-1].actor == "user" and events[-1].detail == "확인 후 해제"
    assert client.get("/api/rules/check").json()["kill_switch"]["tripped"] is False


def test_reset_when_not_tripped_answers_200_without_writing(client, db):
    res = client.post("/api/rules/kill-switch/reset", json={})
    assert res.status_code == 200
    assert res.json() == {"tripped": False, "reason_code": None, "detail": "", "since": None}
    assert db.scalar(select(func.count()).select_from(KillSwitchEvent)) == 0
    # No body at all works too.
    assert client.post("/api/rules/kill-switch/reset").status_code == 200


def test_reset_rejects_an_overlong_detail(client, db):
    KillSwitch(db).trip("manual")
    res = client.post("/api/rules/kill-switch/reset", json={"detail": "x" * 201})
    assert res.status_code == 422
    assert KillSwitch(db).state().tripped is True


# --- diagnosis -----------------------------------------------------------------------------------


def test_diagnosis_without_holdings_is_empty_but_well_formed(client):
    body = client.get("/api/coach/diagnosis").json()
    assert body["empty"] is True and body["policy_set"] is False
    assert body["weights"] == [] and body["violations"] == []
    assert body["risk"] == {"windows": [], "actual": None, "actual_error": None}
    assert body["equity_krw"] == 0 and body["cash_krw"] is None


def test_diagnosis_two_stocks_and_a_won_coin(client):
    seed_mixed(client)
    res = client.get("/api/coach/diagnosis")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["empty"] is False and body["as_of"] == DAY

    weights = {w["symbol"]: w for w in body["weights"]}
    assert set(weights) == {"AAPL", "MSFT", "BTC-USD"}
    assert sum(w["weight_pct"] for w in weights.values()) == pytest.approx(100)
    # No cash record: the equity base is the invested amount, so both weights agree.
    for w in weights.values():
        assert w["weight_pct"] == pytest.approx(w["invested_weight_pct"])
        assert w["cap_pct"] == 20
    assert weights["BTC-USD"]["currency"] == "KRW" and weights["AAPL"]["currency"] == "USD"

    exp = body["exposure"]
    assert exp["cash_pct"] is None
    assert exp["stock_pct"] + exp["crypto_pct"] == pytest.approx(100)
    assert exp["usd_pct"] == pytest.approx(exp["stock_pct"])  # the coin is held in won
    assert body["equity_krw"] == pytest.approx(exp["invested_krw"])
    assert body["concentration"]["count"] == 3 and 1 < body["concentration"]["effective_n"] <= 3

    windows = {w["name"]: w for w in body["risk"]["windows"]}
    assert set(windows) == {"1y", "3y"}
    for w in windows.values():
        assert w["usable"] is True and w["reason"] is None, w
        assert w["grid"] == "stock" and w["periods_per_year"] == 252
        assert sorted(w["included"]) == ["AAPL", "BTC-USD", "MSFT"] and w["excluded"] == []
        assert w["annual_vol_pct"] > 0 and 0 <= w["max_drawdown_pct"] < 100
        assert w["swing_1sigma_krw"] == pytest.approx(
            w["annual_vol_pct"] / 100 * body["equity_krw"]
        )
        assert w["coverage_pct"] == pytest.approx(100)
    assert windows["3y"]["rows"] > windows["1y"]["rows"] >= 200

    corr = body["correlation"]
    assert (
        sorted(corr["symbols"]) == ["AAPL", "BTC-USD", "MSFT"] and corr["method"] == "ledoit_wolf"
    )
    for i, row in enumerate(corr["matrix"]):
        assert row[i] == pytest.approx(1.0) and all(-1 <= x <= 1 for x in row)

    # Beta in the trade currency: stocks against SPY; the won coin's benchmark is itself.
    betas = {b["symbol"]: b for b in body["betas"]}
    assert set(betas) == {"AAPL", "MSFT"}
    for b in betas.values():
        assert b["benchmark"] == "SPY" and b["window"] == "1y"
        assert b["beta"] is not None and b["rows"] >= 60 and b["reason"] is None

    actual = body["risk"]["actual"]
    assert actual["since"] == "2026-10-01" and actual["points"] == 16
    assert 0 <= actual["twr_max_drawdown_pct"] < 100
    assert actual["limit_drawdown_pct"] == 20 and actual["limit_daily_loss_pct"] == 3

    codes = {v["code"]: v for v in body["violations"]}
    assert codes["cash_missing"]["severity"] == "info"
    assert body["total_risk_pct_equity"] is not None
    assert body["required_annual_return_pct"] is None and body["goal_years"] is None
    assert PAST_CAVEAT_KO in body["caveats"]


def test_diagnosis_flags_a_position_over_its_cap(client):
    assert buy(client, "AAPL", 100, 100).status_code == 201
    assert buy(client, "MSFT", 1, 200).status_code == 201
    body = client.get("/api/coach/diagnosis").json()
    over = [v for v in body["violations"] if v["code"] == "position_over_cap"]
    assert len(over) == 1 and over[0]["subject"] == "AAPL" and over[0]["severity"] == "warn"
    assert over[0]["limit"] == 20 and over[0]["value"] > 90
    assert "AAPL" in over[0]["detail"] and "상한" in over[0]["detail"]


def test_diagnosis_flags_crypto_over_cap_on_the_all_days_grid(client):
    assert krw_trade(client, "BTC", "0.01", "80000000").status_code == 201
    body = client.get("/api/coach/diagnosis").json()
    codes = {v["code"]: v for v in body["violations"]}
    assert codes["crypto_over_cap"]["value"] == pytest.approx(100)
    assert codes["crypto_over_cap"]["limit"] == 30
    # Only coins: every calendar day counts and the year has 365 periods.
    for w in body["risk"]["windows"]:
        assert w["grid"] == "all" and w["periods_per_year"] == 365 and w["usable"] is True
    # The coin held in won has no beta row (its benchmark would be itself).
    assert body["betas"] == []


def test_actual_curve_fails_closed_on_a_trade_twenty_times_off_its_days_close(client, provider):
    """N-COACH-1: a buy priced like a won total (25x the day's dollar close) would make the
    deposit of that day read as an impossible one-day loss. The curve is not computed; the
    reason names the count and the symbol, and the rest of the diagnosis still stands."""
    seed_mixed(client)
    wrong = round(close_on(provider, "GOOG", "2026-10-01") * 25, 2)
    assert buy(client, "GOOG", 13, wrong).status_code == 201

    body = client.get("/api/coach/diagnosis").json()
    assert body["risk"]["actual"] is None
    err = body["risk"]["actual_error"]
    assert "단가 확인" in err and "1건" in err and "GOOG" in err and "거래 페이지" in err
    # The past-window figures do not depend on the trade prices and are still there.
    assert all(w["usable"] for w in body["risk"]["windows"])
    assert "GOOG" in {w["symbol"] for w in body["weights"]}

    review = client.get("/api/coach/review").json()
    assert review["suspicious_trades"] == 1
    assert "단가 확인" in review["caveats"][0] and "1건" in review["caveats"][0]
    # The ledger facts are still reported (the caveat is the warning, not a blank).
    assert review["contributions_krw"] > 0
    # A month before the wrong trade is clean.
    before = client.get("/api/coach/review?month=2026-09").json()
    assert before["suspicious_trades"] == 0 and "단가 확인" not in before["caveats"][0]


def test_a_sell_twenty_times_below_the_close_is_suspicious_too(client, provider):
    assert buy(client, "AAPL", 10, 100).status_code == 201
    low = round(close_on(provider, "AAPL", "2026-10-02") / 40, 2)
    assert buy(client, "AAPL", 1, low, day="2026-10-02", side="sell").status_code == 201
    body = client.get("/api/coach/diagnosis").json()
    assert body["risk"]["actual"] is None and "AAPL" in body["risk"]["actual_error"]


def test_diagnosis_uses_the_cash_record_and_the_goal(client):
    seed_mixed(client)
    goal_date = (TODAY + timedelta(days=int(10 * 365.25))).isoformat()
    put_policy(
        client,
        cash={"krw": "100000000", "usd": "0", "as_of": DAY},
        goal_krw="1000000000",
        goal_date=goal_date,
        monthly_contribution_krw="500000",
        target_stock_pct="50",
        target_crypto_pct="20",
        target_cash_pct="30",
    )
    body = client.get("/api/coach/diagnosis").json()
    assert body["policy_set"] is True
    assert body["cash_krw"] == 100_000_000 and body["cash_as_of"] == DAY
    assert body["equity_krw"] == pytest.approx(body["invested_krw"] + 100_000_000)
    exp = body["exposure"]
    assert exp["cash_pct"] is not None and exp["cash_pct"] > 0
    assert exp["stock_pct"] + exp["crypto_pct"] + exp["cash_pct"] == pytest.approx(100)
    for w in body["weights"]:
        assert w["weight_pct"] < w["invested_weight_pct"]
    codes = {v["code"] for v in body["violations"]}
    assert "cash_missing" not in codes
    assert body["goal_years"] == pytest.approx(10, abs=0.01)
    assert body["required_annual_return_pct"] is not None and body["required_annual_return_pct"] > 0
    assert any("산수" in c for c in body["caveats"])


# --- rebalancing --------------------------------------------------------------------------------


def test_rebalance_sells_first_and_notes_the_missing_cash(client):
    assert buy(client, "AAPL", 100, 100).status_code == 201
    assert buy(client, "MSFT", 1, 200).status_code == 201
    assert krw_trade(client, "BTC", "0.001", "80000000").status_code == 201
    body = client.get("/api/coach/rebalance").json()
    assert body["empty"] is False and body["cash_known"] is False
    assert body["headline_ko"] == REBALANCE_HEADLINE_KO
    assert NO_CASH_NOTE_KO in body["notes"]
    assert body["class_targets"]["cash"] is None
    assert body["class_targets"]["stock"] + body["class_targets"]["crypto"] == pytest.approx(100)

    targets = {t["symbol"]: t for t in body["targets"]}
    assert targets["AAPL"]["capped"] is True and targets["AAPL"]["target_pct"] == pytest.approx(20)
    assert targets["AAPL"]["drift_pt"] == pytest.approx(
        targets["AAPL"]["current_pct"] - targets["AAPL"]["target_pct"]
    )

    orders = body["orders"]
    assert orders and orders[0]["side"] == "sell" and orders[0]["symbol"] == "AAPL"
    sell = orders[0]
    assert sell["status"] == "accepted" and sell["allowed_krw"] == pytest.approx(
        sell["requested_krw"]
    )
    # Bought at $100 and worth far more today: the reference realized P&L is positive.
    assert sell["realized_pnl_krw_if_sold"] > 0
    assert sell["approx_qty"] == pytest.approx(sell["allowed_krw"] / sell["price_krw"], abs=0.01)
    sides = [o["side"] for o in orders]
    assert sides == sorted(sides, key=lambda s: s != "sell")  # every sell before any buy
    buys = [o for o in orders if o["side"] == "buy"]
    assert buys
    for o in buys:
        assert o["realized_pnl_krw_if_sold"] is None
        assert len(o["labels"]) == len(o["reasons"])
        if "max_order_fraction" in o["reasons"]:
            assert "1회 주문 상한" in o["labels"]
    # The book after the orders: AAPL is down to its cap, the proceeds not spent stay as cash.
    after = {w["symbol"]: w["weight_pct"] for w in body["after"]["weights"]}
    assert after["AAPL"] == pytest.approx(20, abs=0.5)
    assert body["after"]["cash_pct"] is None and body["after"]["cash_krw"] >= 0


def test_rebalance_within_the_band_proposes_nothing(client):
    seed_mixed(client)
    put_policy(client, rebalance_band_pt="90")
    body = client.get("/api/coach/rebalance").json()
    assert body["band_pt"] == 90 and body["orders"] == []
    assert len(body["targets"]) == 3


def test_rebalance_without_holdings_is_empty(client):
    body = client.get("/api/coach/rebalance").json()
    assert body["empty"] is True and body["orders"] == [] and body["after"] is None


# --- habit patterns -----------------------------------------------------------------------------


def test_patterns_without_trades_is_empty(client):
    body = client.get("/api/coach/patterns").json()
    assert body["empty"] is True and body["patterns"] == [] and body["monthly"] == []


def test_patterns_flag_a_buy_after_a_run_up_from_real_synthetic_bars(client):
    # In FakeProvider's AAPL series the close before 2025-12-04 is 17.9% above the close 20
    # bars earlier; MSFT never moves 15% in 20 bars that year.
    assert buy(client, "MSFT", 2, 200).status_code == 201
    assert buy(client, "AAPL", 1, 250, day="2025-12-04").status_code == 201
    body = client.get("/api/coach/patterns").json()
    assert body["empty"] is False
    assert body["window_start"] == (TODAY - timedelta(days=365)).isoformat()
    assert body["window_end"] == DAY
    assert body["trades_considered"] == 2 and body["trades_without_bars"] == 0

    by_code = {p["code"]: p for p in body["patterns"]}
    chasing = by_code["chasing_buy"]
    assert chasing["label_ko"] == "급등 뒤 매수" and chasing["count"] == 1
    [flag] = chasing["trades"]
    assert flag["symbol"] == "AAPL" and flag["date"] == "2025-12-04"
    assert flag["value"] == pytest.approx(17.9, abs=0.2)
    assert by_code["averaging_down_below_cut"]["count"] == 0
    assert by_code["quick_rebuy_after_loss"]["count"] == 0
    assert by_code["overtrading"]["count"] == 0 and by_code["overtrading"]["months"] == []
    # Months from the first trade to the last, zeros included.
    months = [m["month"] for m in body["monthly"]]
    assert months[0] == "2025-12" and months[-1] == "2026-10" and len(months) == 11
    assert sum(m["total"] for m in body["monthly"]) == 2
    assert body["rule_lag"] == []


def test_patterns_flag_averaging_down_below_the_stop_and_a_quick_rebuy(client):
    # Won prices typed by the user: the stop for coins is -25% of the average cost. The
    # rebuy at 65M sits above the 85M average's stop (63.75M), so only the 70M buy is
    # averaging down.
    assert krw_trade(client, "BTC", "0.01", "100000000", day="2026-09-01").status_code == 201
    assert krw_trade(client, "BTC", "0.01", "70000000", day="2026-09-10").status_code == 201
    assert (
        krw_trade(client, "BTC", "0.01", "60000000", day="2026-09-15", side="sell").status_code
        == 201
    )
    assert krw_trade(client, "BTC", "0.01", "65000000", day="2026-09-20").status_code == 201
    body = client.get("/api/coach/patterns").json()
    by_code = {p["code"]: p for p in body["patterns"]}
    down = by_code["averaging_down_below_cut"]
    assert down["count"] == 1 and down["trades"][0]["date"] == "2026-09-10"
    assert "-30.0%" in down["trades"][0]["detail"]
    rebuy = by_code["quick_rebuy_after_loss"]
    assert rebuy["count"] == 1 and rebuy["trades"][0]["date"] == "2026-09-20"
    assert rebuy["trades"][0]["value"] == 5  # days after the losing sell
    assert body["trades_considered"] == 4


def test_rule_lag_carries_the_window_start_flag(client, provider):
    """A coin bought at three times its day's Upbit close sits far below its −25% stop ever
    since; the flag says how long and whether the loaded bars were below it from the first
    one (`since_window_start`, N-COACH-6). Not the 20x rule: 3x is a bad trade, not a typo."""
    price = round(close_on(provider, "KRW-BTC", "2026-10-01") * 3)
    assert krw_trade(client, "BTC", "0.01", str(price)).status_code == 201
    body = client.get("/api/coach/patterns").json()
    [lag] = body["rule_lag"]
    assert lag["symbol"] == "BTC-USD" and lag["currency"] == "KRW"
    assert lag["cut_price"] == pytest.approx(price * 0.75)
    assert lag["days"] >= 5 and lag["since"] <= "2026-10-11"
    assert isinstance(lag["since_window_start"], bool)
    # The 3x price is not a mis-priced trade: the actual curve is still computed.
    assert client.get("/api/coach/diagnosis").json()["risk"]["actual"] is not None


# --- monthly review -----------------------------------------------------------------------------


def test_review_of_the_buy_month_counts_the_buys_as_contributions(client):
    seed_mixed(client)
    holdings = client.get("/api/portfolio/holdings").json()
    summary = client.get("/api/portfolio/summary").json()
    res = client.get("/api/coach/review")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["empty"] is False and body["month"] == "2026-10"
    assert body["start"] == "2026-09-30" and body["end"] == DAY
    # Nothing was held before the month: the first buys are deposits, not market gains.
    assert body["start_point"] is None and body["start_value_krw"] == 0
    assert body["end_point"] == DAY
    assert body["contributions_krw"] == pytest.approx(
        sum(h["cost_basis_krw"] for h in holdings), rel=1e-6
    )
    assert body["end_value_krw"] == pytest.approx(summary["market_value_krw"], rel=1e-3)
    assert body["change_krw"] == pytest.approx(body["end_value_krw"] - body["start_value_krw"])
    assert body["market_pnl_krw"] == pytest.approx(body["change_krw"] - body["contributions_krw"])
    assert body["realized_pnl_krw"] == 0 and body["dividends_krw"] == 0
    assert body["trades"] == {"buys": 3, "sells": 0}
    assert [b["symbol"] for b in body["benchmarks"]] == ["SPY", "BTC-USD"]
    for b in body["benchmarks"]:
        assert b["name_ko"] and b["start_value_krw"] == 0
        assert b["excess_krw"] == pytest.approx(body["change_krw"] - b["change_krw"])
    assert body["months_available"] == ["2026-10"]
    assert isinstance(body["violations_now"], int)
    # Sane prices: no 20x trade, flags counted (the month is inside the habit window), and the
    # caveats start with the benchmark note.
    assert body["suspicious_trades"] == 0 and body["flags_counted"] is True
    assert body["caveats"][0] == BENCHMARK_CAVEAT_KO


def test_review_of_a_month_before_the_habit_window_does_not_count_flags(client, provider):
    """N-COACH-2: habit flags exist only for the last year of trades, so a month that starts
    before the window says so instead of showing zero flags as a fact."""
    day = "2025-06-16"
    assert (
        buy(client, "AAPL", 1, round(close_on(provider, "AAPL", day), 2), day=day).status_code
        == 201
    )
    old = client.get("/api/coach/review?month=2025-06").json()
    assert old["flags_counted"] is False and old["flagged_trades"] == []
    assert FLAGS_OUTSIDE_WINDOW_KO in old["caveats"]
    # The window starts 2025-10-16: October 2025 begins before it, November inside it.
    assert client.get("/api/coach/review?month=2025-10").json()["flags_counted"] is False
    recent = client.get("/api/coach/review?month=2025-11").json()
    assert recent["flags_counted"] is True
    assert FLAGS_OUTSIDE_WINDOW_KO not in recent["caveats"]


def test_review_of_a_month_before_the_first_trade_is_all_zero(client):
    seed_mixed(client)
    body = client.get("/api/coach/review?month=2026-08").json()
    assert body["empty"] is False and body["month"] == "2026-08"
    assert body["start"] == "2026-07-31" and body["end"] == "2026-08-31"
    assert body["start_value_krw"] == 0 and body["end_value_krw"] == 0
    assert body["contributions_krw"] == 0 and body["trades"] == {"buys": 0, "sells": 0}
    assert body["months_available"] == ["2026-10"]


def test_review_months_run_from_the_first_trade(client):
    assert buy(client, "AAPL", 1, 100, day="2026-03-15").status_code == 201
    assert buy(client, "AAPL", 1, 100, day="2026-05-02").status_code == 201
    body = client.get("/api/coach/review?month=2026-05").json()
    assert body["trades"] == {"buys": 1, "sells": 0}
    assert body["months_available"] == [
        "2026-10",
        "2026-09",
        "2026-08",
        "2026-07",
        "2026-06",
        "2026-05",
        "2026-04",
        "2026-03",
    ]
    # One share bought in March was worth something on 2026-04-30: the May start value.
    assert body["start_point"] == "2026-04-30" and body["start_value_krw"] > 0


@pytest.mark.parametrize("month", ["2026-13", "abc", "2027-01"])
def test_review_rejects_a_bad_or_future_month(client, month):
    seed_mixed(client)
    assert client.get(f"/api/coach/review?month={month}").status_code == 422


def test_review_without_trades_is_empty(client):
    body = client.get("/api/coach/review").json()
    assert body["empty"] is True and body["months_available"] == ["2026-10"]
