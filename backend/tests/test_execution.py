"""The order gate: kill switch, risk check, and the live-trading block (ISSUE-011~013, 027).

Rule: no file in this repository sets AM_LIVE_TRADING to true, these tests included. They
prove the block from the default side only: with the flag off the live broker is never built
or called.
"""

import logging
import os
import re
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.config import Settings, get_settings
from app.db.models import KillSwitchEvent
from app.strategy.execution import BrokerAck, KillSwitch, execute
from app.strategy.risk import Book, Order, RiskLimits

FAKE_SECRET = "sk-ant-api03-FAKE-SECRET-0123456789"
ACCOUNT = "123-45-678901"
REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def settings(monkeypatch) -> Settings:
    for key in list(os.environ):
        if key.upper().startswith("AM_"):
            monkeypatch.delenv(key)
    get_settings.cache_clear()
    yield Settings(_env_file=None)
    get_settings.cache_clear()


@pytest.fixture
def switch(db) -> KillSwitch:
    return KillSwitch(db, clock=lambda: datetime(2026, 10, 20, 12, 0))


def paper_broker() -> MagicMock:
    broker = MagicMock()
    broker.submit.return_value = BrokerAck("paper", "paper:1")
    return broker


BOOK = Book(1_000_000.0, {})


def run(order, settings, switch, paper, live_factory):
    return execute(
        order,
        book=BOOK,
        settings=settings,
        kill_switch=switch,
        limits=RiskLimits.from_settings(settings),
        paper=paper,
        live_factory=live_factory,
    )


def test_default_settings_route_orders_to_paper_and_never_build_the_live_broker(settings, switch):
    assert settings.live_trading is False
    paper, live_factory = paper_broker(), MagicMock()
    result = run(Order("SPY", "buy", 30_000), settings, switch, paper, live_factory)
    assert result.status == "submitted"
    assert result.ack.venue == "paper"
    live_factory.assert_not_called()
    live_factory.return_value.submit.assert_not_called()
    paper.submit.assert_called_once_with(Order("SPY", "buy", 30_000))


def test_the_paper_broker_gets_the_clipped_order(settings, switch):
    paper, live_factory = paper_broker(), MagicMock()
    result = run(Order("SPY", "buy", 900_000), settings, switch, paper, live_factory)
    assert result.decision.status == "clipped"
    paper.submit.assert_called_once_with(Order("SPY", "buy", 50_000))
    live_factory.assert_not_called()


def test_rejected_orders_reach_no_broker(settings, switch):
    paper, live_factory = paper_broker(), MagicMock()
    result = run(Order("SPY", "sell", 10_000), settings, switch, paper, live_factory)
    assert result.status == "rejected"
    assert "short_sale" in result.reason
    paper.submit.assert_not_called()
    live_factory.assert_not_called()


def test_tripped_kill_switch_halts_every_order_and_keeps_the_reason(settings, switch, db):
    switch.trip("max_drawdown", "drawdown 21.3% > 20%")
    paper, live_factory = paper_broker(), MagicMock()
    for order in (Order("SPY", "buy", 10_000), Order("BTC-USD", "buy", 1_000)):
        result = run(order, settings, switch, paper, live_factory)
        assert result.status == "halted"
        assert "max_drawdown" in result.reason
    paper.submit.assert_not_called()
    live_factory.assert_not_called()
    event = db.scalars(select(KillSwitchEvent)).one()
    assert (event.action, event.reason_code, event.actor) == ("trip", "max_drawdown", "system")
    assert event.detail == "drawdown 21.3% > 20%"


def test_only_the_user_resets_the_kill_switch(settings, switch):
    switch.trip("daily_loss", "loss 3.4% > 3%")
    with pytest.raises(PermissionError):
        switch.reset(actor="system")
    assert switch.state().tripped
    switch.reset(actor="user")
    assert not switch.state().tripped
    paper = paper_broker()
    assert run(Order("SPY", "buy", 10_000), settings, switch, paper, MagicMock()).status == (
        "submitted"
    )


def test_unknown_trip_reason_is_refused(switch):
    with pytest.raises(ValueError):
        switch.trip("bored")


