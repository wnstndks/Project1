"""Online backup of the SQLite ledger (DECISIONS.md D-035).

Run from `backend/` (or use `scripts/backup-db.ps1` from the project root):

    py -3.11 -m uv run python scripts/backup_db.py
    py -3.11 -m uv run python scripts/backup_db.py --dest-dir D:\\backups --keep 30
    py -3.11 -m uv run python scripts/backup_db.py --source other.db --dest-dir D:\\backups

Copies the database with sqlite3's online backup API (`Connection.backup`), so the server may
keep running: the copy is one consistent snapshot that includes rows still sitting in the
`-wal` file, which copying the `.db` file by hand would miss. The source is opened read-only
and is never created or modified.

The copy is written as `asset_manager-YYYYMMDD-HHMMSS.db.partial`, checked with
`PRAGMA integrity_check` and only then renamed to `asset_manager-YYYYMMDD-HHMMSS.db` (local
time). After a verified backup, backups beyond the newest `--keep` are deleted; only files
with exactly that name pattern are ever removed. A failed run deletes nothing.

Backups hold the real ledger: keep the destination outside the repository (the default is
`~/asset-manager-backups`) and out of any folder a container can see.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

PREFIX = "asset_manager-"
BACKUP_NAME = re.compile(r"^asset_manager-\d{8}-\d{6}\.db$")
DEFAULT_KEEP = 14
DEFAULT_DEST = Path.home() / "asset-manager-backups"


class BackupError(Exception):
    """The backup was not made; nothing was pruned."""


@dataclass(frozen=True)
class BackupResult:
    path: Path
    size: int
    removed: list[Path] = field(default_factory=list)


def sqlite_path(url: str) -> Path:
    """File behind a SQLAlchemy sqlite URL (`sqlite:///rel.db`, `sqlite:////abs/x.db`,
    `sqlite:///C:/x.db`). Anything else, including in-memory databases, is refused."""
    scheme, sep, rest = url.partition("://")
    if not sep or scheme.split("+")[0].lower() != "sqlite":
        raise BackupError(f"only sqlite databases can be backed up, not '{scheme}'")
    if not rest.startswith("/"):
        raise BackupError("sqlite URL has no file path (in-memory database)")
    path = rest[1:].split("?", 1)[0]
    if not path or path == ":memory:" or path.startswith("file:"):
        raise BackupError("sqlite URL has no file path (in-memory database)")
    return Path(path)


def _settings_url() -> str:
    backend = str(Path(__file__).resolve().parent.parent)
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from app.config import get_settings

    return get_settings().database_url


def default_source() -> Path:
    """The database the app itself uses (`AM_DATABASE_URL`, else the default file)."""
    return sqlite_path(_settings_url())


def _open_readonly(path: Path, *, immutable: bool = False) -> sqlite3.Connection:
    # mode=ro: a missing file is an error instead of a new empty database.
    # immutable=1 (only for the finished copy): no -wal/-shm files appear next to it.
    uri = f"{path.resolve().as_uri()}?mode=ro" + ("&immutable=1" if immutable else "")
    return sqlite3.connect(uri, uri=True)


def integrity_errors(path: Path) -> list[str]:
    """Messages from `PRAGMA integrity_check`; empty when the file is sound."""
    with contextlib.closing(_open_readonly(path, immutable=True)) as conn:
        messages = [str(row[0]) for row in conn.execute("PRAGMA integrity_check")]
    return [] if messages == ["ok"] else messages


def existing_backups(dest_dir: Path) -> list[Path]:
    """This script's backups in `dest_dir`, newest first (the name carries the time)."""
    found = [p for p in dest_dir.iterdir() if p.is_file() and BACKUP_NAME.match(p.name)]
    return sorted(found, key=lambda p: p.name, reverse=True)


def prune(dest_dir: Path, keep: int) -> list[Path]:
    removed = []
    for old in existing_backups(dest_dir)[keep:]:
        old.unlink()
        removed.append(old)
    return removed


def backup(
    source: Path, dest_dir: Path, keep: int = DEFAULT_KEEP, now: datetime | None = None
) -> BackupResult:
    if keep < 1:
        raise BackupError("--keep must be at least 1")
    if not source.is_file():
        raise BackupError(f"source database not found: {source}")

    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    final = dest_dir / f"{PREFIX}{stamp}.db"
    if final.exists():
        raise BackupError(f"backup already exists, not overwriting: {final}")
    partial = final.with_name(final.name + ".partial")

    try:
        with (
            contextlib.closing(_open_readonly(source)) as src,
            contextlib.closing(sqlite3.connect(partial)) as dst,
        ):
            src.backup(dst)
        errors = integrity_errors(partial)
        if errors:
            raise BackupError(f"integrity_check failed on the copy: {'; '.join(errors[:5])}")
        os.replace(partial, final)
    except (sqlite3.Error, OSError) as exc:
        raise BackupError(f"could not back up {source}: {exc}") from exc
    finally:
        for leftover in (partial, partial.with_name(partial.name + "-journal")):
            leftover.unlink(missing_ok=True)

    return BackupResult(final, final.stat().st_size, prune(dest_dir, keep))


def _source_arg(value: str) -> Path:
    return sqlite_path(value) if "://" in value else Path(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--source",
        help="SQLite file or sqlite:/// URL to back up (default: the app's AM_DATABASE_URL)",
    )
    parser.add_argument(
        "--dest-dir",
        type=Path,
        default=DEFAULT_DEST,
        help=f"folder for the backups (default: {DEFAULT_DEST})",
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=DEFAULT_KEEP,
        help=f"number of newest backups to keep (default: {DEFAULT_KEEP})",
    )
    args = parser.parse_args(argv)

    try:
        source = _source_arg(args.source) if args.source else default_source()
        result = backup(source, args.dest_dir, args.keep)
    except BackupError as exc:
        print(f"backup failed: {exc}", file=sys.stderr)
        return 1

    print(f"Backup written: {result.path} ({result.size:,} bytes, integrity_check ok)")
    if result.removed:
        names = ", ".join(p.name for p in result.removed)
        print(f"Removed {len(result.removed)} old backup(s): {names}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
