"""`scripts/backup_db.py`: online SQLite backup, integrity check and retention.

Every database here lives under `tmp_path`; the real ledger is never opened.
"""

import contextlib
import importlib.util
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# `scripts/` is not a package: load the file by path. The module has to be in sys.modules
# while it runs, because its dataclass resolves annotations through its module.
SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "backup_db.py"
_spec = importlib.util.spec_from_file_location("backup_db_script", SCRIPT)
backup_db = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = backup_db
_spec.loader.exec_module(backup_db)

NOW = datetime(2026, 11, 10, 9, 30, 15)


def _make_db(path: Path, rows: int = 3, wal: bool = True) -> None:
    with contextlib.closing(sqlite3.connect(path)) as conn:
        if wal:
            conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE trades (id INTEGER PRIMARY KEY, symbol TEXT, qty TEXT)")
        conn.executemany(
            "INSERT INTO trades (symbol, qty) VALUES (?, ?)",
            [(f"DEMO{i}", str(i)) for i in range(rows)],
        )
        conn.commit()


def _rows(path: Path) -> list[tuple]:
    with contextlib.closing(sqlite3.connect(path)) as conn:
        return conn.execute("SELECT id, symbol, qty FROM trades ORDER BY id").fetchall()


def _names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


def _fake_backup(folder: Path, stamp: datetime) -> Path:
    path = folder / f"asset_manager-{stamp:%Y%m%d-%H%M%S}.db"
    _make_db(path, rows=1, wal=False)
    return path


def test_backup_is_a_verified_copy_with_a_timestamped_name(tmp_path):
    source = tmp_path / "ledger.db"
    _make_db(source)
    dest = tmp_path / "backups" / "nested"  # created on demand

    result = backup_db.backup(source, dest, now=NOW)

    assert result.path == dest / "asset_manager-20261110-093015.db"
    assert result.size == result.path.stat().st_size > 0
    assert result.removed == []
    assert backup_db.integrity_errors(result.path) == []
    assert _rows(result.path) == _rows(source)
    # No temporary or journal files are left next to the backup.
    assert [n for n in _names(dest) if not backup_db.BACKUP_NAME.match(n)] == []


@pytest.mark.parametrize("wal", [True, False])
def test_backup_includes_rows_committed_while_the_app_holds_the_db_open(tmp_path, wal):
    """The app keeps connections open and, in WAL mode, recent commits live only in the
    `-wal` file: a plain file copy would lose them, the online backup must not."""
    source = tmp_path / "ledger.db"
    _make_db(source, rows=2, wal=wal)
    with contextlib.closing(sqlite3.connect(source)) as app_conn:
        app_conn.execute("INSERT INTO trades (symbol, qty) VALUES ('LATE', '9')")
        app_conn.commit()

        result = backup_db.backup(source, tmp_path / "backups", now=NOW)

        # The source stays usable for the still-open connection.
        app_conn.execute("INSERT INTO trades (symbol, qty) VALUES ('AFTER', '1')")
        app_conn.commit()

    copied = _rows(result.path)
    assert [r[1] for r in copied] == ["DEMO0", "DEMO1", "LATE"]
    assert [r[1] for r in _rows(source)] == ["DEMO0", "DEMO1", "LATE", "AFTER"]


def test_keep_removes_only_this_scripts_oldest_backups(tmp_path):
    source = tmp_path / "ledger.db"
    _make_db(source)
    dest = tmp_path / "backups"
    dest.mkdir()
    old = [_fake_backup(dest, NOW - timedelta(days=d)) for d in (1, 2, 3)]
    # Same folder, different names: none of these may ever be deleted.
    bystanders = [
        "notes.txt",
        "asset_manager-latest.db",
        "asset_manager-20260101-000000.db.bak",
        "asset_manager-20260101-000000.sqlite",
        "other-20260101-000000.db",
        "xasset_manager-20260101-000000.db",
    ]
    for name in bystanders:
        (dest / name).write_text("keep me")
    (dest / "asset_manager-20250101-000000.db").mkdir()  # a folder with a matching name

    result = backup_db.backup(source, dest, keep=2, now=NOW)

    assert sorted(p.name for p in result.removed) == sorted(p.name for p in old[1:])
    kept = [p.name for p in backup_db.existing_backups(dest)]
    assert kept == [result.path.name, old[0].name]
    for name in bystanders:
        assert (dest / name).read_text() == "keep me"
    assert (dest / "asset_manager-20250101-000000.db").is_dir()


def test_keep_larger_than_the_number_of_backups_removes_nothing(tmp_path):
    source = tmp_path / "ledger.db"
    _make_db(source)
    dest = tmp_path / "backups"
    dest.mkdir()
    old = _fake_backup(dest, NOW - timedelta(days=1))

    result = backup_db.backup(source, dest, now=NOW)  # default keep

    assert backup_db.DEFAULT_KEEP == 14
    assert result.removed == []
    assert backup_db.existing_backups(dest) == [result.path, old]


@pytest.mark.parametrize("keep", [0, -1])
def test_keep_must_be_at_least_one(tmp_path, keep):
    source = tmp_path / "ledger.db"
    _make_db(source)
    dest = tmp_path / "backups"
    dest.mkdir()
    old = _fake_backup(dest, NOW - timedelta(days=1))

    with pytest.raises(backup_db.BackupError, match="keep"):
        backup_db.backup(source, dest, keep=keep, now=NOW)

    assert _names(dest) == [old.name]


