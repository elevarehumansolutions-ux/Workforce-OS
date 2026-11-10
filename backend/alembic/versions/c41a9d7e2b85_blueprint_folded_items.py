"""Let the blueprint hold 'folded' items: a department or role another one covers.

Revision ID: c41a9d7e2b85
Revises: fb48710b400f
Create Date: 2026-11-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c41a9d7e2b85'
down_revision: Union[str, Sequence[str], None] = 'fb48710b400f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('blueprint_items', sa.Column('folded_into_ref', sa.String(length=20), nullable=True))

    # Autogenerate does not see CHECK rules: widen the list of kinds by hand.
    op.execute("ALTER TABLE blueprint_items DROP CONSTRAINT check_blueprint_item_kind")
    op.execute(
        "ALTER TABLE blueprint_items ADD CONSTRAINT check_blueprint_item_kind CHECK "
        "(kind IN ('department', 'position', 'objective', 'key_result', 'kpi', "
        "'rename_department', 'rename_position', 'review_note', 'folded'))"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER TABLE blueprint_items DROP CONSTRAINT check_blueprint_item_kind")
    # The old rule would reject these rows, so they go before it comes back.
    op.execute("DELETE FROM blueprint_items WHERE kind = 'folded'")
    op.execute(
        "ALTER TABLE blueprint_items ADD CONSTRAINT check_blueprint_item_kind CHECK "
        "(kind IN ('department', 'position', 'objective', 'key_result', 'kpi', "
        "'rename_department', 'rename_position', 'review_note'))"
    )
    op.drop_column('blueprint_items', 'folded_into_ref')
