"""NOT NULL on defaulted columns; users.email as a unique index

Revision ID: d5a8f0c2b7e1
Revises: c7d2e4a19b53
Create Date: 2026-09-19

Brings the database in line with the models (`alembic check` is clean afterwards):

1. 14 columns that always receive a value (server_default now()/enum default) were created
   nullable. Any NULL there would crash the ORM/serialisation (e.g. a NULL marked_at). Existing
   NULLs, if any, are backfilled first, then the columns are made NOT NULL.
2. users.email was enforced by a UNIQUE constraint plus a separate non-unique index; the model
   declares a single unique index. Swapped atomically (DDL is transactional in PostgreSQL), so
   uniqueness is never absent.
"""
from alembic import op

revision = "d5a8f0c2b7e1"
down_revision = "c7d2e4a19b53"
branch_labels = None
depends_on = None

_TIMESTAMPS = [
    ("anomaly_scores", "computed_at"),
    ("attendance_records", "marked_at"),
    ("attendance_sessions", "started_at"),
    ("attendance_tokens", "issued_at"),
    ("cooldowns", "started_at"),
    ("device_sessions", "login_at"),
    ("enrollments", "created_at"),
    ("lectures", "created_at"),
    ("manual_attendance", "created_at"),
    ("security_events", "created_at"),
    ("users", "created_at"),
    ("users", "updated_at"),
]
_ENUM_DEFAULTS = [("security_events", "severity", "LOW"), ("security_events", "status", "OPEN")]


def upgrade() -> None:
    for table, column in _TIMESTAMPS:
        op.execute(f"UPDATE {table} SET {column} = now() WHERE {column} IS NULL")
        op.alter_column(table, column, nullable=False)
    for table, column, default in _ENUM_DEFAULTS:
        op.execute(f"UPDATE {table} SET {column} = '{default}' WHERE {column} IS NULL")
        op.alter_column(table, column, nullable=False)

    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_index("ix_users_email", table_name="users")
    op.create_index("ix_users_email", "users", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    op.create_index("ix_users_email", "users", ["email"], unique=False)
    op.create_unique_constraint("uq_users_email", "users", ["email"])

    for table, column, _default in _ENUM_DEFAULTS:
        op.alter_column(table, column, nullable=True)
    for table, column in _TIMESTAMPS:
        op.alter_column(table, column, nullable=True)
