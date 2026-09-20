"""Seed realistic DEVELOPMENT/STAGING data: professors, students, subjects, divisions,
enrollments, lectures. Never run this against production — see backend/scripts/reset_demo_data.py
for the safe, explicit production-data reset instead.

All identities use the RFC 2606 reserved @example.test domain and generic names/roll numbers
so this data can never be mistaken for a real person — do not seed real names or real emails
here, even for local testing.

Run with: python seed.py   (from backend/, with .env pointed at a dev/staging database)
"""
import random
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.core.time import ensure_utc
from app.models.academic import ClassDivision, Enrollment, Lecture, Subject
from app.models.user import ProfessorProfile, StudentProfile, User, UserRole

SUBJECTS = [
    ("CS-301", "Data Structures", 4),
    ("CS-302", "DBMS", 4),
    ("CS-303", "Operating Systems", 4),
    ("MA-202", "Mathematics IV", 3),
    ("CS-401", "Artificial Intelligence", 3),
]

PROFESSORS = [
    ("Professor One", "professor001@example.test", "Computer Science"),
    ("Professor Two", "professor002@example.test", "Computer Science"),
    ("Professor Three", "professor003@example.test", "Mathematics"),
]

STUDENT_NAMES = [f"Student {i:03d}" for i in range(1, 21)]


def _confirm_target_database() -> None:
    """Fake data must never silently land in a production database just because that's
    what DATABASE_URL happens to point at. Anything that isn't obviously local requires
    an explicit typed confirmation naming the actual host, unless --yes is passed."""
    if "--yes" in sys.argv:
        return
    host = urlsplit(get_settings().database_url.replace("postgresql+psycopg2", "postgresql")).hostname or ""
    if host in ("", "localhost", "127.0.0.1", "postgres"):
        return  # local dev / docker-compose service name — no confirmation needed

    print(f"DATABASE_URL points at host: {host!r}")
    print("This does not look like a local database. Seeding fake data here could pollute")
    print("a shared staging/production database.")
    answer = input(f"Type the host ({host}) to confirm you want to seed fake data into it: ")
    if answer.strip() != host:
        print("Confirmation did not match — aborting. No data was written.")
        sys.exit(1)


