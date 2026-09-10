"""One-time admin bootstrap for ProxyBuster.

There is deliberately no public /register-admin API endpoint — admin accounts are the one
role with no self-registration path at all (students self-register, professors self-register
behind PROFESSOR_INVITE_CODE). This script is the only way to create the first admin account
in a database, run directly from a trusted terminal by someone who already has DATABASE_URL.

WHAT THIS DOES:
  - Connects using the existing configured DATABASE_URL (same Settings/engine as the app).
  - Creates exactly one `users` row with role=ADMIN, using the same bcrypt/passlib hashing
    (`app.core.security.hash_password`) as normal registration.
  - Nothing else. There is no AdminProfile model in app/models/*.py — admin has no profile
    table the way StudentProfile/ProfessorProfile exist for those roles (the role column on
    `users` is sufficient, per require_admin in app/core/deps.py), so this script does not
    invent one. No demo/seed data of any kind is created.

WHAT THIS DOES NOT DO:
  - Never prints the password, JWT_SECRET, QR_SIGNING_SECRET, or DATABASE_URL — only the
    target host (same convention as scripts/reset_demo_data.py) and the created email/id.
  - Never runs automatically — no code path in the application imports this script.
  - Never weakens RBAC — the created account goes through the exact same `authenticate()` /
    `require_admin` path as any other user; nothing here bypasses login or token issuance.

HOW TO USE:

    python scripts/create_admin.py --email you@yourcollege.edu --full-name "Your Name"

The password is never accepted as a command-line argument (it would leak into shell history
and process listings) — it is always prompted for interactively (with a confirmation re-entry)
via getpass, which does not echo to the terminal.

Against any database that isn't obviously local, you'll be asked to type the target host to
confirm before anything is written — same safety convention as scripts/reset_demo_data.py.
"""
import argparse
import getpass
import sys
from pathlib import Path
from urllib.parse import urlsplit

# Allow running this script directly (`python scripts/create_admin.py`) regardless of current
# working directory — `app` lives in backend/, one level up from this file.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import email_validator  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402


class AdminBootstrapError(Exception):
    pass


def create_admin_user(db: Session, email: str, password: str, full_name: str) -> User:
    """Core logic, kept separate from CLI/prompting so it can be exercised directly in tests.

    Transactional: on any failure the caller's session is left uncommitted and the exception
    propagates — callers should catch and roll back, exactly like scripts/reset_demo_data.py.
    """
    try:
        email_validator.validate_email(email, test_environment=True, check_deliverability=False)
    except email_validator.EmailNotValidError as exc:
        raise AdminBootstrapError(f"Invalid email address: {exc}") from exc

    if len(password) < 8:
        raise AdminBootstrapError("Password must be at least 8 characters.")

    if not full_name.strip():
        raise AdminBootstrapError("Full name is required.")

    existing = db.query(User).filter(User.email == email).first()
    if existing is not None:
        raise AdminBootstrapError(f"A user with email {email!r} already exists (role={existing.role.value}).")

    user = User(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        role=UserRole.ADMIN,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _confirm_target_host(host: str) -> None:
    if host in ("", "localhost", "127.0.0.1", "postgres"):
        return  # local dev / docker-compose service name — no confirmation needed
    print(f"DATABASE_URL points at host: {host!r}")
    answer = input(f"Type the host ({host}) to confirm you want to create an admin here: ")
    if answer.strip() != host:
        print("Confirmation did not match — aborting. No data was written.")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True, help="Admin login email.")
    parser.add_argument("--full-name", required=True, help="Admin's display name.")
    args = parser.parse_args()

    settings = get_settings()
    host = urlsplit(settings.database_url.replace("postgresql+psycopg2", "postgresql")).hostname or "unknown"
    _confirm_target_host(host)

    password = getpass.getpass("Admin password (min 8 characters, input hidden): ")
    password_confirm = getpass.getpass("Confirm password: ")
    if password != password_confirm:
        print("Passwords did not match — aborting. No data was written.", file=sys.stderr)
        sys.exit(1)

    db = SessionLocal()
    try:
        user = create_admin_user(db, email=args.email, password=password, full_name=args.full_name)
    except AdminBootstrapError as exc:
        db.rollback()
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception:
        db.rollback()
        print("\nERROR creating admin — transaction rolled back. No data was changed.", file=sys.stderr)
        raise
    else:
        print(f"\nAdmin account created: {user.email} (id={user.id}, role={user.role.value}) on host {host!r}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
