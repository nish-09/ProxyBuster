"""Proves the "at most one active session per lecture" rule is enforced at the database
level (a partial unique index — see migration 9ebaabdae366), not only by the read-then-write
check in attendance_service.create_session. This is what actually protects against two
concurrent requests racing past that Python check at the same time."""
import pytest
from sqlalchemy.exc import IntegrityError

from app.models.attendance import AttendanceSession, SessionStatus
from tests.conftest import make_class_setup


def test_db_rejects_second_active_session_for_same_lecture_bypassing_service_layer(
    db_session, professor_and_token, student_and_token
):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])

    first = AttendanceSession(
        lecture_id=setup["lecture_id"], professor_id=setup["professor_profile_id"], status=SessionStatus.ACTIVE
    )
    db_session.add(first)
    db_session.commit()

    second = AttendanceSession(
        lecture_id=setup["lecture_id"], professor_id=setup["professor_profile_id"], status=SessionStatus.ACTIVE
    )
    db_session.add(second)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_db_allows_new_active_session_after_previous_one_closed(db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])

    first = AttendanceSession(
        lecture_id=setup["lecture_id"], professor_id=setup["professor_profile_id"], status=SessionStatus.ACTIVE
    )
    db_session.add(first)
    db_session.commit()

    first.status = SessionStatus.CLOSED
    db_session.commit()

    second = AttendanceSession(
        lecture_id=setup["lecture_id"], professor_id=setup["professor_profile_id"], status=SessionStatus.ACTIVE
    )
    db_session.add(second)
    db_session.commit()  # should not raise — only one row has status = 'ACTIVE' at a time
