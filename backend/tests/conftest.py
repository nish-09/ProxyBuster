import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("QR_SIGNING_SECRET", "test-qr-signing-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_unused_placeholder.db")
os.environ.setdefault("PROFESSOR_INVITE_CODE", "test-professor-invite-code")

TEST_INVITE_CODE = os.environ["PROFESSOR_INVITE_CODE"]

from app.core.db import Base, get_db  # noqa: E402
from app.core.rate_limit import limiter  # noqa: E402
from app.main import app  # noqa: E402
from app.models.academic import ClassDivision, Enrollment, Lecture, Subject  # noqa: E402
from app.models.user import ProfessorProfile, StudentProfile  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Every test hits the API from the same TestClient IP; without resetting between
    tests, slowapi's shared in-memory counters would make later tests fail with 429s
    that have nothing to do with what that test is actually checking. Rate limiting
    itself stays real/enforced (see test_rate_limit.py) — this only isolates tests."""
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture()
def db_session_factory(tmp_path):
    db_path = tmp_path / f"test_{uuid.uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    yield TestingSessionLocal
    engine.dispose()


@pytest.fixture()
def db_session(db_session_factory):
    session = db_session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session_factory):
    def override_get_db():
        session = db_session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)


# --- Registration / login helpers -------------------------------------------------


def register_student(client, *, email="student@college.edu", password="Password123!", full_name="Test Student",
                      roll_number="R001", program="B.Tech CS", semester=6):
    resp = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": full_name,
            "role": "student",
            "roll_number": roll_number,
            "program": program,
            "semester": semester,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def register_professor(client, *, email="prof@college.edu", password="Password123!", full_name="Test Professor",
                        department="Computer Science", invite_code=TEST_INVITE_CODE):
    resp = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": full_name,
            "role": "professor",
            "department": department,
            "invite_code": invite_code,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def login(client, email, password="Password123!", device_id=None):
    resp = client.post("/api/auth/login", json={"email": email, "password": password, "device_id": device_id})
    return resp


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def student_and_token(client):
    register_student(client)
    resp = login(client, "student@college.edu")
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.fixture()
def professor_and_token(client):
    register_professor(client)
    resp = login(client, "prof@college.edu")
    assert resp.status_code == 200, resp.text
    return resp.json()


def make_admin(db_session, *, email="admin@college.edu", password="Password123!", full_name="Test Admin"):
    """Admins are never created via the public /auth/register endpoint (no invite-code-style
    gate exists for admin — they're provisioned out-of-band, e.g. directly in the DB or by
    another admin via the admin API). Tests create one directly."""
    from app.core.security import hash_password
    from app.models.user import User, UserRole

    user = User(email=email, password_hash=hash_password(password), full_name=full_name, role=UserRole.ADMIN)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def admin_and_token(client, db_session_factory):
    db_session = db_session_factory()
    try:
        make_admin(db_session)
    finally:
        db_session.close()
    resp = login(client, "admin@college.edu")
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- Direct DB fixtures for academic setup -----------------------------------------


def make_class_setup(db_session, professor_user_id, student_user_id, *, lecture_start=None):
    """Creates a Subject/ClassDivision/Enrollment/Lecture for the given already-registered
    professor & student users, and enrolls the student. Returns dict of created ids."""
    from datetime import datetime, timedelta, timezone

    professor_profile = db_session.query(ProfessorProfile).filter(ProfessorProfile.user_id == professor_user_id).first()
    student_profile = db_session.query(StudentProfile).filter(StudentProfile.user_id == student_user_id).first()

    subject = Subject(code="CS-999", name="Test Subject", credits=3)
    db_session.add(subject)
    db_session.flush()

    class_division = ClassDivision(
        subject_id=subject.id, professor_id=professor_profile.id, name="Div A", semester=6, room="Room 1"
    )
    db_session.add(class_division)
    db_session.flush()

    enrollment = Enrollment(student_id=student_profile.id, class_division_id=class_division.id)
    db_session.add(enrollment)

    if lecture_start is None:
        lecture_start = datetime.now(timezone.utc) - timedelta(minutes=5)
    lecture = Lecture(
        class_division_id=class_division.id,
        topic="Intro",
        scheduled_start=lecture_start,
        scheduled_end=lecture_start + timedelta(hours=1),
        room="Room 1",
    )
    db_session.add(lecture)
    db_session.commit()

    return {
        "professor_profile_id": professor_profile.id,
        "student_profile_id": student_profile.id,
        "subject_id": subject.id,
        "class_division_id": class_division.id,
        "lecture_id": lecture.id,
    }
