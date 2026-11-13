"""Remember the invitee's name on an invite, so the accept page can prefill it.

Revision ID: e7a41c9b3d26
Revises: d52b8e1f7a39
Create Date: 2026-11-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7a41c9b3d26'
down_revision: Union[str, Sequence[str], None] = 'd52b8e1f7a39'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('invites', sa.Column('invitee_name', sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('invites', 'invitee_name')
