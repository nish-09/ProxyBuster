"""classroom AI verification: reference photos, verifications, results, decisions, violations

Revision ID: b6f1c9d3a204
Revises: d5a8f0c2b7e1
Create Date: 2026-09-24

Adds the tables backing the new Classroom AI Verification + Attendance Discrepancy Detection
layer (see app/models/verification.py):

- student_reference_photos: one admin-managed reference photo per student, used only
  server-side to let the AI provider match a face to a known student. Its own table (not a
  column on student_profiles) so ordinary student queries never pull image bytes.
- classroom_verifications / classroom_verification_results: one row per "Verify Classroom"
  action and one row per enrolled-and-photographed student's AI read for it.
- verification_decisions: the professor's explicit call on a discrepancy — the only thing in
  this feature allowed to touch attendance state or create a violation.
- attendance_violations: a professor-confirmed violation, which doubles as the restriction
  record (restriction_start/end + status) so student/session/professor data isn't duplicated
  across two tables.

Existing tables/data are untouched.
"""
from alembic import op
import sqlalchemy as sa

from app.core.types import GUID

# revision identifiers, used by Alembic.
revision = "b6f1c9d3a204"
down_revision = "d5a8f0c2b7e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "student_reference_photos",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("student_id", GUID(), sa.ForeignKey("student_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("image_data", sa.LargeBinary(), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("uploaded_by_user_id", GUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("student_id", name="uq_student_reference_photos_student_id"),
    )

    op.create_table(
        "classroom_verifications",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("session_id", GUID(), sa.ForeignKey("attendance_sessions.id"), nullable=False),
        sa.Column("lecture_id", GUID(), sa.ForeignKey("lectures.id"), nullable=False),
        sa.Column("professor_id", GUID(), sa.ForeignKey("professor_profiles.id"), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PROCESSING", "COMPLETED", "FAILED", name="verification_status"),
            nullable=False,
            server_default="PROCESSING",
        ),
        sa.Column("image_count", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_classroom_verifications_session_id", "classroom_verifications", ["session_id"])
    op.create_index("ix_classroom_verifications_lecture_id", "classroom_verifications", ["lecture_id"])
    op.create_index("ix_classroom_verifications_professor_id", "classroom_verifications", ["professor_id"])

    op.create_table(
        "classroom_verification_results",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column(
            "verification_id", GUID(), sa.ForeignKey("classroom_verifications.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("student_id", GUID(), sa.ForeignKey("student_profiles.id"), nullable=False),
        sa.Column("qr_present", sa.Boolean(), nullable=False),
        sa.Column(
            "ai_status",
            sa.Enum("CONFIRMED", "HIGH_CONFIDENCE", "UNCERTAIN", "NOT_DETECTED", name="detection_status"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column(
            "discrepancy_type",
            sa.Enum(
                "ATTENDED_AND_DETECTED",
                "ATTENDED_NOT_DETECTED",
                "DETECTED_NOT_ATTENDED",
                "NONE",
                name="discrepancy_type",
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("verification_id", "student_id", name="uq_verification_student"),
    )
    op.create_index("ix_classroom_verification_results_verification_id", "classroom_verification_results", ["verification_id"])
    op.create_index("ix_classroom_verification_results_student_id", "classroom_verification_results", ["student_id"])

    op.create_table(
        "verification_decisions",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column(
            "result_id",
            GUID(),
            sa.ForeignKey("classroom_verification_results.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("professor_id", GUID(), sa.ForeignKey("professor_profiles.id"), nullable=False),
        sa.Column(
            "action",
            sa.Enum(
                "CONFIRMED_PRESENT", "ASKED_TO_SCAN", "DISMISSED", "VIOLATION", name="verification_decision_action"
            ),
            nullable=False,
        ),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("result_id", name="uq_verification_decisions_result_id"),
    )

    op.create_table(
        "attendance_violations",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("student_id", GUID(), sa.ForeignKey("student_profiles.id"), nullable=False),
        sa.Column("lecture_id", GUID(), sa.ForeignKey("lectures.id"), nullable=False),
        sa.Column("session_id", GUID(), sa.ForeignKey("attendance_sessions.id"), nullable=True),
        sa.Column("professor_id", GUID(), sa.ForeignKey("professor_profiles.id"), nullable=False),
        sa.Column(
            "verification_result_id", GUID(), sa.ForeignKey("classroom_verification_results.id"), nullable=True
        ),
        sa.Column(
            "reason",
            sa.Enum(
                "PROXY_ATTENDANCE",
                "NOT_PHYSICALLY_PRESENT",
                "UNAUTHORIZED_ATTENDANCE",
                "OTHER",
                name="violation_reason",
            ),
            nullable=False,
        ),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column(
            "status", sa.Enum("ACTIVE", "REVOKED", name="violation_status"), nullable=False, server_default="ACTIVE"
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("restriction_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("restriction_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", GUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("revocation_reason", sa.String(length=500), nullable=True),
    )
    op.create_index("ix_attendance_violations_student_id", "attendance_violations", ["student_id"])
    op.create_index("ix_attendance_violations_professor_id", "attendance_violations", ["professor_id"])
    op.create_index("ix_attendance_violations_restriction_end", "attendance_violations", ["restriction_end"])


def downgrade() -> None:
    op.drop_index("ix_attendance_violations_restriction_end", table_name="attendance_violations")
    op.drop_index("ix_attendance_violations_professor_id", table_name="attendance_violations")
    op.drop_index("ix_attendance_violations_student_id", table_name="attendance_violations")
    op.drop_table("attendance_violations")

    op.drop_table("verification_decisions")

    op.drop_index("ix_classroom_verification_results_student_id", table_name="classroom_verification_results")
    op.drop_index("ix_classroom_verification_results_verification_id", table_name="classroom_verification_results")
    op.drop_table("classroom_verification_results")

    op.drop_index("ix_classroom_verifications_professor_id", table_name="classroom_verifications")
    op.drop_index("ix_classroom_verifications_lecture_id", table_name="classroom_verifications")
    op.drop_index("ix_classroom_verifications_session_id", table_name="classroom_verifications")
    op.drop_table("classroom_verifications")

    op.drop_table("student_reference_photos")

    for enum_name in (
        "violation_status",
        "violation_reason",
        "verification_decision_action",
        "discrepancy_type",
        "detection_status",
        "verification_status",
    ):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