def test_missing_source_fails_and_is_not_created(tmp_path):
    source = tmp_path / "nope.db"

    with pytest.raises(backup_db.BackupError, match="not found"):
        backup_db.backup(source, tmp_path / "backups", now=NOW)

    assert not source.exists()
    assert not (tmp_path / "backups").exists()


def test_a_source_that_is_not_a_database_leaves_no_backup_and_prunes_nothing(tmp_path):
    source = tmp_path / "ledger.db"
    source.write_text("this is not a sqlite file, " * 200)
    dest = tmp_path / "backups"
    dest.mkdir()
    old = [_fake_backup(dest, NOW - timedelta(days=d)) for d in (1, 2)]

    with pytest.raises(backup_db.BackupError, match="could not back up"):
        backup_db.backup(source, dest, keep=1, now=NOW)

    # The failed run neither left a file behind nor deleted the good backups.
    assert _names(dest) == sorted(p.name for p in old)


def test_an_existing_backup_is_never_overwritten(tmp_path):
    source = tmp_path / "ledger.db"
    _make_db(source, rows=1)
    dest = tmp_path / "backups"
    first = backup_db.backup(source, dest, now=NOW)
    with contextlib.closing(sqlite3.connect(source)) as conn:
        conn.execute("INSERT INTO trades (symbol, qty) VALUES ('NEW', '1')")
        conn.commit()

    with pytest.raises(backup_db.BackupError, match="already exists"):
        backup_db.backup(source, dest, now=NOW)

    assert _names(dest) == [first.path.name]
    assert [r[1] for r in _rows(first.path)] == ["DEMO0"]


def test_integrity_errors_reports_a_damaged_file(tmp_path):
    good = tmp_path / "good.db"
    _make_db(good, rows=500, wal=False)
    assert backup_db.integrity_errors(good) == []

    damaged = tmp_path / "damaged.db"
    data = bytearray(good.read_bytes())
    page = 4096
    assert len(data) > 3 * page
    data[page : 2 * page] = b"\xff" * page  # wipe a whole b-tree page, keep the header
    damaged.write_bytes(bytes(data))

    try:
        errors = backup_db.integrity_errors(damaged)
    except sqlite3.DatabaseError as exc:  # some damage is reported as an exception
        errors = [str(exc)]
    assert errors


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://user@db.example/asset",
        "postgresql+psycopg://user@db.example/asset",
        "mysql+pymysql://user@db.example/asset",
        "sqlite://",
        "sqlite:///:memory:",
        "sqlite:///",
        "not-a-url",
        "",
    ],
)
def test_urls_without_a_sqlite_file_are_rejected(url):
    with pytest.raises(backup_db.BackupError):
        backup_db.sqlite_path(url)


def test_sqlite_urls_resolve_like_sqlalchemy():
    assert backup_db.sqlite_path("sqlite:///demo.db") == Path("demo.db")
    assert backup_db.sqlite_path("sqlite:////data/demo.db") == Path("/data/demo.db")
    assert backup_db.sqlite_path("sqlite:///C:/data/asset.db") == Path("C:/data/asset.db")
    assert backup_db.sqlite_path("sqlite+pysqlite:///x/y.db?timeout=5") == Path("x/y.db")


def test_default_source_comes_from_the_settings_url(tmp_path, monkeypatch):
    source = tmp_path / "from-settings.db"
    monkeypatch.setattr(backup_db, "_settings_url", lambda: f"sqlite:///{source.as_posix()}")
    assert backup_db.default_source() == source

    monkeypatch.setattr(backup_db, "_settings_url", lambda: "postgresql://user@db.example/asset")
    with pytest.raises(backup_db.BackupError, match="only sqlite"):
        backup_db.default_source()


def test_cli_backs_up_and_reports(tmp_path, capsys):
    source = tmp_path / "ledger.db"
    _make_db(source)
    dest = tmp_path / "backups"

    code = backup_db.main(["--source", str(source), "--dest-dir", str(dest), "--keep", "3"])

    assert code == 0
    (made,) = backup_db.existing_backups(dest)
    out = capsys.readouterr().out
    assert made.name in out and "integrity_check ok" in out
    assert _rows(made) == _rows(source)


def test_cli_accepts_a_sqlite_url_and_refuses_other_databases(tmp_path, capsys, monkeypatch):
    source = tmp_path / "ledger.db"
    _make_db(source)
    dest = tmp_path / "backups"

    url = f"sqlite:///{source.as_posix()}"
    assert backup_db.main(["--source", url, "--dest-dir", str(dest)]) == 0
    assert len(backup_db.existing_backups(dest)) == 1
    capsys.readouterr()

    other = "postgresql://user@db.example/asset"
    code = backup_db.main(["--source", other, "--dest-dir", str(dest)])
    assert code == 1
    assert "only sqlite" in capsys.readouterr().err

    # Without --source the settings URL decides, and a non-sqlite one is refused as well.
    monkeypatch.setattr(backup_db, "_settings_url", lambda: "postgresql://user@db.example/asset")
    assert backup_db.main(["--dest-dir", str(dest)]) == 1
    assert "only sqlite" in capsys.readouterr().err
    assert len(backup_db.existing_backups(dest)) == 1
