"""The deployment image has neither torch nor transformers (the `lstm` and `ml` dependency
groups, DECISIONS.md D-035). The app must still import, and what needs those libraries must
say so plainly instead of answering with made-up numbers.

The import check runs in a fresh interpreter: in this process other tests have already
imported torch, so only a new one shows what happens when it was never there.
"""

import importlib.abc
import importlib.machinery
import inspect
import json
import os
import subprocess
import sys
import types
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from app.data.news_sources import Article, NewsDataError
from app.deps import get_finnhub, get_gdelt, get_scorer
from app.services.news import NewsService, finbert_installed
from app.services.predictions import LSTM_UNAVAILABLE_CODE
from tests.conftest import TODAY
from tests.fakes import FakeFinnhub, FakeGdelt

BACKEND = Path(__file__).resolve().parent.parent
NOW = datetime.combine(TODAY, datetime.min.time()) + timedelta(hours=22)  # UTC
BLOCKED = ("torch", "transformers")


class Block(importlib.abc.MetaPathFinder):
    """What an install without a package looks like to `import`: the name cannot be found.
    (Putting None in sys.modules instead would break scipy, which looks torch up there.)"""

    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in BLOCKED:
            raise ModuleNotFoundError(f"No module named {name!r} (blocked by the test)", name=name)
        return None


# Runs with torch and transformers impossible to import, and prints one JSON line.
PROBE = (
    f"import importlib.abc\nimport json\nimport sys\n\nBLOCKED = {BLOCKED!r}\n\n\n"
    + inspect.getsource(Block)
    + """

sys.meta_path.insert(0, Block())

from fastapi.testclient import TestClient  # noqa: E402

from app.deps import get_scorer  # noqa: E402
from app.main import app  # noqa: E402

with TestClient(app, base_url="http://localhost") as client:
    routes = {
        "list": client.get("/api/predictions"),
        "forecast": client.get("/api/predictions/AAA"),
        "backtest": client.get("/api/predictions/AAA/backtest"),
        "train": client.post("/api/predictions/AAA/train"),
        "train_status": client.get("/api/predictions/AAA/train"),
    }
    print(
        json.dumps(
            {
                "health": client.get("/api/health").status_code,
                "routes": {k: [r.status_code, r.json().get("code")] for k, r in routes.items()},
                "scorer_is_none": get_scorer() is None,
                "imported": sorted(m for m in sys.modules if m.split(".")[0] in BLOCKED),
            }
        )
    )
"""
)


def test_app_imports_and_answers_without_torch(tmp_path):
    script = tmp_path / "probe.py"
    script.write_text(PROBE, encoding="utf-8")
    env = os.environ | {
        "PYTHONPATH": str(BACKEND),
        "AM_DATABASE_URL": f"sqlite:///{(tmp_path / 'probe.db').as_posix()}",
        "AM_MARKET_PROVIDER": "fake",
        # A plain local instance whatever the developer's own .env says.
        "AM_ENV": "development",
        "AM_DEMO_MODE": "false",
        "AM_AUTH_PASSWORD_HASH": "",
        "AM_SESSION_SECRET": "",
        "AM_RATE_LIMIT_PER_MINUTE": "0",
    }
    done = subprocess.run(
        [sys.executable, str(script)],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    result = json.loads(done.stdout.strip().splitlines()[-1])

    assert result["health"] == 200
    assert result["imported"] == []  # nothing pulled torch in behind our back
    assert result["scorer_is_none"] is True
    assert result["routes"] == {
        name: [501, LSTM_UNAVAILABLE_CODE]
        for name in ("list", "forecast", "backtest", "train", "train_status")
    }


@pytest.fixture
def no_torch(monkeypatch):
    """torch cannot be imported in this process either (both are put back after the test)."""
    monkeypatch.delitem(sys.modules, "torch", raising=False)
    monkeypatch.setattr(sys, "meta_path", [Block(), *sys.meta_path])


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/predictions"),
        ("GET", "/api/predictions/AAA"),
        ("GET", "/api/predictions/AAA/backtest"),
        ("POST", "/api/predictions/AAA/train"),
        ("GET", "/api/predictions/AAA/train"),
    ],
)
def test_lstm_routes_answer_501_without_torch(client, no_torch, method, path):
    res = client.request(method, path)
    assert res.status_code == 501
    body = res.json()
    assert body["code"] == LSTM_UNAVAILABLE_CODE
    assert "torch" in body["detail"]


@pytest.mark.parametrize("missing", ["torch", "transformers"])
def test_no_scorer_when_a_finbert_library_is_missing(monkeypatch, missing):
    for name in ("torch", "transformers"):
        # Stand-in modules (find_spec reads `__spec__`), so the check does not depend on what
        # this environment happens to have installed.
        stub = types.ModuleType(name)
        stub.__spec__ = importlib.machinery.ModuleSpec(name, loader=None)
        monkeypatch.setitem(sys.modules, name, stub)
    assert finbert_installed() is True
    monkeypatch.delitem(sys.modules, missing)
    monkeypatch.setattr(sys, "meta_path", [Block(), *sys.meta_path])
    assert finbert_installed() is False
    assert get_scorer.__wrapped__() is None


@pytest.fixture
def finnhub():
    headline = Article(
        published_at=datetime(2026, 10, 15, 14, tzinfo=UTC),
        headline="AAA shares surge on record sales",
        source="Test",
        url="u1",
    )
    return FakeFinnhub({"AAA": [headline]})


def test_news_without_a_sentiment_model_fetches_no_headlines(db, provider, finnhub):
    gdelt = FakeGdelt()
    service = NewsService(db, provider, gdelt, finnhub, None, now=lambda: NOW)

    summary = service.summary("AAA")
    assert summary.sentiment_enabled is False
    assert summary.finnhub_enabled is True  # the key is there; the model is what is missing
    assert summary.articles == []  # nothing stored without a score
    assert summary.warnings == []
    assert finnhub.calls == []
    assert len(gdelt.calls) == 1 and summary.days  # GDELT tone still works

    # A background sync wants the sentiment features, so it stops instead of skipping them.
    with pytest.raises(NewsDataError, match="FinBERT"):
        service.sync("AAA", date(2026, 10, 1))


def test_news_endpoint_reports_the_missing_sentiment_model(client, finnhub):
    client.app.dependency_overrides[get_gdelt] = lambda: FakeGdelt()
    client.app.dependency_overrides[get_finnhub] = lambda: finnhub
    client.app.dependency_overrides[get_scorer] = lambda: None
    body = client.get("/api/news/aaa").json()
    assert body["sentiment_enabled"] is False
    assert body["finnhub_enabled"] is True
    assert body["articles"] == []
