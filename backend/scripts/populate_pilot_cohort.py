"""One-time population of a realistic pilot cohort — entirely through the SAME admin
service functions the Admin Panel calls (app.services.admin_service), never raw SQL.

WHAT THIS DOES, using only existing service functions:
  - update_student()      — updates program/semester on all 60 EXISTING student profiles
                             so they share one cohort. Never touches email, password,
                             roll_number, or full_name (AdminUpdateStudentRequest doesn't
                             even accept those fields) — identities are fully preserved.
  - create_subject()      — creates the subjects that don't already exist (by code).
  - create_professor()    — creates new professor accounts (unique emails only).
  - create_division()     — one ClassDivision per subject, all named the same division.
  - bulk_enroll()         — enrolls all 60 students into each division.
  - create_lecture()      — a couple of near-future lectures per division, so "Start
                             Session" has something real to attach to. No AttendanceRecord
                             or AttendanceSession rows are ever created by this script —
                             attendance itself is left for you to test through the real
                             QR flow, exactly as requested.

WHAT THIS PRESERVES (verified against the live DB before writing anything):
  - The existing professor account (darshikasinghhh@gmail.com / "Darshika SIngh") — never
    updated, deleted, or recreated. It is only assigned as professor_id on one division,
    the same relationship an admin would set by picking her from a dropdown.
  - The existing subject (code "CS-1", "Data Structures") — reused as-is, not duplicated.
  - All 60 existing student accounts — never deleted or recreated; only their
    `program`/`semester` fields are updated via update_student(), through the exact same
    validated path as an admin editing a student in the UI.

IDEMPOTENT: every step first checks what already exists (by code/email/name/division) and
skips or reuses it — safe to re-run without creating duplicates.

A NOTE ON WHAT COULDN'T BE STORED: the current data model (StudentProfile) has no
"college" or "academic year" field at all — only `roll_number`, `program`, `semester`. Per
your instruction not to modify the schema, "Thadomal Shahani Engineering College" and
"2026-27" have nowhere to be recorded; only course/branch (via `program`) and semester/
division (via `semester` + ClassDivision) are representable. This is reported, not silently
dropped — see the printed plan and the final report.

HOW TO USE:
  python scripts/populate_pilot_cohort.py             # dry run (default) — shows the plan
  python scripts/populate_pilot_cohort.py --execute    # writes, with host confirmation
"""
import argparse
import secrets
import string
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.models.academic import ClassDivision, Enrollment, Lecture, Subject  # noqa: E402
from app.models.user import ProfessorProfile, StudentProfile, User, UserRole  # noqa: E402
from app.schemas.admin import (  # noqa: E402
    AdminCreateDivisionRequest,
    AdminCreateLectureRequest,
    AdminCreateProfessorRequest,
    AdminCreateSubjectRequest,
    AdminUpdateStudentRequest,
)
from app.services import admin_service  # noqa: E402

# ---------------------------------------------------------------------------------------
PILOT_PROGRAM = "B.Tech Artificial Intelligence and Data Science"
PILOT_SEMESTER = 3  # 2nd Year, 1st semester — see docstring: "2nd Year" has no dedicated
                     # field, this is the semester-number representation of it.
DIVISION_NAME = "A"
ROOM = "AI-DS 301"
DEPARTMENT = "Artificial Intelligence and Data Science"

EXISTING_SUBJECT_CODE = "CS-1"  # already present — reused, not duplicated

NEW_SUBJECTS = [
    ("AIDS-201", "Database Management Systems", 4),
    ("AIDS-202", "Operating Systems", 4),
    ("AIDS-203", "Probability and Statistics", 3),
    ("AIDS-204", "Machine Learning", 4),
]

NEW_PROFESSORS = [
    ("Dr. Rajesh Kulkarni", "rajesh.kulkarni@example.test"),
    ("Dr. Sneha Deshmukh", "sneha.deshmukh@example.test"),
    ("Dr. Anand Rao", "anand.rao@example.test"),
    ("Dr. Priyanka Joshi", "priyanka.joshi@example.test"),
]

LECTURES_PER_DIVISION = 2
PASSWORD_ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*"


def _gen_password(length: int = 14) -> str:
    while True:
        pw = "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(length))
        if (
            any(c.islower() for c in pw)
            and any(c.isupper() for c in pw)
            and any(c.isdigit() for c in pw)
            and any(c in "!@#$%^&*" for c in pw)
        ):
            return pw


