"""Safe, explicit data reset for ProxyBuster.

Deletes ALL application data — every user, academic structure row, attendance record, and
security/session row — while leaving the schema, indexes, constraints, and Alembic migration
history completely untouched. Use this to clear demo/seed data out of a database (including
Supabase) before it goes live with real students, professors, subjects, and attendance.

WHAT THIS DOES NOT DO:
  - Does not touch table definitions, columns, indexes, or constraints (no DDL at all).
  - Does not touch the `alembic_version` table — migration history is preserved.
  - Does not drop or truncate-with-cascade; it issues explicit DELETEs in FK-safe order.
  - Never runs on its own. There is no code path anywhere in the application that imports
    or calls this script — it only runs when a human invokes it directly from a terminal.

HOW TO USE:

  1. Dry run (default, deletes nothing) — shows exactly what would be deleted:

         python scripts/reset_demo_data.py

  2. Actually delete, with an interactive typed confirmation naming the target DB host:

         python scripts/reset_demo_data.py --execute

  3. Non-interactive (CI/scripted use only — never pass this against a database you haven't
     already reviewed the dry-run output for):

         python scripts/reset_demo_data.py --execute --yes

TRANSACTION SAFETY: every DELETE runs inside a single database transaction. If any statement
fails, the whole transaction is rolled back and the database is left exactly as it was —
this is an all-or-nothing operation, never a partial one.
"""
import argparse
import sys
from pathlib import Path
from urllib.parse import urlsplit

# Allow running this script directly (`python scripts/reset_demo_data.py`) regardless of
# current working directory — `app` lives in backend/, one level up from this file.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
import app.models  # noqa: E402,F401 (registers all tables on Base.metadata; harmless if unused here)

# Deletion order mirrors every FK relationship in app/models/*.py — each table is deleted
# only after every table that references it via a foreign key has already been cleared.
TABLES_IN_DELETE_ORDER = [
    "manual_attendance",       # -> attendance_records, professor_profiles
    "attendance_tokens",       # -> attendance_sessions, student_profiles
    "attendance_records",      # -> student_profiles, lectures, attendance_sessions
    "attendance_sessions",     # -> lectures, professor_profiles
    "lectures",                # -> class_divisions
    "enrollments",             # -> student_profiles, class_divisions
    "class_divisions",         # -> subjects, professor_profiles
    "subjects",
    "anomaly_scores",          # -> student_profiles
    "cooldowns",                # -> student_profiles
    "security_events",         # -> users
    "device_sessions",         # -> users
    "student_profiles",        # -> users
    "professor_profiles",      # -> users
    "users",
]


def _row_counts(db) -> dict[str, int]:
    return {table: db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() for table in TABLES_IN_DELETE_ORDER}


def _print_report(row_counts: dict[str, int], host: str) -> int:
    total = sum(row_counts.values())
    print("=" * 72)
    print(f"ProxyBuster data reset — target database host: {host!r}")
    print("=" * 72)
    for table, count in row_counts.items():
        marker = "" if count == 0 else "  <-- will be deleted"
        print(f"  {table:<22} {count:>8}{marker}")
    print("-" * 72)
    print(f"  TOTAL ROWS TO DELETE: {total}")
    print("=" * 72)
    print("NOT affected: table schema, indexes, constraints, alembic_version (migration history).")
    return total


def run(execute: bool, assume_yes: bool) -> None:
    settings = get_settings()
    host = urlsplit(settings.database_url.replace("postgresql+psycopg2", "postgresql")).hostname or "unknown"

    db = SessionLocal()
    try:
        row_counts = _row_counts(db)
        total = _print_report(row_counts, host)

        if total == 0:
            print("\nNothing to delete — database is already empty.")
            return

        if not execute:
            print("\nDry run only (default) — nothing was deleted.")
            print("Re-run with --execute once you've reviewed this list and are ready to proceed.")
            return

        if not assume_yes:
            print(f"\nThis is IRREVERSIBLE and will permanently delete {total} rows from host {host!r}.")
            answer = input(f"Type the host ({host}) to confirm: ")
            if answer.strip() != host:
                print("Confirmation did not match — aborting. No data was deleted.")
                sys.exit(1)

        try:
            for table in TABLES_IN_DELETE_ORDER:
                db.execute(text(f"DELETE FROM {table}"))
            db.commit()
        except Exception:
            db.rollback()
            print("\nERROR during delete — transaction rolled back. No data was changed.", file=sys.stderr)
            raise

        print(f"\nDone. Deleted {total} rows across {len(TABLES_IN_DELETE_ORDER)} tables. Schema and migration history untouched.")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--execute", action="store_true", help="Actually delete data (default is dry-run only).")
    parser.add_argument("--yes", action="store_true", help="Skip the interactive typed confirmation (scripted use only).")
    args = parser.parse_args()
    run(execute=args.execute, assume_yes=args.yes)


if __name__ == "__main__":
    main()