def test_unreadable_kill_switch_state_counts_as_tripped(settings):
    broken = MagicMock()
    broken.scalars.side_effect = OperationalError("SELECT", {}, Exception("disk I/O error"))
    switch = KillSwitch(broken)
    state = switch.state()
    assert (state.tripped, state.reason_code) == (True, "state_unreadable")
    paper, live_factory = paper_broker(), MagicMock()
    result = run(Order("SPY", "buy", 10_000), settings, switch, paper, live_factory)
    assert result.status == "halted"
    paper.submit.assert_not_called()
    live_factory.assert_not_called()


def test_broker_errors_never_leak_secrets(settings, switch, caplog):
    paper = MagicMock()
    paper.submit.side_effect = RuntimeError(f"401 for key={FAKE_SECRET} account {ACCOUNT}")
    with caplog.at_level(logging.DEBUG):
        result = run(Order("SPY", "buy", 10_000), settings, switch, paper, MagicMock())
    assert result.status == "failed"
    text = repr(result) + caplog.text
    assert FAKE_SECRET not in text
    assert ACCOUNT not in text
    assert "RuntimeError" in caplog.text


# --- static check: nothing in the repository switches real orders on ----------------------

FLAG = "AM_LIVE_" + "TRADING"
FIELD = "live_" + "trading"
TRUTHY = "(?:" + "|".join(["tr" + "ue", "1", "yes", "on"]) + ")"
PATTERNS = [
    # The comments below write the truthy value as <on> so this file passes its own scan.
    # FLAG=<on> in env files, scripts and settings
    re.compile(FLAG + r"\s*[=:]\s*['\"]?" + TRUTHY + r"\b", re.IGNORECASE),
    # monkeypatch.setenv("FLAG", "<on>") / os.environ["FLAG"] = "<on>"
    re.compile(FLAG + r"['\"]\s*[,\]]\s*=?\s*['\"]" + TRUTHY + r"['\"]", re.IGNORECASE),
    # Settings(FIELD=<on>), FIELD: bool = <on>, settings.FIELD = <on>
    re.compile(FIELD + r"\s*(?::\s*bool\s*)?=\s*(?:Tr" + r"ue|['\"]" + TRUTHY + r"['\"])"),
    # model_copy(update={"FIELD": <on>}) and dict literals
    re.compile(r"['\"]" + FIELD + r"['\"]\s*:\s*(?:Tr" + r"ue|['\"]" + TRUTHY + r"['\"])"),
]
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "dist", "artifacts", ".ruff_cache"}
SUFFIXES = {
    *(".py", ".toml", ".ini", ".cfg", ".json", ".yml", ".yaml"),
    *(".ts", ".tsx", ".ps1", ".sh", ".md"),
}


def _scanned_files():
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".pytest")]
        for name in files:
            path = Path(root) / name
            # The user's own backend/.env is theirs to change; .env.example is ours.
            if name == ".env.example" or path.suffix in SUFFIXES:
                yield path


def test_patterns_catch_what_they_should():
    samples = [
        FLAG + "=" + "tr" + "ue",
        f'monkeypatch.setenv("{FLAG}", "{"TR" + "UE"}")',
        f"Settings({FIELD}={'Tr' + 'ue'})",
        f'{{"{FIELD}": {"Tr" + "ue"}}}',
    ]
    for sample in samples:
        assert any(p.search(sample) for p in PATTERNS), sample
    assert not any(p.search(FLAG + "=false") for p in PATTERNS)


def test_no_file_turns_live_trading_on():
    hits = []
    for path in _scanned_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for p in PATTERNS:
            for m in p.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                hits.append(f"{path.relative_to(REPO)}:{line}: {m.group(0)}")
    assert hits == []


def test_env_example_ships_live_trading_off():
    text = (REPO / "backend" / ".env.example").read_text(encoding="utf-8")
    assert re.search(rf"^{FLAG}=false$", text, re.MULTILINE)


def test_last_trip_survives_a_reset_and_fails_closed(switch):
    assert switch.last_trip_at() is None
    switch.trip("daily_loss", "loss 3.4% > 3%")
    switch.reset(actor="user")
    assert switch.last_trip_at() == datetime(2026, 10, 20, 12, 0)
    broken = MagicMock()
    broken.scalar.side_effect = OperationalError("SELECT", {}, Exception("disk I/O error"))
    assert KillSwitch(broken).last_trip_at() == datetime.max