def _confirm_target_host(host: str, assume_yes: bool) -> None:
    if assume_yes or host in ("", "localhost", "127.0.0.1", "postgres"):
        return
    print(f"DATABASE_URL points at host: {host!r}")
    answer = input(f"Type the host ({host}) to confirm you want to populate the pilot cohort here: ")
    if answer.strip() != host:
        print("Confirmation did not match — aborting. No data was written.")
        sys.exit(1)


def _write_credentials_file(professors: list[dict]) -> Path:
    out_dir = Path(__file__).resolve().parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"pilot_professor_credentials_{stamp}.md"
    lines = [
        "# ProxyBuster pilot cohort — newly created professor credentials",
        "",
        f"Generated: {stamp}",
        "",
        "**Do not commit this file. Do not share it outside your own records.**",
        "",
        "| Name | Email | Password |",
        "| ---- | ----- | -------- |",
    ]
    for p in professors:
        lines.append(f"| {p['full_name']} | {p['email']} | {p['password']} |")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def run(execute: bool, assume_yes: bool) -> None:
    settings = get_settings()
    host = urlsplit(settings.database_url.replace("postgresql+psycopg2", "postgresql")).hostname or "unknown"

    db = SessionLocal()
    try:
        # ---------- Plan ----------
        existing_professors = db.query(ProfessorProfile).all()
        existing_professor_emails = {db.get(User, p.user_id).email for p in existing_professors}
        student_profiles = db.query(StudentProfile).all()
        existing_subject = db.query(Subject).filter(Subject.code == EXISTING_SUBJECT_CODE).first()

        to_create_professors = [
            (name, email) for name, email in NEW_PROFESSORS if email not in existing_professor_emails
        ]
        to_create_subjects = [
            (code, name, credits)
            for code, name, credits in NEW_SUBJECTS
            if db.query(Subject).filter(Subject.code == code).first() is None
        ]

        print("=" * 76)
        print(f"ProxyBuster pilot cohort population — target database host: {host!r}")
        print("=" * 76)
        print(f"Existing students to update (program/semester only): {len(student_profiles)}")
        print(f"Existing professors preserved: {len(existing_professors)} ({', '.join(existing_professor_emails)})")
        print(f"Existing subject reused: {EXISTING_SUBJECT_CODE!r}" if existing_subject else "WARNING: expected existing subject CS-1 not found")
        print(f"New professors to create: {len(to_create_professors)} -> {[e for _, e in to_create_professors]}")
        print(f"New subjects to create: {len(to_create_subjects)} -> {[c for c, _, _ in to_create_subjects]}")
        print(f"Divisions to ensure: 5 (one per subject), all named {DIVISION_NAME!r}, semester {PILOT_SEMESTER}")
        print(f"Enrollments to ensure: up to {len(student_profiles) * 5} (60 students x 5 divisions)")
        print(f"Lectures to create: up to {LECTURES_PER_DIVISION * 5} (near-future only, no attendance records)")
        print("-" * 76)
        print("NOT representable in the current schema (no field exists, none added):")
        print("  - College name ('Thadomal Shahani Engineering College')")
        print("  - Academic year ('2026-27')")
        print(f"  Captured instead: program={PILOT_PROGRAM!r}, semester={PILOT_SEMESTER}, division={DIVISION_NAME!r}")
        print("=" * 76)

        if not execute:
            print("\nDry run only (default) — nothing was written.")
            print("Re-run with --execute once you've reviewed this plan.")
            return

        _confirm_target_host(host, assume_yes)

        # ---------- 1. Update all 60 existing students to the same cohort ----------
        updated = 0
        for sp in student_profiles:
            if sp.program != PILOT_PROGRAM or sp.semester != PILOT_SEMESTER:
                admin_service.update_student(
                    db, sp.id, AdminUpdateStudentRequest(program=PILOT_PROGRAM, semester=PILOT_SEMESTER)
                )
                updated += 1
        print(f"Updated {updated} student profiles to the pilot cohort (program/semester).")

        # ---------- 2. Create missing subjects ----------
        subject_by_code: dict[str, Subject] = {EXISTING_SUBJECT_CODE: existing_subject}
        for code, name, credits in to_create_subjects:
            out = admin_service.create_subject(db, AdminCreateSubjectRequest(code=code, name=name, credits=credits))
            subject_by_code[code] = db.get(Subject, out.id)
        for code, _, _ in NEW_SUBJECTS:
            if code not in subject_by_code:
                subject_by_code[code] = db.query(Subject).filter(Subject.code == code).first()
        print(f"Subjects ready: {list(subject_by_code.keys())}")

        # ---------- 3. Create missing professors ----------
        professor_user_by_email: dict[str, ProfessorProfile] = {}
        created_professor_credentials: list[dict] = []
        for name, email in NEW_PROFESSORS:
            existing = (
                db.query(ProfessorProfile)
                .join(User, ProfessorProfile.user_id == User.id)
                .filter(User.email == email)
                .first()
            )
            if existing:
                professor_user_by_email[email] = existing
                continue
            password = _gen_password()
            out = admin_service.create_professor(
                db, AdminCreateProfessorRequest(email=email, password=password, full_name=name, department=DEPARTMENT)
            )
            professor_user_by_email[email] = db.get(ProfessorProfile, out.id)
            created_professor_credentials.append({"full_name": name, "email": email, "password": password})
        existing_prof_profile = existing_professors[0] if existing_professors else None
        print(f"Professors ready: {len(professor_user_by_email) + (1 if existing_prof_profile else 0)} total")

        # ---------- 4. Assignments: existing subject -> existing professor; new subjects -> new professors ----------
        assignments = [(EXISTING_SUBJECT_CODE, existing_prof_profile)]
        for (code, _, _), (name, email) in zip(NEW_SUBJECTS, NEW_PROFESSORS):
            assignments.append((code, professor_user_by_email[email]))

        # ---------- 5. Create missing divisions (one per subject) ----------
        divisions: list[ClassDivision] = []
        for code, professor_profile in assignments:
            subject = subject_by_code[code]
            existing_div = (
                db.query(ClassDivision)
                .filter(ClassDivision.subject_id == subject.id, ClassDivision.name == DIVISION_NAME)
                .first()
            )
            if existing_div:
                divisions.append(existing_div)
                continue
            out = admin_service.create_division(
                db,
                AdminCreateDivisionRequest(
                    subject_id=subject.id,
                    professor_id=professor_profile.id,
                    name=DIVISION_NAME,
                    semester=PILOT_SEMESTER,
                    room=ROOM,
                ),
            )
            divisions.append(db.get(ClassDivision, out.id))
        print(f"Divisions ready: {len(divisions)}")

        # ---------- 6. Enroll all 60 students in every division ----------
        student_ids = [sp.id for sp in student_profiles]
        total_enrolled = 0
        for div in divisions:
            result = admin_service.bulk_enroll(db, student_ids, div.id)
            total_enrolled += len(result.enrolled)
        print(f"New enrollments created: {total_enrolled} (existing/duplicate ones skipped automatically)")

        # ---------- 7. Create a couple of near-future lectures per division ----------
        now = datetime.now(timezone.utc)
        lectures_created = 0
        for div in divisions:
            existing_count = db.query(Lecture).filter(Lecture.class_division_id == div.id).count()
            for i in range(existing_count, LECTURES_PER_DIVISION):
                start = (now + timedelta(days=i + 1)).replace(hour=10, minute=0, second=0, microsecond=0)
                admin_service.create_lecture(
                    db,
                    AdminCreateLectureRequest(
                        class_division_id=div.id,
                        topic=f"Lecture {i + 1}",
                        scheduled_start=start,
                        scheduled_end=start + timedelta(hours=1),
                        room=ROOM,
                    ),
                )
                lectures_created += 1
        print(f"New lectures created: {lectures_created}")

        if created_professor_credentials:
            out_path = _write_credentials_file(created_professor_credentials)
            print(f"\nNew professor credentials written to: {out_path}")
        else:
            print("\nNo new professor accounts were created (all target emails already existed).")

        print("\nDone.")
    except Exception:
        db.rollback()
        print("\nERROR during population — transaction rolled back where possible. Re-run to resume safely (idempotent).", file=sys.stderr)
        raise
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--execute", action="store_true", help="Actually write data (default is dry-run only).")
    parser.add_argument("--yes", action="store_true", help="Skip the interactive typed confirmation (scripted use only).")
    args = parser.parse_args()
    run(execute=args.execute, assume_yes=args.yes)


if __name__ == "__main__":
    main()
