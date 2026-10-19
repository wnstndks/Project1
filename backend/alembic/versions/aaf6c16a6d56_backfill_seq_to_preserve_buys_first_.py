"""backfill seq to preserve buys-first order

Revision ID: aaf6c16a6d56
Revises: 2720e6161285
Create Date: 2026-10-19 16:55:04.235631

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import app.db.base


# revision identifiers, used by Alembic.
revision: str = 'aaf6c16a6d56'
down_revision: Union[str, Sequence[str], None] = '2720e6161285'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Keep the old buys-first replay for existing rows.

    Ordering changed from (date, buys before sells, id) to (date, seq, id). A same-day sell
    entered before a buy it depended on would now replay first and look like an oversell, so
    such sells get seq=1 (after the default 0 of the buys).
    """
    op.execute(
        """
        UPDATE transactions SET seq = 1
        WHERE side = 'sell' AND seq = 0 AND EXISTS (
            SELECT 1 FROM transactions b
            WHERE b.symbol = transactions.symbol
              AND b.trade_date = transactions.trade_date
              AND b.side = 'buy'
              AND b.id > transactions.id
        )
        """
    )


def downgrade() -> None:
    """Nothing to undo: seq is ignored by the old ordering."""
