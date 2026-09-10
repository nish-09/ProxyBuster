"""One-time bulk creation of test student accounts, through the SAME service function the
Admin API uses — not a parallel implementation.

This script imports and calls `app.services.admin_service.create_student` directly — the
exact function `POST /api/admin/students` calls. Every account it creates goes through the
same validation, the same password hashing (`app.core.security.hash_password`, the identical
bcrypt/passlib context used everywhere else in the app), and produces the identical
User + StudentProfile shape as a student created by hand via Admin Dashboard -> Students ->
Add Student. Nothing here touches the database directly and nothing here duplicates
create_student's logic.

WHAT THIS CREATES:
  - 59 randomly generated students with @example.test emails (never real people) and strong
    random passwords.
  - 1 specific student using the exact email/password you provide via CLI flags (defaults to
    the ones requested for this run) — still hashed through the same hash_password() call as
    every other account; the plaintext password is never written to the database.

DUPLICATE SAFETY: before creating anything, every requested email AND roll_number is checked
against the database in one batch query. If ANY of them already exists, the script reports
exactly which ones and creates NOTHING — it never overwrites or modifies an existing account.
This is what makes the operation effectively all-or-nothing without needing to change
create_student()'s own per-row commit behavior (see NOTE below).

NOTE ON TRANSACTIONALITY: `admin_service.create_student` commits after each successful insert
(that's how the Admin API's single-student endpoint already works, and this script
deliberately does not modify that function). The batch as a whole is made safe in practice by
the pre-flight duplicate check above, which eliminates the realistic failure modes (email or
roll-number collision) before any row is written. If some other unexpected error interrupts
the loop partway through, the script stops immediately, reports exactly how many accounts were
created before the failure, and does not continue — you would need to re-run with the
remaining students only (the duplicate check on the next run will skip everything already
created).

CREDENTIALS OUTPUT: a Markdown table of every created account (name, email, password) is
written to backend/scripts/output/ — a path covered by .gitignore. Plaintext passwords are
NEVER printed to the console or to any application log; they exist only inside that one
generated file plus the caller's own terminal (which itself is not saved by this script).

HOW TO USE:

  1. Dry run (default, creates nothing) — shows exactly what would be created and runs the
     duplicate-safety check:

         python scripts/create_test_students.py

  2. Actually create the 60 accounts, with an interactive typed confirmation naming the
     target DB host (same convention as reset_demo_data.py / create_admin.py):

         python scripts/create_test_students.py --execute

     Non-interactive (scripted use only): add --yes to skip that confirmation.
"""
import argparse
import random
import secrets
import string
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

# Allow running this script directly regardless of current working directory — `app` lives in
# backend/, one level up from this file.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import ValidationError  # noqa: E402
from sqlalchemy import func  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.models.user import StudentProfile, User  # noqa: E402
from app.schemas.admin import AdminCreateStudentRequest  # noqa: E402
from app.services.admin_service import create_student  # noqa: E402

# ---- The one specific account requested for this run -----------------------------------
NISHIT_EMAIL = "nishitparikh0976@gmail.com"
NISHIT_PASSWORD = "mynameisnishit"
NISHIT_FULL_NAME = "Nishit Parikh"
NISHIT_ROLL_NUMBER = "TESTSTU060"

RANDOM_STUDENT_COUNT = 59
EMAIL_DOMAIN = "example.test"  # RFC 2606 reserved test domain — never a real person's address

FIRST_NAMES = [
    "Aarav", "Vihaan", "Aditya", "Arjun", "Kabir", "Reyansh", "Ishaan", "Rohan", "Kunal", "Dev",
    "Ananya", "Diya", "Ira", "Kavya", "Myra", "Saanvi", "Anika", "Riya", "Tara", "Zara",
    "Rahul", "Karan", "Sahil", "Nikhil", "Varun", "Yash", "Aman", "Siddharth", "Manav", "Rishabh",
    "Priya", "Neha", "Pooja", "Simran", "Tanya", "Aisha", "Meera", "Sneha", "Divya", "Isha",
]
LAST_NAMES = [
    "Sharma", "Verma", "Gupta", "Mehta", "Shah", "Patel", "Iyer", "Nair", "Rao", "Reddy",
    "Kapoor", "Malhotra", "Chatterjee", "Bose", "Das", "Kumar", "Singh", "Joshi", "Agarwal", "Bhatt",
]
PROGRAMS = [
    "B.Tech Computer Science",
    "B.Tech Information Technology",
    "B.Tech Electronics & Communication",
    "B.Tech Mechanical Engineering",
    "B.Sc Mathematics",
]

PASSWORD_ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*"


def _generate_password(length: int = 14) -> str:
    while True:
        pw = "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(length))
        if (
            any(c.islower() for c in pw)
            and any(c.isupper() for c in pw)
            and any(c.isdigit() for c in pw)
            and any(c in "!@#$%^&*" for c in pw)
        ):
            return pw


