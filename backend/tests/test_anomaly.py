import uuid
from datetime import datetime, timedelta, timezone

from app.models.academic import ClassDivision, Enrollment, Lecture, Subject
from app.models.attendance import AttendanceMethod, AttendanceRecord, AttendanceStatus
from app.models.security import SecurityEvent, SecurityEventSeverity
from app.models.user import ProfessorProfile, StudentProfile, User, UserRole
from app.core.security import hash_password
from app.services import anomaly_service


def _make_student(db_session, email):
    user = User(email=email, password_hash=hash_password("x"), full_name=email.split("@")[0], role=UserRole.STUDENT)
    db_session.add(user)
    db_session.flush()
    profile = StudentProfile(user_id=user.id, roll_number=email, program="B.Tech", semester=6)
    db_session.add(profile)
    db_session.flush()
    return user, profile


def _make_class(db_session):
    prof_user = User(email="anomaly-prof@college.edu", password_hash=hash_password("x"), full_name="Prof", role=UserRole.PROFESSOR)
    db_session.add(prof_user)
    db_session.flush()
    prof_profile = ProfessorProfile(user_id=prof_user.id, department="CS")
    db_session.add(prof_profile)
    db_session.flush()
    subject = Subject(code="AN-101", name="Anomaly Testing", credits=3)
    db_session.add(subject)
    db_session.flush()
    division = ClassDivision(subject_id=subject.id, professor_id=prof_profile.id, name="Div A", semester=6)
    db_session.add(division)
    db_session.flush()
    return division


def _make_lecture(db_session, division, start):
    lecture = Lecture(class_division_id=division.id, scheduled_start=start, scheduled_end=start + timedelta(hours=1))
    db_session.add(lecture)
    db_session.flush()
    return lecture


def test_insufficient_history_returns_zero_score(db_session):
    _, profile = _make_student(db_session, "sparse@college.edu")
    db_session.commit()
    score, reasons = anomaly_service.compute_rule_based_score(db_session, profile.id)
    assert score == 0.0
    assert reasons == ["Insufficient history for scoring"]


def test_concurrent_login_events_raise_score(db_session):
    user, profile = _make_student(db_session, "risky@college.edu")
    division = _make_class(db_session)
    db_session.add(Enrollment(student_id=profile.id, class_division_id=division.id))
    now = datetime.now(timezone.utc)
    for i in range(4):
        lecture = _make_lecture(db_session, division, now - timedelta(days=i, minutes=30))
        db_session.add(
            AttendanceRecord(
                student_id=profile.id,
                lecture_id=lecture.id,
                status=AttendanceStatus.PRESENT,
                method=AttendanceMethod.QR,
                marked_at=lecture.scheduled_start + timedelta(minutes=1),
            )
        )
    for _ in range(3):
        db_session.add(
            SecurityEvent(
                user_id=user.id,
                event_type="concurrent_login",
                description="test",
                severity=SecurityEventSeverity.MEDIUM,
                event_metadata={},
            )
        )
    db_session.commit()

    score, reasons = anomaly_service.compute_rule_based_score(db_session, profile.id)
    assert score > 0
    assert any("concurrent-login" in r for r in reasons)


def test_normal_student_low_score(db_session):
    _, profile = _make_student(db_session, "normal@college.edu")
    division = _make_class(db_session)
    db_session.add(Enrollment(student_id=profile.id, class_division_id=division.id))
    now = datetime.now(timezone.utc)
    for i in range(5):
        lecture = _make_lecture(db_session, division, now - timedelta(days=i, minutes=30))
        db_session.add(
            AttendanceRecord(
                student_id=profile.id,
                lecture_id=lecture.id,
                status=AttendanceStatus.PRESENT,
                method=AttendanceMethod.QR,
                marked_at=lecture.scheduled_start + timedelta(minutes=2),
            )
        )
    db_session.commit()

    score, reasons = anomaly_service.compute_rule_based_score(db_session, profile.id)
    assert score == 0.0
    assert reasons == ["No significant anomaly signals detected"]


def test_synchronized_pair_detected(db_session):
    _, profile_a = _make_student(db_session, "sync-a@college.edu")
    _, profile_b = _make_student(db_session, "sync-b@college.edu")
    division = _make_class(db_session)
    db_session.add(Enrollment(student_id=profile_a.id, class_division_id=division.id))
    db_session.add(Enrollment(student_id=profile_b.id, class_division_id=division.id))
    now = datetime.now(timezone.utc)

    for i in range(4):
        lecture = _make_lecture(db_session, division, now - timedelta(days=i, minutes=30))
        base = lecture.scheduled_start + timedelta(minutes=5)
        db_session.add(
            AttendanceRecord(
                student_id=profile_a.id,
                lecture_id=lecture.id,
                status=AttendanceStatus.PRESENT,
                method=AttendanceMethod.QR,
                marked_at=base,
            )
        )
        db_session.add(
            AttendanceRecord(
                student_id=profile_b.id,
                lecture_id=lecture.id,
                status=AttendanceStatus.PRESENT,
                method=AttendanceMethod.QR,
                marked_at=base + timedelta(seconds=2),
            )
        )
    db_session.commit()

    pairs = anomaly_service.find_synchronized_pairs(db_session, class_division_id=division.id)
    assert len(pairs) == 1
    pair = pairs[0]
    assert pair["sync_count"] == 4
    assert {pair["student_a"], pair["student_b"]} == {profile_a.id, profile_b.id}
    assert pair["risk"] in ("medium", "high")

    score, reasons = anomaly_service.compute_rule_based_score(db_session, profile_a.id)
    assert score > 0
    assert any("Synchronized attendance" in r for r in reasons)
