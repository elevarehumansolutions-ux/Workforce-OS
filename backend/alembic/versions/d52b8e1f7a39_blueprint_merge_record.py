"""Remember what a blueprint merge changed, so it can be undone.

Revision ID: d52b8e1f7a39
Revises: c41a9d7e2b85
Create Date: 2026-11-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd52b8e1f7a39'
down_revision: Union[str, Sequence[str], None] = 'c41a9d7e2b85'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('blueprint_items', sa.Column('merge_record', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('blueprint_items', 'merge_record')
