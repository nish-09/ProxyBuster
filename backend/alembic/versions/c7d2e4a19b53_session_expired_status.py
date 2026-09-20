"""attendance session EXPIRED status

Revision ID: c7d2e4a19b53
Revises: 9ebaabdae366
Create Date: 2026-09-19

Adds 'EXPIRED' to the session_status enum so a session that ran out of time is
distinguishable from one the professor stopped (CLOSED). Existing rows are untouched;
already-closed sessions keep their CLOSED status.
"""
from alembic import op

revision = "c7d2e4a19b53"
down_revision = "9ebaabdae366"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Postgres 12+ allows ADD VALUE inside a transaction as long as the new value isn't
    # used in the same transaction — it isn't.
    op.execute("ALTER TYPE session_status ADD VALUE IF NOT EXISTS 'EXPIRED'")


def downgrade() -> None:
    # Postgres cannot drop a single enum value without recreating the type. Fold EXPIRED
    # rows back into CLOSED so older code can still read them; the (unused) enum value
    # itself is left in place.
    op.execute("UPDATE attendance_sessions SET status = 'CLOSED' WHERE status = 'EXPIRED'")
