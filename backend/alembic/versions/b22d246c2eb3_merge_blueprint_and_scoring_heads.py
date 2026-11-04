"""merge blueprint and scoring heads

Revision ID: b22d246c2eb3
Revises: e3de7830b474, fc24c1890470
Create Date: 2026-11-04 19:17:00.977560

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b22d246c2eb3'
down_revision: Union[str, Sequence[str], None] = ('e3de7830b474', 'fc24c1890470')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
