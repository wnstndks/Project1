"""invalidate symbol syncs stored in local time

Revision ID: 9f363af5cd85
Revises: e67d73f03bf8
Create Date: 2026-10-21 10:47:40.492635

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import app.db.base


# revision identifiers, used by Alembic.
revision: str = '9f363af5cd85'
down_revision: Union[str, Sequence[str], None] = 'e67d73f03bf8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Forget when each symbol was last synced (ISSUE-001, DECISIONS.md D-016).

    `symbol_syncs.synced_at` used to be local time (KST) and is now naive UTC; old rows
    cannot be told apart from new ones, and finality is judged from this value. Deleting the
    sync records makes the cache re-fetch each symbol on its next read. Cached bars in
    `price_bars` stay: the re-fetch overwrites them and drops unfinished ones.
    """
    op.execute("DELETE FROM symbol_syncs")


def downgrade() -> None:
    """Nothing to restore: the deleted rows only told the cache what it had already fetched."""