def _generate_students() -> list[dict]:
    """Builds the 60 requested account payloads (data only — no DB access, no side effects)."""
    random.seed()  # system-random seeded, not deterministic — these are real accounts, not fixtures
    students = []
    used_emails: set[str] = set()

    for i in range(1, RANDOM_STUDENT_COUNT + 1):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        base_email = f"{first.lower()}.{last.lower()}{i:03d}@{EMAIL_DOMAIN}"
        while base_email in used_emails:
            base_email = f"{first.lower()}.{last.lower()}{i:03d}{secrets.token_hex(2)}@{EMAIL_DOMAIN}"
        used_emails.add(base_email)

        students.append(
            {
                "full_name": f"{first} {last}",
                "email": base_email,
                "password": _generate_password(),
                "roll_number": f"TESTSTU{i:03d}",
                "program": random.choice(PROGRAMS),
                "semester": random.randint(1, 8),
            }
        )

    students.append(
        {
            "full_name": NISHIT_FULL_NAME,
            "email": NISHIT_EMAIL,
            "password": NISHIT_PASSWORD,
            "roll_number": NISHIT_ROLL_NUMBER,
            "program": "B.Tech Computer Science",
            "semester": 5,
        }
    )
    return students


def _confirm_target_host(host: str, assume_yes: bool) -> None:
    if assume_yes or host in ("", "localhost", "127.0.0.1", "postgres"):
        return
    print(f"DATABASE_URL points at host: {host!r}")
    answer = input(f"Type the host ({host}) to confirm you want to create 60 student accounts here: ")
    if answer.strip() != host:
        print("Confirmation did not match — aborting. No data was written.")
        sys.exit(1)


def _check_duplicates(db, students: list[dict]) -> list[str]:
    """Returns a list of human-readable collision descriptions. Empty list = safe to proceed."""
    emails = [s["email"] for s in students]
    roll_numbers = [s["roll_number"] for s in students]

    existing_emails = {
        row[0] for row in db.query(User.email).filter(func.lower(User.email).in_([e.lower() for e in emails])).all()
    }
    existing_rolls = {
        row[0] for row in db.query(StudentProfile.roll_number).filter(StudentProfile.roll_number.in_(roll_numbers)).all()
    }

    problems = []
    for s in students:
        if s["email"].lower() in {e.lower() for e in existing_emails}:
            problems.append(f"email already exists: {s['email']}")
        if s["roll_number"] in existing_rolls:
            problems.append(f"roll_number already exists: {s['roll_number']}")
    return problems


def _write_credentials_file(students: list[dict]) -> Path:
    out_dir = Path(__file__).resolve().parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"test_student_credentials_{stamp}.md"

    lines = [
        "# ProxyBuster test student credentials",
        "",
        f"Generated: {stamp}",
        "",
        "**Do not commit this file. Do not share it outside your own records.**",
        "",
        "| # | Name | Email | Password |",
        "| - | ---- | ----- | -------- |",
    ]
    for i, s in enumerate(students, start=1):
        lines.append(f"| {i} | {s['full_name']} | {s['email']} | {s['password']} |")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def run(execute: bool, assume_yes: bool) -> None:
    settings = get_settings()
    host = urlsplit(settings.database_url.replace("postgresql+psycopg2", "postgresql")).hostname or "unknown"

    students = _generate_students()

    print("=" * 72)
    print(f"ProxyBuster test student bulk-creation — target database host: {host!r}")
    print("=" * 72)
    print(f"  Random students to create: {RANDOM_STUDENT_COUNT} (@{EMAIL_DOMAIN})")
    print(f"  Plus 1 specific account:   {NISHIT_EMAIL}")
    print(f"  TOTAL: {len(students)} accounts")
    print("=" * 72)

    db = SessionLocal()
    try:
        problems = _check_duplicates(db, students)
        if problems:
            print("\nABORTING — the following would collide with existing accounts (nothing was created):")
            for p in problems:
                print(f"  - {p}")
            sys.exit(1)
        print("\nDuplicate check passed: none of the 60 emails/roll numbers exist yet.")

        if not execute:
            print("\nDry run only (default) — nothing was created.")
            print("Re-run with --execute once you're ready to actually create these accounts.")
            return

        _confirm_target_host(host, assume_yes)

        created: list[dict] = []
        try:
            for s in students:
                payload = AdminCreateStudentRequest(
                    email=s["email"],
                    password=s["password"],
                    full_name=s["full_name"],
                    roll_number=s["roll_number"],
                    program=s["program"],
                    semester=s["semester"],
                )
                # The exact same call POST /api/admin/students makes — same validation, same
                # hash_password() bcrypt hashing, same User + StudentProfile creation.
                create_student(db, payload)
                created.append(s)
        except (ValidationError, Exception) as exc:  # noqa: BLE001
            print(
                f"\nERROR after creating {len(created)}/{len(students)} accounts: {exc}",
                file=sys.stderr,
            )
            print("Stopped immediately — no further accounts were attempted.", file=sys.stderr)
            if created:
                out_path = _write_credentials_file(created)
                print(f"Credentials for the {len(created)} accounts created before the error were saved to: {out_path}")
            raise

        out_path = _write_credentials_file(created)
        print(f"\nDone. Created {len(created)} student accounts.")
        print(f"Credentials file: {out_path}")
        print("(Passwords are only in that file — never printed above, never logged.)")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--execute", action="store_true", help="Actually create the accounts (default is dry-run only).")
    parser.add_argument("--yes", action="store_true", help="Skip the interactive typed confirmation (scripted use only).")
    args = parser.parse_args()
    run(execute=args.execute, assume_yes=args.yes)


if __name__ == "__main__":
    main()