def run():
    if get_settings().is_production:
        sys.exit("Refusing to seed demo data: ENVIRONMENT=production. Use scripts/create_admin.py for the bootstrap admin.")
    _confirm_target_database()
    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == PROFESSORS[0][1]).first():
            print("Seed data already present, skipping.")
            return

        professors = []
        for name, email, dept in PROFESSORS:
            user = User(email=email, password_hash=hash_password("Password123!"), full_name=name, role=UserRole.PROFESSOR)
            db.add(user)
            db.flush()
            profile = ProfessorProfile(user_id=user.id, department=dept)
            db.add(profile)
            db.flush()
            professors.append(profile)

        subjects = []
        for code, name, credits in SUBJECTS:
            subj = Subject(code=code, name=name, credits=credits)
            db.add(subj)
            db.flush()
            subjects.append(subj)

        divisions = []
        for i, subj in enumerate(subjects):
            div = ClassDivision(
                subject_id=subj.id,
                professor_id=professors[i % len(professors)].id,
                name="Div A",
                semester=6,
                room=f"Room {200 + i}",
            )
            db.add(div)
            db.flush()
            divisions.append(div)

        students = []
        for i, name in enumerate(STUDENT_NAMES):
            email = f"student{i + 1:03d}@example.test"
            user = User(email=email, password_hash=hash_password("Password123!"), full_name=name, role=UserRole.STUDENT)
            db.add(user)
            db.flush()
            profile = StudentProfile(
                user_id=user.id,
                roll_number=f"BT23CS{100 + i}",
                program="B.Tech Computer Science",
                semester=6,
            )
            db.add(profile)
            db.flush()
            students.append(profile)

        for student in students:
            for div in divisions:
                db.add(Enrollment(student_id=student.id, class_division_id=div.id))

        now = datetime.now(timezone.utc)
        lectures_by_division = {}
        for div in divisions:
            lectures = []
            for day_offset in range(-14, 1):
                start = (now + timedelta(days=day_offset)).replace(hour=10, minute=0, second=0, microsecond=0)
                lecture = Lecture(
                    class_division_id=div.id,
                    topic=None,
                    scheduled_start=start,
                    scheduled_end=start + timedelta(hours=1),
                    room=div.room,
                )
                db.add(lecture)
                lectures.append(lecture)
            db.flush()
            lectures_by_division[div.id] = lectures

        from app.models.attendance import AttendanceMethod, AttendanceRecord, AttendanceStatus

        for div in divisions:
            for lecture in lectures_by_division[div.id]:
                if lecture.scheduled_start > now:
                    continue
                for student in students:
                    roll = random.random()
                    status = AttendanceStatus.PRESENT if roll < 0.85 else (
                        AttendanceStatus.LATE if roll < 0.92 else AttendanceStatus.ABSENT
                    )
                    if status == AttendanceStatus.ABSENT:
                        continue
                    db.add(
                        AttendanceRecord(
                            student_id=student.id,
                            lecture_id=lecture.id,
                            status=status,
                            method=AttendanceMethod.QR,
                            marked_at=lecture.scheduled_start + timedelta(minutes=random.randint(0, 15)),
                        )
                    )

        db.commit()

        # --- Security events -------------------------------------------------
        from app.models.security import (
            AnomalyScore,
            Cooldown,
            SecurityEvent,
            SecurityEventSeverity,
            SecurityEventStatus,
        )

        flagged_student = students[0]  # Student 001
        flagged_user = flagged_student.user
        second_flagged = students[2]  # Student 003

        db.add_all(
            [
                SecurityEvent(
                    user_id=flagged_user.id,
                    event_type="concurrent_login",
                    description="New login detected while a previous session was still active; prior session(s) revoked.",
                    severity=SecurityEventSeverity.MEDIUM,
                    event_metadata={"revoked_session_ids": ["seed-demo-session"], "new_ip": "10.0.0.42"},
                    status=SecurityEventStatus.OPEN,
                ),
                SecurityEvent(
                    user_id=flagged_user.id,
                    event_type="concurrent_login",
                    description="New login detected while a previous session was still active; prior session(s) revoked.",
                    severity=SecurityEventSeverity.MEDIUM,
                    event_metadata={"revoked_session_ids": ["seed-demo-session-2"], "new_ip": "10.0.0.77"},
                    status=SecurityEventStatus.OPEN,
                ),
                SecurityEvent(
                    user_id=second_flagged.user.id,
                    event_type="rapid_device_switch",
                    description="Three distinct devices used to access the account within a 10 minute window.",
                    severity=SecurityEventSeverity.HIGH,
                    event_metadata={"device_count": 3, "window_minutes": 10},
                    status=SecurityEventStatus.OPEN,
                ),
            ]
        )

        # --- Active cooldowns (for the Cooldown Monitor / student lock screen) ---
        cooldown_students = students[-2:]  # Student 019, Student 020
        for offset_minutes, student in zip((45, 22), cooldown_students):
            db.add(
                Cooldown(
                    student_id=student.id,
                    expires_at=now + timedelta(minutes=offset_minutes),
                    reason="manual_logout",
                )
            )

        # --- Deliberate synchronized-attendance pattern (anomaly detection demo) ---
        from app.models.attendance import AttendanceRecord as _AR

        sync_pair = (students[3], students[4])  # Student 004 & Student 005
        sync_hits = 0
        for div in divisions:
            for lecture in lectures_by_division[div.id]:
                lecture_start = ensure_utc(lecture.scheduled_start)
                if lecture_start > now:
                    continue
                if sync_hits >= 6:
                    break
                base_marked_at = lecture_start + timedelta(minutes=random.randint(2, 10))
                records = (
                    db.query(_AR)
                    .filter(_AR.lecture_id == lecture.id, _AR.student_id.in_([s.id for s in sync_pair]))
                    .all()
                )
                if len(records) == 2:
                    records[0].marked_at = base_marked_at
                    records[1].marked_at = base_marked_at + timedelta(seconds=random.randint(1, 3))
                    sync_hits += 1

        db.commit()

        print(f"Seeded {len(professors)} professors, {len(students)} students, {len(subjects)} subjects, "
              f"{len(divisions)} divisions, attendance history for the last 14 days.")
        print(f"Security events: 2x concurrent_login for {flagged_user.full_name}, "
              f"1x rapid_device_switch for {second_flagged.user.full_name}.")
        print(f"Active cooldowns (locked out right now): "
              f"{cooldown_students[0].user.full_name} ({cooldown_students[0].user.email}), "
              f"{cooldown_students[1].user.full_name} ({cooldown_students[1].user.email}).")
        print(f"Synchronized-attendance pattern seeded across {sync_hits} lectures for "
              f"{sync_pair[0].user.full_name} & {sync_pair[1].user.full_name} "
              "(should surface as a high-risk pair in anomaly detection).")
        print("All seeded users have password: Password123!")
    finally:
        db.close()


if __name__ == "__main__":
    run()
