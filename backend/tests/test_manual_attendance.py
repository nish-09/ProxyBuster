from app.models.attendance import AttendanceRecord, ManualAttendance
from tests.conftest import auth_headers, login, make_class_setup, register_student


def test_manual_mark_creates_record_and_audit_row(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])

    resp = client.post(
        "/api/attendance/manual",
        json={
            "student_id": str(setup["student_profile_id"]),
            "lecture_id": str(setup["lecture_id"]),
            "status": "present",
            "reason": "Phone battery died, verified in person",
        },
        headers=auth_headers(professor_and_token["access_token"]),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["previous_status"] is None
    assert body["new_status"] == "present"

    record = db_session.query(AttendanceRecord).filter(
        AttendanceRecord.student_id == setup["student_profile_id"],
        AttendanceRecord.lecture_id == setup["lecture_id"],
    ).first()
    assert record is not None
    assert record.method.value == "manual"
    assert record.status.value == "present"

    audit_rows = db_session.query(ManualAttendance).filter(
        ManualAttendance.attendance_record_id == record.id
    ).all()
    assert len(audit_rows) == 1
    assert audit_rows[0].reason == "Phone battery died, verified in person"


def test_manual_mark_updates_existing_record_with_previous_status(
    client, db_session, professor_and_token, student_and_token
):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])

    client.post(
        "/api/attendance/manual",
        json={
            "student_id": str(setup["student_profile_id"]),
            "lecture_id": str(setup["lecture_id"]),
            "status": "present",
            "reason": "Initial mark",
        },
        headers=auth_headers(professor_and_token["access_token"]),
    )
    second = client.post(
        "/api/attendance/manual",
        json={
            "student_id": str(setup["student_profile_id"]),
            "lecture_id": str(setup["lecture_id"]),
            "status": "absent",
            "reason": "Correction after review",
        },
        headers=auth_headers(professor_and_token["access_token"]),
    )
    assert second.status_code == 200
    assert second.json()["previous_status"] == "present"
    assert second.json()["new_status"] == "absent"

    audit_rows = db_session.query(ManualAttendance).all()
    assert len(audit_rows) == 2


def test_manual_mark_requires_enrollment(client, db_session, professor_and_token, student_and_token):
    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    register_student(client, email="not-enrolled@college.edu", roll_number="R888")
    outsider_token = login(client, "not-enrolled@college.edu").json()

    from app.models.user import StudentProfile

    outsider_profile = db_session.query(StudentProfile).filter(
        StudentProfile.user_id == outsider_token["user_id"]
    ).first()

    resp = client.post(
        "/api/attendance/manual",
        json={
            "student_id": str(outsider_profile.id),
            "lecture_id": str(setup["lecture_id"]),
            "status": "present",
            "reason": "Attempted mark for non-enrolled student",
        },
        headers=auth_headers(professor_and_token["access_token"]),
    )
    assert resp.status_code == 403


def test_manual_mark_by_non_owning_professor_forbidden(client, db_session, professor_and_token, student_and_token):
    from tests.conftest import register_professor

    setup = make_class_setup(db_session, professor_and_token["user_id"], student_and_token["user_id"])
    register_professor(client, email="other-manual-prof@college.edu")
    other_prof_token = login(client, "other-manual-prof@college.edu").json()

    resp = client.post(
        "/api/attendance/manual",
        json={
            "student_id": str(setup["student_profile_id"]),
            "lecture_id": str(setup["lecture_id"]),
            "status": "present",
            "reason": "Not my class",
        },
        headers=auth_headers(other_prof_token["access_token"]),
    )
    assert resp.status_code == 403
