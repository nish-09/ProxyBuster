"""device binding (anti-proxy-sharing)

Revision ID: c2a7e94f1b83
Revises: b6f1c9d3a204
Create Date: 2026-09-24

Adds `device_bindings`: ties a client-reported device_id to the one student who first logged
in from it, so a DIFFERENT student can't also claim it (see
app/services/device_binding_service.py). A partial unique index enforces "at most one ACTIVE
binding per device_id" at the database level, mirroring the existing
uq_active_session_per_lecture pattern for attendance sessions (migration 9ebaabdae366).
Existing tables/data are untouched.
"""
from alembic import op
import sqlalchemy as sa

from app.core.types import GUID

# revision identifiers, used by Alembic.
revision = "c2a7e94f1b83"
down_revision = "b6f1c9d3a204"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "device_bindings",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("device_id", sa.String(length=255), nullable=False),
        sa.Column("student_id", GUID(), sa.ForeignKey("student_profiles.id"), nullable=False),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "REVOKED", name="device_binding_status"),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column("bound_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", GUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("revocation_reason", sa.String(length=500), nullable=True),
    )
    op.create_index("ix_device_bindings_device_id", "device_bindings", ["device_id"])
    op.create_index("ix_device_bindings_student_id", "device_bindings", ["student_id"])
    op.create_index(
        "uq_active_device_binding",
        "device_bindings",
        ["device_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )


def downgrade() -> None:
    op.drop_index("uq_active_device_binding", table_name="device_bindings")
    op.drop_index("ix_device_bindings_student_id", table_name="device_bindings")
    op.drop_index("ix_device_bindings_device_id", table_name="device_bindings")
    op.drop_table("device_bindings")
    sa.Enum(name="device_binding_status").drop(op.get_bind(), checkfirst=True)
