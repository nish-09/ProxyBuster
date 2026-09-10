"""admin role, FK indexes, one-active-session-per-lecture constraint

Revision ID: 9ebaabdae366
Revises: a84c266ff0fd
Create Date: 2026-09-10

Three independent changes, bundled because they were all identified in the same
production-readiness audit:

1. Adds 'ADMIN' to the user_role enum (new academic-data-management role).
2. Adds indexes on FK columns that are filtered on directly in hot-path queries
   (professor dashboard, attendance sheet, analytics) but weren't already covered
   by an existing unique constraint's leftmost column. Columns already covered by
   a composite unique constraint (e.g. enrollments.student_id, by
   uq_student_division) are deliberately skipped to avoid a redundant index.
3. Adds a partial unique index on attendance_sessions.lecture_id (rows where
   status = 'ACTIVE' only), enforcing "at most one active session per lecture"
   at the database level instead of relying solely on a Python
   SELECT-then-INSERT check, which is race-prone under concurrent requests.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "9ebaabdae366"
down_revision = "a84c266ff0fd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Postgres 12+ allows ALTER TYPE ... ADD VALUE inside a transaction as long as the
    # new value isn't used in the same transaction, which is the case here.
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'ADMIN'")

    op.create_index("ix_attendance_tokens_session_id", "attendance_tokens", ["session_id"])
    op.create_index("ix_attendance_records_lecture_id", "attendance_records", ["lecture_id"])
    op.create_index("ix_class_divisions_professor_id", "class_divisions", ["professor_id"])
    op.create_index("ix_enrollments_class_division_id", "enrollments", ["class_division_id"])
    op.create_index("ix_lectures_class_division_id", "lectures", ["class_division_id"])
    op.create_index("ix_device_sessions_user_id", "device_sessions", ["user_id"])
    op.create_index("ix_cooldowns_student_id", "cooldowns", ["student_id"])
    op.create_index("ix_security_events_user_id", "security_events", ["user_id"])
    op.create_index("ix_anomaly_scores_student_id", "anomaly_scores", ["student_id"])

    op.create_index(
        "uq_active_session_per_lecture",
        "attendance_sessions",
        ["lecture_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )


def downgrade() -> None:
    op.drop_index("uq_active_session_per_lecture", table_name="attendance_sessions")
    op.drop_index("ix_anomaly_scores_student_id", table_name="anomaly_scores")
    op.drop_index("ix_security_events_user_id", table_name="security_events")
    op.drop_index("ix_cooldowns_student_id", table_name="cooldowns")
    op.drop_index("ix_device_sessions_user_id", table_name="device_sessions")
    op.drop_index("ix_lectures_class_division_id", table_name="lectures")
    op.drop_index("ix_enrollments_class_division_id", table_name="enrollments")
    op.drop_index("ix_class_divisions_professor_id", table_name="class_divisions")
    op.drop_index("ix_attendance_records_lecture_id", table_name="attendance_records")
    op.drop_index("ix_attendance_tokens_session_id", table_name="attendance_tokens")

    # Postgres cannot drop a single enum value without recreating the type (and any
    # column/index depending on it), so removing 'ADMIN' on downgrade is intentionally
    # not implemented. If you must fully reverse this migration, recreate user_role
    # without 'ADMIN' by hand after confirming no ADMIN users exist.
