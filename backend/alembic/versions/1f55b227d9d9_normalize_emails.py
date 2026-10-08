"""Normalize emails to trimmed lower-case and enforce it with CHECK constraints.

Revision ID: 1f55b227d9d9
Revises: 2d57638c6ad3
Create Date: 2026-10-02 07:12:42.570373

Before this, ``Chidi@x.com`` and ``chidi@x.com`` were two different accounts
and an invite to one never matched a user registered as the other. Existing
rows are lower-cased and trimmed, and the database then refuses any
non-normalized value (08_DECISIONS.md 2026-10-02).

Fails loudly, with the offending addresses, if two existing users differ
only by case — those need a human decision (merge or remove) before this
can run, and silently picking one would be wrong.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1f55b227d9d9'
down_revision: Union[str, Sequence[str], None] = '2d57638c6ad3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Normalize existing emails, then add the CHECK constraints."""
    bind = op.get_bind()

    collisions = bind.execute(sa.text(
        "SELECT lower(btrim(email)) AS normalized, array_agg(email) AS originals "
        "FROM users GROUP BY 1 HAVING count(*) > 1"
    )).fetchall()
    if collisions:
        details = "; ".join(f"{row.normalized}: {list(row.originals)}" for row in collisions)
        raise RuntimeError(
            "Cannot normalize emails: these existing accounts differ only by "
            f"case/whitespace and must be merged or removed first — {details}"
        )

    # Two pending invites for the same org + person that only differ by case
    # would both become the same address. Keep the newest, retire the rest.
    op.execute(sa.text(
        "UPDATE invites SET is_used = true WHERE is_used = false AND id NOT IN ("
        "  SELECT DISTINCT ON (organization_id, lower(btrim(email))) id "
        "  FROM invites WHERE is_used = false "
        "  ORDER BY organization_id, lower(btrim(email)), created_at DESC"
        ")"
    ))

    op.execute(sa.text("UPDATE users SET email = lower(btrim(email)) WHERE email <> lower(btrim(email))"))
    op.execute(sa.text("UPDATE invites SET email = lower(btrim(email)) WHERE email <> lower(btrim(email))"))
    op.execute(sa.text(
        "UPDATE employees SET work_email = lower(btrim(work_email)) "
        "WHERE work_email <> lower(btrim(work_email))"
    ))

    op.create_check_constraint('check_user_email_normalized', 'users', 'email = lower(btrim(email))')
    op.create_check_constraint('check_invite_email_normalized', 'invites', 'email = lower(btrim(email))')
    op.create_check_constraint(
        'check_employee_work_email_normalized', 'employees', 'work_email = lower(btrim(work_email))'
    )


def downgrade() -> None:
    """Drop the CHECK constraints (the lower-cased data is left as it is)."""
    op.drop_constraint('check_employee_work_email_normalized', 'employees', type_='check')
    op.drop_constraint('check_invite_email_normalized', 'invites', type_='check')
    op.drop_constraint('check_user_email_normalized', 'users', type_='check')
